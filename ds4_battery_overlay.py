# -*- coding: utf-8 -*-
"""
DS4 电量提示悬浮窗
==================
功能：
  · 手柄接入（USB / 蓝牙）时，屏幕底部居中弹出电量提示，显示 5 秒后淡出
  · 显示充电状态：充电中（绿色）、已充满（绿色）、低电量（红色，停留更久）
  · 低电量自动提醒：电量 ≤ 20% 时红色高亮弹窗并停留 8 秒；连接期间每 30 秒检查一次
  · 拔出提示：手柄断开时弹出"手柄已断开"提示
  · PS 双击（500ms 内按两次）→ 立即弹出当前电量（窗口始终置顶）
  · 十字键下 + PS 组合键 → 屏幕正上方显示/隐藏有色电量横条（左侧数字电量，
    随电量变色，显示期间每 5 秒自动刷新）
  · 开机自启（注册表 HKCU Run），支持随时开关

依赖：pywinusb   （python -m pip install pywinusb）
运行：python ds4_battery_overlay.py
预览：python ds4_battery_overlay.py --preview 66   （显示一个 66% 的假电量，用于无手柄时测试界面）
      python ds4_battery_overlay.py --preview-bar 66 （预览顶部电量横条）
开机自启：
  python ds4_battery_overlay.py --autostart     开启
  python ds4_battery_overlay.py --no-autostart  取消

退出：右键点击弹出的电量窗即可退出程序；或在任务管理器中结束 pythonw/python 进程。
"""

import ctypes
import os
import queue
import sys
import threading
import time
import traceback
import tkinter as tk

try:
    from pywinusb import hid
except ImportError:
    print("[错误] 缺少依赖 pywinusb，请先安装：")
    print("       python -m pip install pywinusb")
    sys.exit(1)

# ---------------- 配置 ----------------
DS4_VID = 0x054C                       # Sony Interactive Entertainment
DS4_PIDS = (0x09CC, 0x0BA0, 0x05C4)    # DS4 常见 PID：初版 / 2016 新版 / 早期型号
BATTERY_INDEX = 30                     # 电量状态字节（USB 0x01 报告，含 Report ID）
BT_BATTERY_INDEX = 40                  # 电量状态字节（蓝牙 0x11 完整报告）
PS_BUTTON_INDEX = 7                    # PS 按键所在字节（USB 0x01 报告）
PS_BUTTON_MASK = 0x01                  # PS 按键掩码（bit0）
DPAD_INDEX = 5                         # 十字键所在字节（USB 0x01 报告）
POV_DOWN = 4                           # 十字键"下"的 POV 值（8=未按，0=上，4=下）
DOUBLE_PRESS_MS = 500                  # PS 双击判定窗口（毫秒）
BT_HEADER_EXTRA = 2                    # 蓝牙(0x11)报告头部比 USB(0x01) 多 2 字节（0xc0 0x00），按键等偏移 +2
# 蓝牙 DS4 激活：未发送 0x11 输出配置报告前，部分蓝牙 DS4 只发 0x01 位置报告
# （无按键、无电量），发送后才切换到 0x11 完整报告（实测必需）。
BT_ACTIVATE_LENS = (79, 547)           # 0x11 输出报告候选长度（部分设备要求 547）
BT_ACTIVATE_LED = 0xFF                 # 激活配置的 LED R（红色）

HOLD_SECONDS = 5.0                     # 电量显示保持时间（秒）
HOLD_LOW_SECONDS = 8.0                 # 低电量提示保持时间（秒）
HOLD_DISCONNECT_SECONDS = 2.5          # 拔出提示保持时间（秒）
LOW_BATTERY_PCT = 20                   # 低电量阈值（%）
LOW_CHECK_INTERVAL_POLLS = 30          # 低电量周期检查（每 30 次轮询 ≈ 30 秒）
FADE_IN_MS = 200                       # 淡入总时长（毫秒）
FADE_OUT_MS = 500                      # 淡出总时长（毫秒）
POLL_MS = 1000                         # 手柄接入检测轮询间隔（毫秒）
READ_TIMEOUT = 2.0                     # 读取电量超时（秒）

# 顶部电量横条（组合键：十字键下 + PS 切换显示）
BAR_W, BAR_H = 300, 50
BAR_REFRESH_POLLS = 5                  # 横条显示时每 5 秒自动刷新一次
BAR_TOP_MARGIN = 8                     # 距屏幕顶部

PANEL_BG = "#161A1E"
PANEL_BORDER = "#2E353D"
TEXT_MAIN = "#EDF1F6"
TEXT_SUB = "#9AA3AD"
BAT_OUTLINE = "#C7CFD8"
BAT_EMPTY = "#3A414A"
BAT_GOOD = "#3DDC84"
BAT_MID = "#F5B700"
BAT_LOW = "#E5484D"
MAGIC = "#010101"                      # 透明色键（不参与绘制，用于圆角镂空）

W, H = 340, 90

# 程序目录：PyInstaller 打包后 __file__ 指向临时解压目录，改用 exe 所在目录
if getattr(sys, "frozen", False):
    BASE_DIR = os.path.dirname(sys.executable)
else:
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))

LOG_PATH = os.path.join(BASE_DIR, "ds4_battery_overlay.log")
LOG_MAX_BYTES = 200 * 1024   # 日志体积上限 200 KB，超限自动裁剪
LOG_KEEP_LINES = 200         # 裁剪时保留最近 200 行


def _trim_log(path):
    """日志超过上限时只保留最近 LOG_KEEP_LINES 行，控制体积。"""
    with open(path, "r", encoding="utf-8") as f:
        lines = f.readlines()
    with open(path, "w", encoding="utf-8") as f:
        f.writelines(lines[-LOG_KEEP_LINES:])


def log(msg):
    """写运行日志到脚本同目录，便于无控制台(pythonw)时排查问题。

    日志体积有上限（LOG_MAX_BYTES），超限自动裁剪，不会无限增长。
    """
    try:
        if os.path.exists(LOG_PATH) and \
                os.path.getsize(LOG_PATH) > LOG_MAX_BYTES:
            _trim_log(LOG_PATH)
        with open(LOG_PATH, "a", encoding="utf-8") as f:
            f.write("[%s] %s\n" % (time.strftime("%Y-%m-%d %H:%M:%S"), msg))
    except Exception:
        pass


def round_rect(canvas, x1, y1, x2, y2, r, **kw):
    """在 canvas 上画一个圆角矩形（pill 形）。"""
    pts = [x1 + r, y1, x2 - r, y1, x2, y1, x2, y1 + r,
           x2, y2 - r, x2, y2, x2 - r, y2, x1 + r, y2,
           x1, y2, x1, y2 - r, x1, y1 + r, x1, y1]
    return canvas.create_polygon(pts, smooth=True, **kw)


def find_ds4_devices():
    """枚举当前接入的 DS4 设备列表。"""
    try:
        devices = hid.HidDeviceFilter(vendor_id=DS4_VID).get_devices()
    except Exception:
        return []
    return [d for d in devices if d.product_id in DS4_PIDS]


def read_ds4_battery():
    """读取第一个可用 DS4 的电量百分比；读取失败返回 None。"""
    for dev in find_ds4_devices():
        pct = read_battery_from_device(dev)
        if pct is not None:
            return pct
    return None


def decode_status(status, is_bt=False):
    """
    解析电量状态字节，返回 {"pct","cable","charging","full"}。

    USB(0x01) 报告 byte30：bit3-0 = 电量档位(0-10)，bit4 = 充电中，bit5 = 已充满。
    蓝牙(0x11) 报告 byte40：bit3-0 = 电量档位(0-10)；充电/充满标志按实测设备
    用 bit4/bit5，同时兼容 Linux hid-sony 的 bit6/bit7（任一命中即生效）。
    档位均按 0-10 档 ×10 换算。
    """
    level = status & 0x0F
    if is_bt:
        charging = bool(status & 0x10) or bool(status & 0x40)
        full = bool(status & 0x20) or bool(status & 0x80)
    else:
        charging = bool(status & 0x10)
        full = bool(status & 0x20)
    pct = 100 if full else level * 10
    return {"pct": max(0, min(100, pct)),
            "cable": not is_bt and bool(status & 0x10),
            "charging": charging, "full": full}


def decode_battery(status, is_bt=False):
    """兼容接口：只返回百分比。"""
    return decode_status(status, is_bt)["pct"]


def is_bt_device(dev):
    """判断设备是否蓝牙 HID 接入（蓝牙设备路径含 BTHENUM 或蓝牙 HID GUID）。"""
    p = getattr(dev, "device_path", "") or ""
    return "BTHENUM" in p.upper() or "00001124-0000-1000-8000-00805F9B34FB" in p.upper()


def activate_bt_full_report(dev):
    """激活蓝牙 DS4 完整报告模式。

    蓝牙 DS4 默认只发 0x01 位置报告（仅摇杆数据，无按键、无电量）。
    读取 FEATURE report 0x02（校准数据）后，设备才会切换到 0x11 完整报告
    （电量位于 byte40）——这是实测有效的机制，Linux hid-sony 驱动同样如此。
    发送 0x11 输出报告无法触发切换（实测无效），仅作兜底保留。
    """
    try:
        feats = dev.find_feature_reports()
        for r in feats:
            if getattr(r, "report_id", None) != 0x02:
                continue
            r.get()          # GET REPORT FEATURE 0x02 → 触发切换到 0x11
            return True
    except Exception:
        pass
    # 兜底：发送 0x11 输出配置报告（部分固件可用）
    try:
        reps = dev.find_output_reports()
        for r in reps:
            if getattr(r, "report_id", None) != 0x11:
                continue
            for ln in BT_ACTIVATE_LENS:
                buf = bytearray(ln)
                buf[0] = 0x11
                if ln > 2:
                    buf[1], buf[2] = 0xC0, 0x00
                if ln > 5:
                    buf[5] = BT_ACTIVATE_LED
                try:
                    r.send(bytes(buf))
                    return True
                except Exception:
                    continue
    except Exception:
        pass
    return False


# 蓝牙报告诊断：首帧 hex 转储限频（秒），便于核对真实字节布局
_bt_dump_last = 0.0


def maybe_dump_bt_report(data):
    """蓝牙(0x11)报告首次出现时把关键字节写入日志，供排查电量解析问题。"""
    global _bt_dump_last
    if not data or data[0] != 0x11:
        return
    now = time.time()
    if now - _bt_dump_last < 30:
        return
    _bt_dump_last = now
    hexs = " ".join("%02X" % b for b in data[:42])
    b40 = data[40] if len(data) > 40 else None
    log(f"蓝牙报告诊断: 长度={len(data)} byte40={b40:#04x} 前42字节: {hexs}")


def decode_bt_report(data, bi=BT_BATTERY_INDEX):
    """
    蓝牙(0x11)完整报告电量字节解析（电量位于 byte40）。
    返回与 decode_status 相同的结构。
    """
    raw = data[bi] if len(data) > bi else 0
    return decode_status(raw, is_bt=True)


def report_offsets(data):
    """
    返回 (电量字节偏移, PS 按键字节偏移)。
    USB(0x01) 报告：电量@30、PS@7；蓝牙(0x11) 完整报告：电量@40、PS@9。
    非 DS4 主输入报告返回 None。
    """
    if not data or data[0] not in (0x01, 0x11):
        return None
    if data[0] == 0x11:
        return BT_BATTERY_INDEX, BT_HEADER_EXTRA + PS_BUTTON_INDEX
    return BATTERY_INDEX, PS_BUTTON_INDEX


def dpad_index(data):
    """十字键字节偏移（USB@5 / 蓝牙@7）；非 DS4 主输入报告返回 None。"""
    if not data or data[0] not in (0x01, 0x11):
        return None
    extra = BT_HEADER_EXTRA if data[0] == 0x11 else 0
    return extra + DPAD_INDEX


def dpad_down(data, dpi=None):
    """判断十字键"下"是否处于按下状态（POV 值 = 4）。"""
    if dpi is None:
        dpi = dpad_index(data)
    if dpi is None or len(data) <= dpi:
        return False
    return (data[dpi] & 0x0F) == POV_DOWN


def read_battery_from_device(dev):
    """
    读取 DS4 电量。
    报告格式：USB 连接时输入报告 ID 为 0x01（64 字节），蓝牙为 0x11
    （78 字节，头部多 2 字节 0xc0 0x00）。
    电量状态字节位于第 30（USB）/ 40（蓝牙完整报告）字节：
        bit3-0 = 电量档位（0-10）；bit4 = 充电中；bit5 = 已充满。
    蓝牙设备打开后先读取 FEATURE 0x02（校准数据）激活完整报告模式（实测必需）。
    """
    result = {}
    got = threading.Event()

    def handler(data):
        try:
            offs = report_offsets(data)
            if offs is None:
                return
            bi, _ = offs
            if len(data) <= bi:
                return
            if data[0] == 0x11:
                maybe_dump_bt_report(data)
                result["pct"] = decode_bt_report(data, bi)["pct"]
            elif is_bt_device(dev):
                return  # 蓝牙设备激活前的位置报告(0x01)无电量，忽略
            else:
                result["pct"] = decode_battery(data[bi])
            got.set()
        except Exception:
            pass

    opened = False
    try:
        # 先注册回调再打开：设备打开瞬间送出的首帧报告即可被捕获
        # （DS4 默认只在状态变化时发报告，不会持续刷屏）
        dev.set_raw_data_handler(handler)
        dev.open()
        opened = dev.is_opened()
        if opened:
            if is_bt_device(dev):
                activate_bt_full_report(dev)
            got.wait(timeout=READ_TIMEOUT)
    except Exception:
        pass
    finally:
        if opened:
            try:
                dev.close()  # close() 会停止内部读取线程
            except Exception:
                pass
    return result.get("pct")


def read_ds4_status():
    """读取第一个可用 DS4 的电量状态（含充电/充满标志）；失败返回 None。"""
    for dev in find_ds4_devices():
        info = read_status_from_device(dev)
        if info is not None:
            return info
    return None


def read_status_from_device(dev):
    """打开设备读取首帧输入报告并解析电量状态。"""
    result = {}
    got = threading.Event()

    def handler(data):
        try:
            offs = report_offsets(data)
            if offs is None:
                return
            bi, _ = offs
            if len(data) <= bi:
                return
            if data[0] == 0x11:
                maybe_dump_bt_report(data)
                result["info"] = decode_bt_report(data, bi)
            elif is_bt_device(dev):
                return  # 蓝牙设备激活前的位置报告(0x01)无电量，忽略
            else:
                result["info"] = decode_status(data[bi])
            got.set()
        except Exception:
            pass

    opened = False
    try:
        dev.set_raw_data_handler(handler)
        dev.open()
        opened = dev.is_opened()
        if opened:
            if is_bt_device(dev):
                activate_bt_full_report(dev)
            got.wait(timeout=READ_TIMEOUT)
    except Exception:
        pass
    finally:
        if opened:
            try:
                dev.close()
            except Exception:
                pass
    return result.get("info")


class BatteryOverlay:
    def __init__(self):
        # 异常兜底：无控制台(pythonw)时所有未捕获异常写入日志，避免静默停摆
        sys.excepthook = lambda t, v, tb: log(
            "未捕获异常:\n" + "".join(traceback.format_exception(t, v, tb)))
        self.root = tk.Tk()
        self.root.report_callback_exception = lambda t, v, tb: log(
            "回调异常:\n" + "".join(traceback.format_exception(t, v, tb)))
        self.root.withdraw()
        self.root.overrideredirect(True)
        self.root.attributes("-topmost", True)
        try:
            self.root.attributes("-transparentcolor", MAGIC)
        except tk.TclError:
            pass
        self.root.attributes("-alpha", 0.0)

        sw, sh = self.root.winfo_screenwidth(), self.root.winfo_screenheight()
        x = (sw - W) // 2
        y = sh - H - 90
        self.root.geometry(f"{W}x{H}+{x}+{y}")

        self.canvas = tk.Canvas(self.root, width=W, height=H,
                                bg=MAGIC, highlightthickness=0)
        self.canvas.pack()
        # 右键点击弹窗 = 退出程序
        self.canvas.bind("<Button-3>", lambda e: self.root.destroy())

        # 顶部电量横条窗口（组合键：十字键下 + PS 切换显示）
        self.bar_win = tk.Toplevel(self.root)
        self.bar_win.withdraw()
        self.bar_win.overrideredirect(True)
        self.bar_win.attributes("-topmost", True)
        try:
            self.bar_win.attributes("-transparentcolor", MAGIC)
        except tk.TclError:
            pass
        bx = (sw - BAR_W) // 2
        by = BAR_TOP_MARGIN
        self.bar_win.geometry(f"{BAR_W}x{BAR_H}+{bx}+{by}")
        self.bar_canvas = tk.Canvas(self.bar_win, width=BAR_W, height=BAR_H,
                                    bg=MAGIC, highlightthickness=0)
        self.bar_canvas.pack()
        # 右键点击横条 = 关闭横条
        self.bar_canvas.bind("<Button-3>",
                             lambda e: self.result_q.put({"kind": "toggle_bar"}))

        self.state = "hidden"      # hidden / shown / fading
        self.alpha = 0.0
        self.anim_job = None
        self.timer_job = None
        self.result_q = queue.Queue()
        self.prev_connected = None
        self.first_poll = True
        self.watch_dev = None    # 常驻手柄句柄（监听 PS 键用）
        self.ps_prev = False
        self.last_ps_time = None # PS 双击判定：上一次按下时间
        self.bar_visible = False # 电量横条是否显示
        self.bar_last_key = None # 横条上次绘制内容（去重）
        self.low_warned = False  # 本轮低电量是否已提示过（用于周期检查去重）
        self.poll_count = 0      # 低电量周期检查计数器
        self._last_lowcheck = None  # 上次例行检查的(电量,充电,充满)，用于去重日志

        self.root.after(300, self.poll_loop)

    # ---------- 绘制 ----------
    def draw_battery(self, percent, charging=False, full=False):
        c = self.canvas
        c.delete("all")
        low = percent is not None and percent <= LOW_BATTERY_PCT
        border = BAT_LOW if low else PANEL_BORDER
        round_rect(c, 4, 4, W - 4, H - 4, 24, fill=PANEL_BG,
                   outline=border, width=2)

        bx, by, bw, bh = 34, 31, 62, 28
        pct_show = None if percent is None else max(0, min(100, int(percent)))

        # 电池外框 + 正极帽
        c.create_rectangle(bx, by, bx + bw, by + bh,
                           outline=BAT_OUTLINE, width=2)
        c.create_rectangle(bx + bw + 1, by + 8, bx + bw + 6, by + bh - 8,
                           fill=BAT_OUTLINE, outline=BAT_OUTLINE)

        # 电量填充（低电量红色高亮）
        if pct_show is None:
            fill = BAT_EMPTY
        elif pct_show <= LOW_BATTERY_PCT:
            fill = BAT_LOW
        elif pct_show < 60:
            fill = BAT_MID
        else:
            fill = BAT_GOOD
        fw = int((bw - 6) * (pct_show if pct_show is not None else 0) / 100)
        if fw > 0:
            c.create_rectangle(bx + 3, by + 3, bx + 3 + fw, by + bh - 3,
                               fill=fill, outline=fill)

        # 百分比 + 状态文字
        txt = "--%" if pct_show is None else f"{pct_show}%"
        c.create_text(128, 40, text=txt, anchor="w",
                      font=("Segoe UI", 30, "bold"),
                      fill=BAT_LOW if low else TEXT_MAIN)
        if low:
            sub, sub_color = "低电量 · 请及时充电", BAT_LOW
        elif charging:
            sub, sub_color = "充电中", BAT_GOOD
        elif full:
            sub, sub_color = "已充满", BAT_GOOD
        else:
            sub, sub_color = "DUALSHOCK 4", TEXT_SUB
        c.create_text(131, 68, text=sub, anchor="w",
                      font=("Segoe UI", 9), fill=sub_color)

    def draw_message(self, title, sub):
        c = self.canvas
        c.delete("all")
        round_rect(c, 4, 4, W - 4, H - 4, 24, fill=PANEL_BG,
                   outline=PANEL_BORDER, width=2)
        c.create_text(W // 2, 36, text=title, anchor="center",
                      font=("Segoe UI", 22, "bold"), fill=TEXT_MAIN)
        c.create_text(W // 2, 64, text=sub, anchor="center",
                      font=("Segoe UI", 9), fill=TEXT_SUB)

    # ---------- 顶部电量横条 ----------
    def draw_bar(self, percent, charging=False, full=False, connected=True):
        """绘制顶部电量横条（严格按参考图方案）：
        背景完全透明（白色即去色区）；左上状态标签；
        底部一条随电量变色的进度条；百分比数字居中、与进度条重叠。"""
        c = self.bar_canvas
        c.delete("all")
        pct_show = None if (not connected or percent is None) \
            else max(0, min(100, int(percent)))

        # 进度条颜色随电量：≤20% 红 / 20–60% 黄 / >60% 绿；未连接浅灰
        if pct_show is None:
            fill = "#D1D5DB"
        elif pct_show <= LOW_BATTERY_PCT:
            fill = BAT_LOW
        elif pct_show < 60:
            fill = BAT_MID
        else:
            fill = BAT_GOOD

        # 左上状态标签（参考图：黑色小字）
        if not connected:
            label = "未连接"
        elif full:
            label = "已充满"
        elif charging:
            label = "充电中"
        else:
            label = "DS4"
        c.create_text(14, 8, text=label, anchor="w",
                      font=("Segoe UI", 11, "bold"), fill="#111827")

        # 底部进度条：浅灰轨道 + 彩色填充（长度随电量，颜色随电量）
        px1, px2, py1, py2 = 12, BAR_W - 12, 30, 46
        round_rect(c, px1, py1, px2, py2, 8, fill="#E5E7EB", outline="")
        if pct_show is not None:
            fw = (px2 - px1) * pct_show / 100
            if fw > 0:
                round_rect(c, px1, py1, px1 + fw, py2, 8,
                           fill=fill, outline="")

        # 百分比：水平居中、垂直居中于进度条（与电量条重叠）
        txt = "--" if pct_show is None else f"{pct_show}%"
        c.create_text(BAR_W // 2, py1 + (py2 - py1) // 2, text=txt,
                      anchor="center", font=("Segoe UI", 18, "bold"),
                      fill="#111827")

    def update_bar(self, percent, charging=False, full=False, connected=True):
        """横条可见时更新内容；数据没变则不重绘。"""
        if not self.bar_visible:
            return
        key = (percent, charging, full, connected)
        if key == self.bar_last_key:
            return
        self.bar_last_key = key
        self.draw_bar(percent, charging, full, connected)

    def toggle_bar(self):
        """组合键切换顶部横条显示/隐藏。"""
        self.bar_visible = not self.bar_visible
        log(f"电量横条 {'显示' if self.bar_visible else '隐藏'}")
        if self.bar_visible:
            self.bar_last_key = None
            self.bar_win.deiconify()
            self.bar_win.attributes("-topmost", True)
            self.bar_win.lift()
            # 立即读一次电量填充横条
            threading.Thread(target=self._battery_worker, args=("bar",),
                             daemon=True).start()
        else:
            self.bar_win.withdraw()

    # ---------- 显隐动画 ----------
    def _set_alpha(self, a):
        self.alpha = max(0.0, min(1.0, a))
        self.root.attributes("-alpha", self.alpha)

    def _cancel_anim(self):
        if self.anim_job:
            self.root.after_cancel(self.anim_job)
            self.anim_job = None

    def _present(self, hold_seconds):
        """进入显示状态并调度淡出；已在显示时仅重置计时。"""
        self._cancel_anim()
        if self.timer_job:
            self.root.after_cancel(self.timer_job)
            self.timer_job = None
        if self.state != "shown":
            self.state = "shown"
            self.root.deiconify()
            self.root.attributes("-topmost", True)   # 始终保持最前
            self.root.lift()
            self._set_alpha(0.0)
            step = FADE_IN_MS / 10
            cur = [0.0]

            def fade_in():
                cur[0] += 0.1
                if cur[0] >= 1.0:
                    self._set_alpha(1.0)
                else:
                    self._set_alpha(cur[0])
                    self.anim_job = self.root.after(int(step), fade_in)
            fade_in()
        self.timer_job = self.root.after(int(hold_seconds * 1000), self.fade_out)

    def show_battery(self, percent, charging=False, full=False):
        """弹出电量窗；低电量时红色高亮并停留更久。"""
        self.draw_battery(percent, charging, full)
        low = percent is not None and percent <= LOW_BATTERY_PCT
        log(f"弹出电量窗 pct={percent} charging={charging} full={full} "
            f"hold={'低电量8s' if low else '5s'}")
        self._present(HOLD_LOW_SECONDS if low else HOLD_SECONDS)

    def show_disconnect(self):
        """弹出断开提示。"""
        self.draw_message("手柄已断开", "DS4")
        log("弹出断开提示窗")
        self._present(HOLD_DISCONNECT_SECONDS)

    def fade_out(self):
        if self.state != "shown":
            return
        self._cancel_anim()
        self.state = "fading"
        step = FADE_OUT_MS / 10
        cur = [self.alpha]

        def fade():
            cur[0] -= 0.1
            if cur[0] <= 0.0:
                self._set_alpha(0.0)
                self.root.withdraw()
                self.state = "hidden"
            else:
                self._set_alpha(cur[0])
                self.anim_job = self.root.after(int(step), fade)
        fade()

    def hide_now(self):
        """手柄拔出时立即隐藏。"""
        self._cancel_anim()
        if self.timer_job:
            self.root.after_cancel(self.timer_job)
            self.timer_job = None
        self._set_alpha(0.0)
        self.root.withdraw()
        self.state = "hidden"

    # ---------- 接入检测 ----------
    def on_connect(self):
        log("手柄接入 -> 读取电量")
        threading.Thread(target=self._battery_worker, args=("plug",),
                         daemon=True).start()

    def _battery_worker(self, reason="plug"):
        try:
            info = read_ds4_status()
            if info is None:
                log(f"电量读取失败(reason={reason}) -> 弹窗显示 --%")
                self.result_q.put({"kind": "battery", "pct": None,
                                   "reason": reason})
            elif reason == "lowcheck":
                # 例行检查只在"状态有变化"或"低电量"时写日志，避免刷屏
                note = (info["pct"], info["charging"], info["full"])
                if note != self._last_lowcheck or info["pct"] <= LOW_BATTERY_PCT:
                    log(f"电量读取(reason={reason}) -> {info}")
                    self._last_lowcheck = note
                self.result_q.put({"kind": "battery", "reason": reason,
                                   **info})
            else:
                log(f"电量读取(reason={reason}) -> {info}")
                self.result_q.put({"kind": "battery", "reason": reason,
                                   **info})
        except Exception:
            log("battery_worker 异常:\n" + traceback.format_exc())

    # ---------- PS 键监听（常驻读取） ----------
    def ps_handler(self, data):
        """pywinusb 回调线程执行。

        · PS 双击（500ms 内两次按下）→ 弹出电量窗
        · 十字键下 + PS 组合键 → 切换顶部电量横条
        """
        try:
            offs = report_offsets(data)
            if offs is None:
                return
            if data[0] == 0x01 and self.watch_dev is not None and \
                    is_bt_device(self.watch_dev):
                return  # 蓝牙设备激活前的位置报告(0x01)无按键，忽略
            _, psi = offs
            if len(data) <= psi:
                return
            ps = bool(data[psi] & PS_BUTTON_MASK)
            if ps and not self.ps_prev:          # PS 上升沿
                if dpad_down(data):
                    # 组合键：十字键下 + PS → 切换横条
                    log("组合键(十字键下+PS) -> 切换电量横条")
                    self.result_q.put({"kind": "toggle_bar"})
                    self.last_ps_time = None      # 不计入双击判定
                else:
                    now = time.monotonic()
                    if self.last_ps_time is not None and \
                            (now - self.last_ps_time) * 1000 <= DOUBLE_PRESS_MS:
                        # 双击 PS → 弹电量
                        log("PS 双击 -> 弹出电量")
                        self.last_ps_time = None
                        bi, _ = offs
                        if len(data) > bi:
                            if data[0] == 0x11:
                                maybe_dump_bt_report(data)
                                info = decode_bt_report(data, bi)
                            else:
                                info = decode_status(data[bi])
                            self.result_q.put({"kind": "battery",
                                               "reason": "ps", **info})
                        else:
                            self.result_q.put({"kind": "battery", "pct": None,
                                               "reason": "ps"})
                    else:
                        # 第一次按下，等双击
                        self.last_ps_time = now
            self.ps_prev = ps
        except Exception:
            log("ps_handler 异常:\n" + traceback.format_exc())

    def close_watcher(self):
        if self.watch_dev is not None:
            try:
                self.watch_dev.close()
            except Exception:
                pass
            self.watch_dev = None
            self.ps_prev = False

    def _watcher_alive(self):
        """监听句柄是否仍健康。

        pywinusb 的 is_opened() 只是内部标志，拔线后不会自动变 False；
        但内部读取线程在设备断开时（错误 1167）会退出，is_active() 变 False，
        用它作为"手柄还在不在"的可靠信号。
        """
        dev = self.watch_dev
        if dev is None:
            return False
        try:
            if not dev.is_opened():
                return False
            reader = getattr(dev, "_HidDevice__reading_thread", None)
            if reader is not None and hasattr(reader, "is_active"):
                return bool(reader.is_active())
            return True
        except Exception:
            return False

    def ensure_watcher(self):
        """维持一个常开手柄句柄，用于监听 PS 键；设备拔出/重插时自动重开。"""
        devices = find_ds4_devices()
        paths = {d.device_path for d in devices}
        if self.watch_dev is not None:
            if self.watch_dev.device_path in paths and self._watcher_alive():
                return
            # 路径对不上，或句柄已失效（快速拔插漏检）→ 重开
            log("监听句柄失效，重开手柄句柄")
            self.close_watcher()
        if not devices:
            return
        dev = devices[0]
        try:
            dev.set_raw_data_handler(self.ps_handler)
            dev.open()
            if dev.is_opened():
                if is_bt_device(dev):
                    activate_bt_full_report(dev)
                self.watch_dev = dev
                self.ps_prev = False
        except Exception:
            log("ensure_watcher 打开失败:\n" + traceback.format_exc())

    def poll_loop(self):
        """轮询主循环：任何异常都记录日志并继续调度，绝不静默停摆。"""
        try:
            self._poll_tick()
        except Exception:
            log("poll_loop 异常:\n" + traceback.format_exc())
        finally:
            self.root.after(POLL_MS, self.poll_loop)

    def _poll_tick(self):
        # 先处理队列消息（主线程，tkinter 线程安全）
        try:
            while True:
                self._dispatch(self.result_q.get_nowait())
        except queue.Empty:
            pass

        try:
            connected = len(find_ds4_devices()) > 0
        except Exception:
            connected = False

        if self.first_poll:
            # 启动时手柄已连接：也弹一次
            self.first_poll = False
            self.prev_connected = connected
            if connected:
                self.on_connect()
        else:
            if connected and not self.prev_connected:
                self.on_connect()      # 刚插入/刚连接
            elif not connected and self.prev_connected:
                # 刚拔出/断开 → 弹出断开提示，并立即释放失效句柄
                log("手柄拔出 -> 弹出断开提示")
                self.result_q.put({"kind": "disconnect"})
                self.low_warned = False
                self.close_watcher()
        self.prev_connected = connected

        # 快速拔插兜底：1 秒轮询可能漏掉瞬时断开，此时连接状态仍是 True，
        # 但监听句柄的读取线程已退出 → 判定为"重插"，重新弹电量并重开句柄
        if connected:
            if self.watch_dev is not None and not self._watcher_alive():
                log("检测到手柄重插(监听句柄失效) -> 重新弹电量")
                self.close_watcher()
                self.on_connect()

        # 低电量周期检查（约每 30 秒一次，避免过度打扰）
        self.poll_count = (self.poll_count + 1) % LOW_CHECK_INTERVAL_POLLS
        if connected and self.poll_count == 0:
            threading.Thread(target=self._battery_worker,
                             args=("lowcheck",), daemon=True).start()

        # 横条实时刷新（显示时每 5 秒读一次电量）
        if self.bar_visible and self.poll_count % BAR_REFRESH_POLLS == 0:
            threading.Thread(target=self._battery_worker,
                             args=("bar",), daemon=True).start()

        # 维持 PS 键监听句柄
        try:
            self.ensure_watcher()
        except Exception:
            log("ensure_watcher 异常:\n" + traceback.format_exc())

    def _dispatch(self, payload):
        if payload.get("kind") == "toggle_bar":
            self.toggle_bar()
            return
        if payload.get("kind") == "disconnect":
            self.show_disconnect()
            self.update_bar(None, connected=False)
            return
        pct = payload.get("pct")
        reason = payload.get("reason", "plug")
        if reason == "bar":
            # 横条刷新：只更新横条，不弹窗
            self.update_bar(pct, payload.get("charging", False),
                            payload.get("full", False))
            return
        if reason == "lowcheck":
            # 周期检查：仅当跨越低电量阈值时提示一次，避免反复打扰
            if pct is None:
                return
            if pct <= LOW_BATTERY_PCT and not self.low_warned:
                self.low_warned = True
                self.show_battery(pct, payload.get("charging", False),
                                  payload.get("full", False))
            elif pct > LOW_BATTERY_PCT:
                self.low_warned = False
        else:
            if pct is not None and pct <= LOW_BATTERY_PCT:
                self.low_warned = True
            self.show_battery(pct, payload.get("charging", False),
                              payload.get("full", False))
        # 顺带刷新横条（接入/PS 读取的同一帧数据）
        self.update_bar(pct, payload.get("charging", False),
                        payload.get("full", False))


AUTOSTART_NAME = "DS4BatteryOverlay"
AUTOSTART_RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"

_MUTEX_HANDLE = None


def _acquire_single_instance():
    """全局互斥：保证只有一个实例在运行，防止重复弹窗。"""
    global _MUTEX_HANDLE
    try:
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        _MUTEX_HANDLE = kernel32.CreateMutexW(None, False,
                                              "DS4BatteryOverlayMutex")
        return ctypes.get_last_error() != 183   # ERROR_ALREADY_EXISTS
    except Exception:
        return True


def autostart_command():
    """开机自启命令：开发模式用 pythonw 无窗口运行脚本；打包后直接运行 exe。"""
    if getattr(sys, "frozen", False):
        return f'"{sys.executable}"'
    exe = sys.executable
    if exe.lower().endswith("python.exe"):
        exe = exe[:-len("python.exe")] + "pythonw.exe"
    return f'"{exe}" "{os.path.abspath(__file__)}"'


def install_autostart():
    """写入 HKCU 启动项注册表，实现开机自启。"""
    import winreg
    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, AUTOSTART_RUN_KEY, 0,
                        winreg.KEY_SET_VALUE) as key:
        winreg.SetValueEx(key, AUTOSTART_NAME, 0, winreg.REG_SZ,
                          autostart_command())
    print("已开启开机自启：")
    print("   ", autostart_command())


def remove_autostart():
    """删除 HKCU 启动项注册表。"""
    import winreg
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, AUTOSTART_RUN_KEY, 0,
                            winreg.KEY_SET_VALUE) as key:
            winreg.DeleteValue(key, AUTOSTART_NAME)
        print("已取消开机自启")
    except FileNotFoundError:
        print("开机自启原本未开启")


def main():
    if "--autostart" in sys.argv:
        install_autostart()
        return
    if "--no-autostart" in sys.argv:
        remove_autostart()
        return

    # 单实例保护：已有实例在运行时本次启动直接退出
    if not _acquire_single_instance():
        log("检测到已有实例在运行，本次启动退出")
        sys.exit(0)

    # DPI 感知，保证文字清晰
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(1)
    except Exception:
        pass

    overlay = BatteryOverlay()
    log(f"程序启动 pid={os.getpid()}")

    if "--preview" in sys.argv:
        pct = None
        try:
            i = sys.argv.index("--preview")
            if i + 1 < len(sys.argv):
                pct = int(sys.argv[i + 1])
        except ValueError:
            pct = None
        overlay.root.after(300, lambda: overlay.show_battery(pct, False, False))

    if "--preview-bar" in sys.argv:
        pct = None
        try:
            i = sys.argv.index("--preview-bar")
            if i + 1 < len(sys.argv):
                pct = int(sys.argv[i + 1])
        except ValueError:
            pct = None

        def _preview_bar():
            overlay.bar_visible = True
            overlay.bar_last_key = None
            overlay.bar_win.deiconify()
            overlay.bar_win.lift()
            overlay.draw_bar(pct, False, False)
        overlay.root.after(300, _preview_bar)

    overlay.root.mainloop()


if __name__ == "__main__":
    main()
