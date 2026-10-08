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

import collections
import ctypes
import faulthandler
import os
import queue
import sys
import threading
import time
import traceback
import tkinter as tk
import tkinter.font as tkfont

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
BT_BATTERY_INDEX = 32                  # 电量状态字节（蓝牙 0x11 完整报告，= USB byte30 + 蓝牙头 2 字节）
PS_BUTTON_INDEX = 7                    # PS 按键所在字节（USB 0x01 报告）
PS_BUTTON_MASK = 0x01                  # PS 按键掩码（bit0）
DPAD_INDEX = 5                         # 十字键所在字节（USB 0x01 报告）
POV_DOWN = 4                           # 十字键"下"的 POV 值（8=未按，0=上，4=下）
DOUBLE_PRESS_MS = 500                  # PS 双击判定窗口（毫秒）
BT_HEADER_EXTRA = 2                    # 蓝牙(0x11)报告头部比 USB(0x01) 多 2 字节（0xc0 0x00），按键等偏移 +2
# 蓝牙 DS4 激活：设备默认只发 0x01 位置报告（仅摇杆，无按键无电量）。
# 读取 FEATURE report 0x02（校准数据）后，设备才切换到 0x11 完整报告
# （电量在 byte32，与 Linux hid-sony 驱动一致）。发送 0x11 输出报告无法触发切换（实测无效）。
BT_ACTIVATE_LENS = (79, 547)           # 兜底：0x11 输出报告候选长度（实测主方案不依赖此）
BT_ACTIVATE_LED = 0xFF                 # 兜底激活配置的 LED R（红色）

HOLD_SECONDS = 3.0                     # 电量显示保持时间（秒）
HOLD_PS_SECONDS = 2.0                  # PS 双击弹电量窗保持时间（秒）
HOLD_LOW_SECONDS = 3.0                 # 低电量提示保持时间（秒）
HOLD_DISCONNECT_SECONDS = 2.5          # 拔出提示保持时间（秒）
HOLD_POWER_SECONDS = 1.5              # 接入/拔出电源提示保持时间（秒）
LOW_BATTERY_PCT = 20                   # 低电量阈值（%）
# ---- 防过充 ----
# 物理前提：手柄插上 USB 后充电由硬件直连，软件无法切断充电电路，
# 因此"防过充"实现为：带电达到阈值时主动提醒拔线（可关闭 / 可改阈值）。
OVERCHARGE_DEFAULT_PCT = 90            # 达到该电量即提醒拔线（%）
LOW_CHECK_INTERVAL_POLLS = 30          # 低电量周期检查（每 30 次轮询 ≈ 30 秒）
FADE_IN_MS = 150                       # 淡入总时长（毫秒；与淡出合计 0.5 秒）
FADE_OUT_MS = 350                      # 淡出总时长（毫秒；与淡入合计 0.5 秒）
POLL_MS = 1000                         # 手柄接入检测轮询间隔（毫秒）
READ_TIMEOUT = 2.0                     # 读取电量超时（秒）
QUICK_TIMEOUT = 1.2                    # 横条刷新等"要跟手"的场景用更短等待（秒）

# ---- 与屏幕共享/语音开黑软件（黑盒语音、Sunshine、OBS 等）共存相关的参数 ----
# 这类软件会同时枚举/占用 DS4 的 HID 接口，导致：
#   · HID 枚举(setupapi)在主线程上长时间阻塞 → tkinter 假死
#   · 常驻句柄的读取线程虽仍 alive，但系统调用已被卡住 → PS 键/电量再也不触发
# 因此：所有 HID 枚举都放到后台线程；用 is_plugged() 主动探测句柄健康；
# 连续失败时指数退避，避免与共享软件互相抢设备形成风暴。
DEV_POLL_SEC = 1.0                     # 后台手柄连接检测周期（秒）
DEV_POLL_IDLE_SEC = 5.0                # 未连接时的降频探测间隔（秒，省 CPU）
RES_SAMPLE_SEC = 300.0                 # 资源占用采样/写日志间隔（秒）
MEM_LIMIT_MB = 250.0                   # 内存超过此值视为异常增长 → 自愈重启（MB）
WATCH_PROBE_SEC = 5.0                  # 常驻句柄健康探测周期（秒）
WATCH_QUIET_SEC = 45.0                 # 有报告时的静默上限；超时强制重开（秒）
WATCH_OPEN_TIMEOUT_SEC = 8.0           # 单次打开句柄的时限；超时视为卡住并放弃该次（秒）
WATCH_OPEN_HANG_COOLDOWN_SEC = 60.0    # 打开超时后的全局冷却：期间不再尝试，防卡死线程堆积（秒）
WATCH_FAIL_BACKOFF_BASE = 3.0          # 打开失败退避基数（秒）：3·2^(n-1)
WATCH_FAIL_BACKOFF_MAX = 60.0          # 退避上限（秒）
ACTIVE_WORKERS_MAX = 2                 # 同时运行的 HID 读取工作线程上限（防线程爆炸）
BURST_WINDOW_SEC = 1.5                 # 同一类提示在此时长内只响应一次（防触发风暴）

# 顶部电量横条（组合键：十字键下 + PS 切换显示）
BAR_W = 450                            # 横条宽度
BAR_H = 40                             # 横条高度：圆角胶囊外框 + 左上标签 + 8px 进度条
BAR_REFRESH_POLLS = 2                  # 横条显示时每 2 秒刷新一次（更跟手）
BAR_TOP_MARGIN = 8                     # 距屏幕顶部
BAR_RADIUS = 19                        # 横条左右两端圆角半径（约等于高度的一半）
BAR_PAD = 1                            # 横条外轮廓与窗口边缘的留白

# 横条配色（比弹窗更亮，保证叠在任何壁纸上都看得清）
BAR_LABEL_BG = "#111827"               # 状态标签底色
BAR_LABEL_FG = "#F9FAFB"               # 状态标签文字
BAR_TRACK = "#E9EDF3"                  # 进度条轨道（浅灰）
BAR_TEXT = "#0B1220"                   # 百分比数字
BAR_TEXT_HALO = "#FFFFFF"              # 数字描边（浅色描边提升可读性）

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

# ---- 版本号：全项目唯一来源 ----
# 发布脚本、面板、管理程序都从这里/各自同名常量读取，避免各处版本号不一致。
# 升级版本时只改这一处（以及 ds4_manager.py / ds4_battery_overlay_panel.py 的同名常量）。
__version__ = "1.2.8"
APP_NAME = "DS4 电量提示"

W, H = 340, 90

# 程序目录：PyInstaller 打包后 __file__ 指向临时解压目录，改用 exe 所在目录
if getattr(sys, "frozen", False):
    BASE_DIR = os.path.dirname(sys.executable)
else:
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))

LOG_PATH = os.path.join(BASE_DIR, "ds4_battery_overlay.log")
LOG_MAX_BYTES = 200 * 1024   # 日志体积上限 200 KB，超限自动裁剪
CRASH_PATH = os.path.join(BASE_DIR, "ds4_battery_overlay_crash.log")
LOG_KEEP_LINES = 200         # 裁剪时保留最近 200 行

# 最近一次无线（cable=0）真实电量记忆：初版 DS4 有线充电时 USB 报告
# 的电量字节会跳到 11 档（充电电压满刻度），无法读出真实电量，
# 用最近一次无线读数代替显示"充电中 X%"。持久化到状态文件，重启不丢。
STATE_FILE = os.path.join(BASE_DIR, "ds4_battery_state.json")
CONFIG_FILE = os.path.join(BASE_DIR, "ds4_config.json")   # 防过充等设置
NOMINAL_MAH = 1000                     # DS4 标称电池容量（mAh），用于换算容量估算
_last_wireless_pct = None
_last_save_ts = 0.0       # 状态文件写入限频时间戳
_last_saved_pct = None    # 状态文件已保存值（去重）


def _load_state():
    """读取持久化的无线电量记忆。"""
    global _last_wireless_pct
    try:
        import json
        with open(STATE_FILE, "r", encoding="utf-8") as f:
            v = json.load(f).get("wireless_pct")
        if v is not None and 0 <= v <= 100:
            _last_wireless_pct = v
    except Exception:
        _last_wireless_pct = None


def _save_state():
    """保存无线电量记忆到状态文件。

    限频：2 秒内不重复写、值未变化不写——避免回调线程高频 I/O
    （屏幕共享/直播等场景下磁盘被占用时，写入阻塞会拖垮读取回调）。
    """
    global _last_save_ts, _last_saved_pct
    if time.time() - _last_save_ts < 2.0:
        return
    if _last_saved_pct == _last_wireless_pct:
        return
    try:
        import json
        with open(STATE_FILE, "w", encoding="utf-8") as f:
            json.dump({"wireless_pct": _last_wireless_pct}, f)
        _last_save_ts = time.time()
        _last_saved_pct = _last_wireless_pct
    except Exception:
        pass


INFO_FILE = os.path.join(BASE_DIR, "ds4_battery_info.json")


def _save_config(cfg):
    try:
        import json
        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(cfg, f, ensure_ascii=False, indent=2)
        return True
    except Exception:
        return False


def _load_config():
    """读取配置（防过充开关/阈值等）。文件不存在时用默认值并落盘。"""
    import json
    cfg = {"overcharge_enabled": True, "overcharge_pct": OVERCHARGE_DEFAULT_PCT}
    try:
        with open(CONFIG_FILE, "r", encoding="utf-8") as f:
            cfg.update(json.load(f) or {})
    except Exception:
        try:
            _save_config(cfg)     # 首启用默认值生成文件，便于面板读写
        except Exception:
            pass
    return cfg


# 启动时载入一次；改配置需重启常驻程序生效（面板会提示）
_cfg = _load_config()
OVERCHARGE_ENABLED = bool(_cfg.get("overcharge_enabled", True))
OVERCHARGE_PCT = int(_cfg.get("overcharge_pct") or OVERCHARGE_DEFAULT_PCT)


def _fmt_minutes(minutes):
    """把分钟数格式化为"约 X 小时 Y 分钟"。"""
    if minutes is None:
        return None
    m = int(round(minutes))
    if m < 1:
        return "不到 1 分钟"
    if m < 60:
        return "约 %d 分钟" % m
    return "约 %d 小时 %d 分钟" % (m // 60, m % 60)


class UsageEstimator:
    """按历史读数估算「还能用多久」与「还要充多久」。

    现实约束（必须诚实处理）：
      · DS4 只按 **10% 一档**上报电量，单次跳变就是 10 个百分点；
      · 因此速率只有在累计跨过至少一档（≥10%）之后才有意义，
        否则会把测量噪声放大成荒谬的估计；
      · 数据不足时返回 None，界面显示"估算中"，绝不编造数字。
    """

    MIN_SPAN_MIN = 0.5      # 两个样本至少间隔 30 秒
    MIN_DELTA_PCT = 8       # 至少变化 8 个百分点（约 1 档量化步长）
    MAX_AGE_MIN = 180.0     # 只保留最近 3 小时的样本
    CACHE_MIN = 3           # 样本少于这么多时也允许估算（只要首尾差异够）

    def __init__(self):
        self.discharge = []   # [(time, pct)] 放电样本
        self.charge = []      # [(time, pct)] 充电样本

    @staticmethod
    def _pair(samples):
        if len(samples) < 2:
            return None
        (t0, p0), (t1, p1) = samples[0], samples[-1]
        span = (t1 - t0) / 60.0
        if span < UsageEstimator.MIN_SPAN_MIN:
            return None
        if abs(p1 - p0) >= UsageEstimator.MIN_DELTA_PCT:
            return (p0, t0), (p1, t1), span
        return None

    def _trend(self, samples, rising):
        """返回 (当前pct, 每分钟变化率)；数据不足返回 None。"""
        pair = self._pair(samples)
        if pair is None:
            return None
        (p0, _t0), (p1, _t1), span = pair
        rate = (p1 - p0) / span
        if rising and rate <= 0.2:
            return None
        if (not rising) and rate >= -0.2:
            return None
        return p1, rate

    def update(self, pct, charging, cable):
        """喂入一次读数；返回本次是否产生了有意义的变化。"""
        if pct is None:
            return False
        now = time.time()
        bucket = self.charge if (charging or cable) else self.discharge
        other = self.discharge if bucket is self.charge else self.charge
        # 只在档位变化时记录，避免同一档内反复刷样本
        if not bucket or bucket[-1][1] != pct:
            bucket.append((now, pct))
        cutoff = now - self.MAX_AGE_MIN * 60
        for lst in (bucket, other):
            while len(lst) > 1 and lst[0][0] < cutoff:
                lst.pop(0)
        return True

    def remaining_text(self, current_pct=None):
        """还能用多久（放电趋势）。

        插着线时放电样本不再更新，此时用**最近一次的放电速率**配合当前电量
        继续给出估算（并标注为"按上次无线速率"），避免插线后就看不到续航。
        """
        tr = self._trend(self.discharge, rising=False)
        self._used_cache = False
        if tr is not None:
            pct, rate = tr
            self._last_rate = rate          # 记住速率供插线时复用
            self._last_rate_ts = time.time()
            base = current_pct if current_pct is not None else pct
            if base and base > 0:
                return _fmt_minutes(base / abs(rate))
            return None
        # 没有新样本：用缓存的放电速率 + 当前电量推算
        rate = getattr(self, "_last_rate", None)
        if rate is None or current_pct is None or current_pct <= 0:
            return None
        if time.time() - getattr(self, "_last_rate_ts", 0) > self.MAX_AGE_MIN * 60:
            return None
        self._used_cache = True
        return _fmt_minutes(current_pct / abs(rate))

    def remaining_is_cached(self):
        """当前续航是否为"按上次无线速率推算"（插线状态）。"""
        return getattr(self, "_used_cache", False)

    def full_text(self, current_pct):
        """还要多久充满（充电趋势）。"""
        tr = self._trend(self.charge, rising=True)
        if tr is None:
            return None
        pct, rate = tr
        if pct >= 100:
            return "已充满"
        return _fmt_minutes((100 - pct) / rate)

    def note(self, remaining=None, full=None):
        """给界面的简短说明：只有两个估算都拿不到时才提示需要累积数据。"""
        if remaining is None and full is None:
            return "估算中（手柄按 10% 一档上报，需累积到跨档才能算速率）"
        return None


_estimator = UsageEstimator()


def _write_info(info):
    """把最近一次电池详情落盘，供控制面板"电池详情"读取。

    DS4 硬件只按 10% 一档上报百分比，也不提供 mAh 容量/健康度，
    因此这里只记录可实测的真实数据（含原始档位，便于看出量化精度）。
    """
    try:
        import json
        payload = dict(info)
        payload["raw_level"] = info.get("level")
        payload["nominal_mah"] = NOMINAL_MAH
        payload["capacity_mah"] = round(
            NOMINAL_MAH * (info.get("pct") or 0) / 100.0, 1)
        # 时长估算：喂样本后取结果（数据不足时该字段为 None，界面显示"估算中"）
        pct_now = info.get("pct")
        _estimator.update(pct_now, bool(info.get("charging")),
                          bool(info.get("cable")))
        rem = _estimator.remaining_text(pct_now)
        full = _estimator.full_text(pct_now)
        payload["est_remaining"] = rem
        payload["est_full"] = full
        # 插线时续航是按上次无线速率推算的，界面据此加一句说明
        payload["est_remaining_cached"] = bool(rem and _estimator.remaining_is_cached())
        payload["est_note"] = _estimator.note(rem, full)
        payload["updated"] = time.strftime("%Y-%m-%d %H:%M:%S")
        with open(INFO_FILE, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False)
    except Exception:
        pass


def _remember_wireless(pct):
    """记录真实电量（无线读数，或有线档位 0-10 的充电进度）。"""
    global _last_wireless_pct
    if pct is None or not (0 <= pct <= 100):
        return
    _last_wireless_pct = pct
    _save_state()


def _trim_log(path):
    """日志超限时只保留最近几行。

    只读一次、一次性重写，并且只在真正超限时才触发（见 log()）。
    旧实现每次写日志都要先读整个文件再统计大小，属于 O(文件大小) 的额外
    I/O，长跑时是持续开销。
    """
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            lines = f.readlines()
        with open(path, "w", encoding="utf-8", errors="replace") as f:
            f.writelines(lines[-LOG_KEEP_LINES:])
    except Exception:
        pass


_pmc_cls = None


def _read_proc_stats():
    """读取自身进程的 (内存MB, 句柄数)。

    坑：ctypes 调用这两个 API **必须声明 argtypes**——否则 64 位进程句柄会被
    按 32 位 int 传递（甚至截断），调用会静默返回 0、读不到任何数据。
    取不到时返回 (None, None)，绝不影响主流程。
    """
    global _pmc_cls
    try:
        class _PMC(ctypes.Structure):
            _fields_ = [("cb", ctypes.c_ulong),
                        ("PageFaultCount", ctypes.c_ulong),
                        ("PeakWorkingSetSize", ctypes.c_size_t),
                        ("WorkingSetSize", ctypes.c_size_t),
                        ("QuotaPeakPagedPoolUsage", ctypes.c_size_t),
                        ("QuotaPagedPoolUsage", ctypes.c_size_t),
                        ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t),
                        ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
                        ("PagefileUsage", ctypes.c_size_t),
                        ("PeakPagefileUsage", ctypes.c_size_t)]

        k32 = ctypes.WinDLL("kernel32", use_last_error=True)
        psapi = ctypes.WinDLL("psapi", use_last_error=True)
        psapi.GetProcessMemoryInfo.argtypes = [ctypes.c_void_p,
                                               ctypes.POINTER(_PMC),
                                               ctypes.c_ulong]
        psapi.GetProcessMemoryInfo.restype = ctypes.c_int
        k32.GetProcessHandleCount.argtypes = [ctypes.c_void_p,
                                              ctypes.POINTER(ctypes.c_ulong)]
        k32.GetProcessHandleCount.restype = ctypes.c_int
        hproc = ctypes.c_void_p(k32.GetCurrentProcess())
        pmc = _PMC()
        pmc.cb = ctypes.sizeof(pmc)
        mem_mb = None
        if psapi.GetProcessMemoryInfo(hproc, ctypes.byref(pmc), pmc.cb):
            mem_mb = pmc.WorkingSetSize / 1048576.0
        cnt = ctypes.c_ulong(0)
        handles = int(cnt.value) if k32.GetProcessHandleCount(
            hproc, ctypes.byref(cnt)) else None
        return mem_mb, handles
    except Exception:
        return None, None


_log_lock = threading.Lock()
_log_size = None


def _maybe_register_faulthandler():
    """注册原生崩溃转储：C 层崩溃（如 HID/dll 段错误）会留下 Python 堆栈，
    这是"防止使用时崩溃"最重要的证据来源——否则进程直接消失、什么都没有。
    """
    if getattr(_maybe_register_faulthandler, "_done", False):
        return
    _maybe_register_faulthandler._done = True
    try:
        f = open(CRASH_PATH, "a", encoding="utf-8", errors="replace")
        faulthandler.enable(file=f, all_threads=True)
    except Exception:
        pass


def log(msg):
    """写运行日志到程序同目录，便于无控制台(pythonw)时排查问题。

    性能要点（旧实现每次调用都要 stat + 打开文件，超限时还要读整个文件）：
      · 文件大小用内存计数器维护，避免每次都 stat；
      · 只在计数器显示超限时才做裁剪；
      · 单次 append 写入后立即关闭——不长期占用文件句柄，
        这样程序运行时用户/工具依然能直接读取日志。
    """
    global _log_size
    try:
        with _log_lock:
            if _log_size is None:
                try:
                    _log_size = os.path.getsize(LOG_PATH)
                except OSError:
                    _log_size = 0
            if _log_size > LOG_MAX_BYTES:
                _trim_log(LOG_PATH)
                try:
                    _log_size = os.path.getsize(LOG_PATH)
                except OSError:
                    _log_size = 0
            line = "[%s] %s\n" % (time.strftime("%Y-%m-%d %H:%M:%S"), msg)
            with open(LOG_PATH, "a", encoding="utf-8") as f:
                f.write(line)
            _log_size += len(line.encode("utf-8", "replace"))
    except Exception:
        pass


_bar_font_cache = {}


def _bar_font(size, weight="bold"):
    """缓存字体对象：tkfont.Font 每次构造都有开销，横条刷新频繁需复用。"""
    key = (int(size), weight)
    f = _bar_font_cache.get(key)
    if f is None:
        f = tkfont.Font(font=("Segoe UI", int(size), weight))
        _bar_font_cache[key] = f
    return f


def _lighten(hex_color, amount=0.55):
    """把颜色按比例向白色混入，得到同色系的浅色底（用作进度条填充）。"""
    try:
        h = hex_color.lstrip("#")
        r, g, b = (int(h[i:i + 2], 16) for i in (0, 2, 4))
        r = int(r + (255 - r) * amount)
        g = int(g + (255 - g) * amount)
        b = int(b + (255 - b) * amount)
        return "#%02X%02X%02X" % (r, g, b)
    except Exception:
        return hex_color


def round_rect_points(x1, y1, x2, y2, r):
    """圆角矩形（胶囊）的顶点序列。

    单独抽出来是为了"原地更新"：Tk 的 coords() 是按点替换的，
    若只传 4 个数值给一个 24 点多边形，多边形会被解释成
    (x1,y1,x2,y2) 四点、塌缩成一条线——填充条会整个消失。
    所以更新时必须重算整组点。
    """
    return [x1 + r, y1, x2 - r, y1, x2, y1, x2, y1 + r,
            x2, y2 - r, x2, y2, x2 - r, y2, x1 + r, y2,
            x1, y2, x1, y2 - r, x1, y1 + r, x1, y1]


def round_rect(canvas, x1, y1, x2, y2, r, **kw):
    """在 canvas 上画一个圆角矩形（pill 形）。"""
    return canvas.create_polygon(round_rect_points(x1, y1, x2, y2, r),
                                 smooth=True, **kw)


def find_ds4_devices():
    """枚举当前接入的 DS4 设备列表。

    蓝牙接口优先返回：初版 DS4（PID 09CC）充电时，USB 接口的电量字节
    会跳到 11 档（充电电压满刻度假象，易误判为 100%），而蓝牙接口的
    byte32 报真实电量（无线/插电均准确）。纯 USB 连接时仍只有 USB 接口。
    """
    try:
        devices = hid.HidDeviceFilter(vendor_id=DS4_VID).get_devices()
    except Exception:
        return []
    ds = [d for d in devices if d.product_id in DS4_PIDS]
    return sorted(ds, key=lambda d: not is_bt_device(d))


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

    USB(0x01) 报告 byte30：
      · 有线充电中（bit4=1）：档位 0-10 → 档×10 为真实充电进度；
        档位 11-15 为初版 DS4（PID 09CC）充电电压满刻度假象（真实电量
        不可读），此时用最近一次无线记忆电量显示"充电中"。
      · 充满（bit4=0 且档位 ≥ 11）：100% 已充满。
      · 无线（bit4=0 且档位 0-9）：(档位+1)×10。
    蓝牙(0x11) 报告 byte32（= USB byte30 + 2 字节蓝牙头，与 Linux
    hid-sony 驱动一致）：bit3-0 = 电量档位，bit4 = USB 线缆状态。
      · 插电：档位 0-10，档×10；档位 ≥ 10 即充满
      · 无线：档位 0-9，电量为 (档位+1)×10（档 9 = 100%）
    """
    level = status & 0x0F
    cable = bool(status & 0x10)
    if is_bt:
        if cable:
            charging = level <= 10
            pct = 100 if level >= 10 else level * 10
        else:
            charging = False
            pct = (level + 1) * 10
        pct = min(100, pct)
        full = cable and pct >= 100
        return {"pct": pct, "cable": cable, "level": level,
                "charging": charging, "full": full,
                "overcharge": bool(cable and pct >= OVERCHARGE_PCT)}
    if cable:
        if level <= 10:
            pct, charging, full = level * 10, True, False
        else:
            # 初版 DS4 有线充电：电压满刻度假象 → 用最近无线记忆电量
            pct = _last_wireless_pct if _last_wireless_pct is not None else 100
            charging, full = True, False
    else:
        if level >= 11:
            pct, charging, full = 100, False, True     # 充满
        else:
            pct = (level + 1) * 10
            charging, full = False, False
    pct = max(0, min(100, pct))
    return {"pct": pct, "cable": cable, "level": level,
            "charging": charging, "full": full,
            "overcharge": bool(cable and charging and pct >= OVERCHARGE_PCT)}


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
    （电量位于 byte32）——这是实测有效的机制，Linux hid-sony 驱动同样如此。
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


# 蓝牙报告诊断：默认每个进程只转储一次。
# 旧实现每 30 秒就打印一整行 42 字节 hex，蓝牙连接下会持续刷日志
# （实测日志里近 1/3 都是这类诊断行），纯属浪费 CPU 与磁盘。
# 排查解析问题时可用环境变量 DS4_BT_DUMP=1 恢复 30 秒限频输出。
_bt_dump_last = 0.0
_bt_dump_done = False


def maybe_dump_bt_report(data):
    """蓝牙(0x11)报告关键字节写入日志，供排查电量解析问题。"""
    global _bt_dump_last, _bt_dump_done
    if not data or data[0] != 0x11:
        return
    if os.environ.get("DS4_BT_DUMP") == "1":
        now = time.time()
        if now - _bt_dump_last < 30:
            return
        _bt_dump_last = now
    else:
        if _bt_dump_done:
            return
        _bt_dump_done = True
    hexs = " ".join("%02X" % b for b in data[:42])
    b32 = data[32] if len(data) > 32 else None
    log(f"蓝牙报告诊断: 长度={len(data)} byte32={b32:#04x} 前42字节: {hexs}")


def decode_bt_report(data, bi=BT_BATTERY_INDEX):
    """
    蓝牙(0x11)完整报告电量字节解析（电量位于 byte32）。
    返回与 decode_status 相同的结构。
    """
    raw = data[bi] if len(data) > bi else 0
    return decode_status(raw, is_bt=True)


def report_offsets(data):
    """
    返回 (电量字节偏移, PS 按键字节偏移)。
    USB(0x01) 报告：电量@30、PS@7；蓝牙(0x11) 完整报告：电量@32、PS@9。
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


_open_hang_until = 0.0   # 上次打开超时后的全局冷却截止时间（monotonic）


def _open_device_bounded(dev, timeout=WATCH_OPEN_TIMEOUT_SEC):
    """带时限地打开手柄句柄。

    屏幕共享 / 语音开黑软件同时占用手柄 HID 时，dev.open() 可能在
    CreateFile / setupapi 里长时间阻塞（实测可卡住数十秒甚至更久），
    历史上这一步会连带把 tkinter 主线程拖死。这里把打开动作放进独立
    线程并限时等待：超时即放弃，句柄标记为不健康，稍后退避重试。

    注意：Python 无法中断已陷入系统调用的线程，超时后那个线程会一直
    卡着。因此超时后进入全局冷却（冷却期内不再尝试打开），避免重试
    不断产生新的卡死线程。
    返回 True 表示在时限内打开成功。
    """
    global _open_hang_until
    if time.monotonic() < _open_hang_until:
        return False
    done = threading.Event()
    ok = []

    def worker():
        try:
            dev.open()
            ok.append(bool(dev.is_opened()))
        except Exception:
            ok.append(False)
        finally:
            done.set()

    threading.Thread(target=worker, daemon=True).start()
    if not done.wait(timeout):
        _open_hang_until = time.monotonic() + WATCH_OPEN_HANG_COOLDOWN_SEC
        log(f"打开手柄句柄超时(>{timeout:.0f}s)，判定为被占用/卡住，"
            f"进入 {WATCH_OPEN_HANG_COOLDOWN_SEC:.0f} 秒冷却")
        return False
    return bool(ok and ok[0])


def read_battery_from_device(dev):
    """
    读取 DS4 电量。
    报告格式：USB 连接时输入报告 ID 为 0x01（64 字节），蓝牙为 0x11
    （78 字节，头部多 2 字节 0xc0 0x00）。
    电量状态字节位于第 30（USB）/ 32（蓝牙完整报告）字节：
        USB: bit3-0 = 电量档位（0-10）；bit4 = 充电中；bit5 = 已充满。
        蓝牙: bit3-0 = 电量档位（电池 0-9 / 插电 0-10）；bit4 = 线缆状态（充电中）。
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
        opened = _open_device_bounded(dev)
        if opened:
            if is_bt_device(dev):
                activate_bt_full_report(dev)
            got.wait(timeout=QUICK_TIMEOUT if quick else READ_TIMEOUT)
    except Exception:
        pass
    finally:
        if opened:
            try:
                dev.close()  # close() 会停止内部读取线程
            except Exception:
                pass
    return result.get("pct")


def read_ds4_status(quick=False):
    """读取第一个可用 DS4 的电量状态（含充电/充满标志）；失败返回 None。

    quick=True 时只等 QUICK_TIMEOUT（横条刷新等"要跟手"的场景用），
    接入弹窗仍用完整 READ_TIMEOUT，避免误显示 --%。
    """
    for dev in find_ds4_devices():
        info = read_status_from_device(dev, quick=quick)
        if info is not None:
            return info
    return None


def read_status_from_device(dev, quick=False):
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
                info = decode_bt_report(data, bi)
            elif is_bt_device(dev):
                return  # 蓝牙设备激活前的位置报告(0x01)无电量，忽略
            else:
                info = decode_status(data[bi])
            # 记忆真实电量：无线读数（bit4=0），或有线档位 ≤10 的充电进度
            raw = data[bi]
            if not (raw & 0x10) or (raw & 0x0F) <= 10:
                _remember_wireless(info["pct"])
            result["info"] = info
            _write_info(info)
            got.set()
        except Exception:
            pass

    opened = False
    try:
        dev.set_raw_data_handler(handler)
        opened = _open_device_bounded(dev)
        if opened:
            if is_bt_device(dev):
                activate_bt_full_report(dev)
            got.wait(timeout=QUICK_TIMEOUT if quick else READ_TIMEOUT)
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

        # 顶部电量横条窗口：**惰性创建**——不用组合键就完全不建，
        # 省下一个常驻 Toplevel + Canvas 的内存与 Tk 开销。
        # （组合键唤出是"先上屏后刷新"，首次创建的少量开销被即时绘制掩盖）
        self.bar_win = None
        self.bar_canvas = None
        self._bar_ready = False
        self._sw, self._sh = sw, sh

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
        self.overcharge_warned = False   # 本轮是否已提示过防过充（电量回落后重置）
        self._overcharge_cooldown = 0.0  # 防过充提示冷却截止时间（单调时钟）
        self.poll_count = 0      # 低电量周期检查计数器
        self._last_lowcheck = None  # 上次例行检查的(电量,充电,充满)，用于去重日志
        self.ps_cooldown_until = 0.0  # PS 双击/组合键触发冷却（防误触发风暴）
        self._watch_retry_ts = 0.0    # 监听句柄重开退避时间戳（秒）
        self._watcher_busy = False    # 后台重开句柄进行中标志（防并发重开）
        self._open_fail_streak = 0    # 连续打开失败次数（指数退避用）
        self._longframe_log_ts = 0.0  # 长帧异常警告日志限频时间戳（秒）
        self._last_cable = None    # 蓝牙电源线状态基线（接入/拔出电源提示）
        self._last_tick = time.time() # 主循环心跳（看门狗据此判断是否假死）

        # ---- 与屏幕共享/语音软件共存用的状态 ----
        self._dev_poll_busy = False   # 后台 HID 枚举进行中（枚举被占用时会很慢）
        self._dev_state_ready = False # 后台是否已完成首次枚举（主循环据此决定基线）
        self._connected = False       # 由后台线程维护的连接状态（主线程只读缓存）
        self._last_report_ts = 0.0    # 常驻句柄最近一次收到报告的时间
        self._probe_ok_ts = 0.0       # 最近一次 is_plugged() 探测成功的时间
        self._probe_fail_streak = 0   # is_plugged() 连续失败次数
        self._reopen_log_ts = 0.0     # 句柄重开日志限频（避免刷屏）
        self._active_workers = 0      # 兼容保留（并发读取已由常驻工作线程串行化）
        self._worker_lock = threading.Lock()
        self._worker_todo = collections.deque()   # 待处理的读取任务
        self._worker_pending = set()              # 已在队列中的任务类型（去重）
        self._worker_wake = threading.Event()     # 唤醒常驻工作线程
        self._last_queued = {}        # 事件类型 -> 上次入队时间（防触发风暴）
        self.bar_last_data = None     # 横条最近一次真实数据（切换时立即上屏用）
        self.bar_last_pct = None      # 横条最近一次已知电量（跨断开保留，避免灰轨道）
        self._res_sample_ts = time.time()   # 资源自监控采样时间戳
        self._last_dev_poll = 0.0           # 上次设备枚举时间（未连接时降频用）
        self._bar_items = {}                # 横条画布元素 id 缓存（原地更新用）
        self._bar_geo = None                # 上述缓存对应的画布几何
        self._bar_layout = None             # 上述缓存对应的字号/标签宽度布局
        self._bar_draw_pending = False      # 几何未就绪时的延后重画标志

        # 看门狗线程：后台维护设备连接状态、采样资源占用，并在主循环假死
        # （屏幕共享/直播场景可能阻塞主线程）时自动重启；启动即做首次枚举
        threading.Thread(target=self._watchdog, daemon=True).start()
        # 常驻读取线程：所有 HID 读取都排在它上面串行执行，线程数恒定
        threading.Thread(target=self._worker_thread, daemon=True).start()

        self.root.after(50, self.poll_loop)   # 尽快跑首轮：接入弹窗更快出现

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
    def _ensure_bar_win(self):
        """首次需要时创建横条窗口（惰性创建，不用就不占用资源）。"""
        if self._bar_ready:
            return
        win = tk.Toplevel(self.root)
        win.overrideredirect(True)
        win.attributes("-topmost", True)
        try:
            win.attributes("-transparentcolor", MAGIC)
        except tk.TclError:
            pass
        win.geometry("%dx%d+%d+%d" % (BAR_W, BAR_H,
                                      (self._sw - BAR_W) // 2, BAR_TOP_MARGIN))
        canvas = tk.Canvas(win, width=BAR_W, height=BAR_H, bg=MAGIC,
                           highlightthickness=0)
        canvas.pack()
        # 右键点击横条 = 关闭横条
        canvas.bind("<Button-3>", lambda e: self._toggle_bar_event())
        self.bar_win = win
        self.bar_canvas = canvas
        self._bar_items = {}
        self._bar_geo = None
        self._bar_layout = None
        self._bar_ready = True

    def draw_bar(self, percent, charging=False, full=False, connected=True):
        """绘制顶部电量横条。

        美术方案：
          · 整体为左右两端圆角的胶囊形外框（圆角即"左右边缘圆角"）
          · 左上角深色胶囊标签：DS4 / 充电中 / 已充满 / 未连接
          · 中部 8px 浅灰轨道 + 同色系浅色进度填充（随电量变色）
          · 百分比数字加大加粗，绘制时带浅色描边（halo），叠在任何壁纸上都清晰
        """
        # 惰性创建（首次调用时才建窗口；测试替身可能没有该方法）
        getattr(self, "_ensure_bar_win", lambda: None)()
        c = self.bar_canvas

        # DPI 自适应：用画布**实际像素尺寸**等比换算所有坐标。
        # 关键坑：SetProcessDpiAwareness 之后，Tk 给画布分配的物理像素数会小于
        # 常量声明的逻辑尺寸（125% 缩放下 450x40 只分到约 448x26），若直接按逻辑
        # 坐标绘制，内容会被裁掉一截（表现为标签贴顶、底部被切）。
        try:
            self.bar_win.update_idletasks()   # 先结算几何，否则 winfo 返回默认值
        except Exception:
            pass
        try:
            cw = max(120, int(self.bar_win.winfo_width()))
            ch = max(20, int(self.bar_win.winfo_height()))
        except Exception:
            cw, ch = BAR_W, BAR_H
        sx, sy = cw / float(BAR_W), ch / float(BAR_H)

        # 几何未就绪时绝不绘制：Tk 刚创建/刚 deiconify 时 winfo 可能仍是 1x1
        # 或默认值，按这种尺寸换算坐标会画出错乱、重叠的图案。
        # 这里改为延后重画（窗口真正显示后必然就绪）。
        if abs(cw - BAR_W) > 12 or abs(ch - BAR_H) > 12:
            if not self._bar_draw_pending:
                self._bar_draw_pending = True

                def _retry_bar():
                    self._bar_draw_pending = False
                    if self.bar_visible:
                        self.bar_last_key = None
                        self.draw_bar(percent, charging, full, connected)

                try:
                    self.root.after(60, _retry_bar)
                except Exception:
                    self._bar_draw_pending = False
            return

        def RX(v):
            return v * sx

        def RY(v):
            return v * sy

        pct_show = None if (not connected or percent is None) \
            else max(0, min(100, int(percent)))

        # 进度条颜色随电量：≤20% 红 / 20–60% 黄 / >60% 绿；未连接浅灰
        if pct_show is None:
            accent = "#9CA3AF"
        elif pct_show <= LOW_BATTERY_PCT:
            accent = BAT_LOW
        elif pct_show < 60:
            accent = BAT_MID
        else:
            accent = BAT_GOOD

        # 2) 文字按缩放后的字号排布，避免被窗口边缘裁切
        label = ("未连接" if not connected else
                 "已充满" if full else
                 "充电中" if charging else "DS4")
        f_label = _bar_font(max(6, int(round(9 * sy))), "bold")
        f_pct = _bar_font(max(8, int(round(14 * sy))), "bold")
        lh = f_label.metrics("linespace")
        ph = f_pct.metrics("linespace")

        # 纵向排布：标签胶囊在上，百分比数字+进度条在下
        x1, y1 = BAR_PAD, BAR_PAD
        x2, y2 = BAR_W - BAR_PAD, BAR_H - BAR_PAD
        h_pill = lh + RY(2)
        cy = RY(y2 - 2) - ph / 2.0        # 数字/进度条的垂直中心
        y_pill = RY(y1 + 3)
        px1, px2 = RX(x1 + 13), RX(x2 - 13)
        py1, py2 = RY(y2 - 10), RY(y2 - 2)
        lx = RX(16)
        lw = f_label.measure(label) + RX(16)
        txt = "--%" if pct_show is None else "%d%%" % pct_show
        cx = RX(BAR_W // 2)
        fill_w = (px2 - px1) * (pct_show or 0) / 100.0
        fill_w = max(fill_w, RX(8)) if pct_show else 0.0
        bg_fill = BAR_TRACK if pct_show is None else _lighten(accent, 0.60)
        bg_line = _lighten(accent, 0.32) if pct_show is not None else "#CBD5E1"
        brad = RY(BAR_RADIUS - BAR_PAD)

        # 3) 复用策略：几何/字号/标签宽度任一变化，就整幅重建；其余情况原地更新。
        #    这样不会出现"部分元素更新、部分还是旧的"造成的错乱与重叠。
        it = self._bar_items
        geo = (sx, sy, cw, ch)
        layout = (round(f_label.cget("size")), round(f_pct.cget("size")),
                  round(lw, 1), round(h_pill, 1), round(brad, 1))
        if (not it) or self._bar_geo != geo or self._bar_layout != layout:
            c.delete("all")      # 整幅重建，元素状态绝对一致
            it = self._bar_items = {}
            it["bg"] = round_rect(c, RX(x1), RY(y1), RX(x2), RY(y2), brad,
                                  fill=bg_fill, outline=bg_line, width=1)
            it["track"] = round_rect(c, px1, py1, px2, py2, (py2 - py1) / 2.0,
                                     fill="#DCE3EC", outline="")
            it["fill"] = round_rect(c, px1, py1, px1 + fill_w, py2,
                                    (py2 - py1) / 2.0, fill=accent, outline="")
            it["pill"] = round_rect(c, lx, y_pill, lx + lw, y_pill + h_pill,
                                    h_pill / 2.0, fill=BAR_LABEL_BG, outline="")
            it["label"] = c.create_text(lx + lw / 2.0, y_pill + h_pill / 2.0,
                                        text=label, anchor="center",
                                        font=f_label, fill=BAR_LABEL_FG)
            for i, (dx, dy) in enumerate(((-1, 0), (1, 0), (0, -1), (0, 1))):
                it["halo%d" % i] = c.create_text(cx + dx, cy + dy, text=txt,
                                                 anchor="center", font=f_pct,
                                                 fill=BAR_TEXT_HALO)
            it["pct"] = c.create_text(cx, cy, text=txt, anchor="center",
                                      font=f_pct, fill=BAR_TEXT)
            if fill_w <= 0:
                c.itemconfigure(it["fill"], state="hidden")
            self._bar_geo = geo
            self._bar_layout = layout
            return

        # 4) 原地更新（数值/颜色变化时只改动这两类属性，不重建元素）
        #    关键：多边形必须传"整组点"，只传 4 个数值会把它塌缩成一条线
        #    （这正是"进度条填充消失、只剩灰轨道"的原因）。
        c.itemconfigure(it["bg"], fill=bg_fill, outline=bg_line)
        c.coords(it["fill"],
                 *round_rect_points(px1, py1, px1 + fill_w, py2,
                                    (py2 - py1) / 2.0))
        c.itemconfigure(it["fill"], fill=accent,
                        state="normal" if fill_w > 0 else "hidden")
        c.itemconfigure(it["label"], text=label)
        c.coords(it["label"], lx + lw / 2.0, y_pill + h_pill / 2.0)
        for i, (dx, dy) in enumerate(((-1, 0), (1, 0), (0, -1), (0, 1))):
            c.coords(it["halo%d" % i], cx + dx, cy + dy)
            c.itemconfigure(it["halo%d" % i], text=txt)
        c.coords(it["pct"], cx, cy)
        c.itemconfigure(it["pct"], text=txt)

    def update_bar(self, percent, charging=False, full=False, connected=True):
        """横条可见时更新内容；数据没变则不重绘。"""
        self.bar_last_data = (percent, charging, full, connected)  # 供即时切换复用
        if not self.bar_visible:
            return
        key = (percent, charging, full, connected)
        if key == self.bar_last_key:
            return
        self.bar_last_key = key
        self.draw_bar(percent, charging, full, connected)

    def _toggle_bar_event(self):
        """右键点击横条：走与组合键相同的去重入队路径。"""
        self._queue({"kind": "toggle_bar"})

    def toggle_bar(self):
        """组合键切换顶部横条显示/隐藏。

        关键：先用最近一次缓存的电量**立即上屏**，再去后台刷新。
        打开 HID 句柄读一帧最长要 2 秒（句柄重开时更久），之前是等读完才
        绘制，所以按组合键后要好几秒才看到横条。
        """
        self.bar_visible = not self.bar_visible
        log(f"电量横条 {'显示' if self.bar_visible else '隐藏'}")
        if self.bar_visible:
            # 1) 立即绘制：优先用"上次已知电量"，避免刚唤出时显示成灰轨道；
            #    完全没有历史数据时才是 --% 占位
            self.bar_last_key = None
            if self.bar_last_data:
                self.draw_bar(*self.bar_last_data)
            elif self.bar_last_pct is not None:
                self.draw_bar(self.bar_last_pct, False, False, True)
            else:
                self.draw_bar(None, connected=True)   # 中性占位 --%，不误报"未连接"
            self.bar_win.deiconify()
            self.bar_win.attributes("-topmost", True)
            self.bar_win.lift()
            self.bar_win.update_idletasks()   # 立刻刷新，不等下一个事件循环
            # 2) 再后台读一次真实电量，读到后由 update_bar 覆盖刷新
            self._spawn_worker("bar")
        else:
            if self._bar_ready and self.bar_win is not None:
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

    def show_battery(self, percent, charging=False, full=False, hold=None):
        """弹出电量窗；低电量时红色高亮并停留更久；hold 可指定保持秒数。"""
        self.draw_battery(percent, charging, full)
        low = percent is not None and percent <= LOW_BATTERY_PCT
        if hold is None:
            hold = HOLD_LOW_SECONDS if low else HOLD_SECONDS
        log(f"弹出电量窗 pct={percent} charging={charging} full={full} "
            f"hold={hold}s")
        self._present(hold)

    def show_disconnect(self):
        """弹出断开提示。"""
        self.draw_message("手柄已断开", "DS4")
        log("弹出断开提示窗")
        self._present(HOLD_DISCONNECT_SECONDS)

    def show_overcharge(self, pct):
        """防过充提醒：插着线且电量已达阈值（软件无法断电，只能提醒拔线）。"""
        self.draw_message("请拔掉充电线", "电量 %s%% · 防过充（已达 %d%%）"
                          % (pct if pct is not None else "—", OVERCHARGE_PCT))
        log("防过充提醒: 电量 %s%% 已达阈值 %d%%，提示拔线（软件无法切断充电）"
            % (pct, OVERCHARGE_PCT))
        self._present(HOLD_LOW_SECONDS)

    def check_overcharge(self, info):
        """按实测状态判断是否需要防过充提醒（带去重与冷却，避免反复打扰）。

        info 为 read_ds4_status() 的结果（含 pct/cable/charging/overcharge）。
        """
        if not OVERCHARGE_ENABLED or not info:
            return False
        pct = info.get("pct")
        trig = info.get("overcharge")
        if trig is None:
            cable = info.get("cable")
            charging = info.get("charging")
            trig = bool(cable and charging and pct is not None
                        and pct >= OVERCHARGE_PCT)
        now = time.monotonic()
        if not trig:
            # 电量回落到阈值以下（或已拔线）→ 允许下次再提醒
            if pct is not None and pct < OVERCHARGE_PCT:
                self.overcharge_warned = False
            return False
        if self.overcharge_warned or now < self._overcharge_cooldown:
            return False
        self.overcharge_warned = True
        self._overcharge_cooldown = now + 60.0
        self.show_overcharge(pct)
        return True

    def show_power(self, plugged):
        """蓝牙连接时接入/拔出电源提示（约 1.5 秒）。"""
        title = "接入电源" if plugged else "拔出电源"
        self.draw_message(title, "DS4")
        log(f"弹出{title}提示窗")
        self._present(HOLD_POWER_SECONDS)

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
        self._spawn_worker("plug")

    def _battery_worker(self, reason="plug"):
        try:
            info = read_ds4_status(quick=(reason == "bar"))
            if info is None:
                log(f"电量读取失败(reason={reason}) -> 弹窗显示 --%")
                self._queue({"kind": "battery", "pct": None,
                             "reason": reason})
            elif reason == "lowcheck":
                # 例行检查只在"状态有变化"或"低电量"时写日志，避免刷屏
                note = (info["pct"], info["charging"], info["full"])
                if note != self._last_lowcheck or info["pct"] <= LOW_BATTERY_PCT:
                    log(f"电量读取(reason={reason}) -> {info}")
                    self._last_lowcheck = note
                self._queue({"kind": "battery", "reason": reason,
                             **info})
            else:
                log(f"电量读取(reason={reason}) -> {info}")
                self._queue({"kind": "battery", "reason": reason,
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
            self._last_report_ts = time.monotonic()   # 句柄存活证据（健康探测用）
            offs = report_offsets(data)
            if offs is None:
                return
            if data[0] == 0x01 and self.watch_dev is not None and \
                    is_bt_device(self.watch_dev):
                return  # 蓝牙设备激活前的位置报告(0x01)无按键，忽略
            # 长帧扩展报告（547B）：b9 为数据流字节，但实测 bit0 仍是 PS 键
            # （按下时 bit0=1，23:59:43 双击瞬间 b9=0x4D 佐证）。只提示不阻断。
            if len(data) > 78:
                now = time.monotonic()
                if now - self._longframe_log_ts > 300.0:
                    self._longframe_log_ts = now
                    log(f"提示: 手柄报告为扩展格式(长度={len(data)}B)，"
                        f"若 PS 键异常请重启手柄或重新配对")
            bi, psi = offs
            if len(data) <= psi:
                return
            # 电源线状态检测（蓝牙 0x11 / 扩展 547 报告）：b32 bit4 = 线缆标志，
            # 变化即弹接入/拔出电源提示（1.5 秒）。有线 0x01 报告不检测。
            if data[0] == 0x11 and len(data) > bi:
                cable_now = bool(data[bi] & 0x10)
                if self._last_cable is not None and cable_now != self._last_cable:
                    self._queue({"kind": "power_plug" if cable_now
                                 else "power_unplug"})
                self._last_cable = cable_now
            ps = bool(data[psi] & PS_BUTTON_MASK)
            if ps and not self.ps_prev:          # PS 上升沿
                now = time.monotonic()
                if dpad_down(data):
                    # 组合键：十字键下 + PS → 切换横条（冷却 1s 防误触连发）
                    self.last_ps_time = None      # 不计入双击判定
                    if now < self.ps_cooldown_until:
                        pass                      # 冷却中，忽略
                    else:
                        log("组合键(十字键下+PS) -> 切换电量横条")
                        self._queue({"kind": "toggle_bar"})
                        self.ps_cooldown_until = now + 1.0
                else:
                    if now < self.ps_cooldown_until:
                        # 触发冷却中：清掉双击计时，防止抖动连续误触发
                        self.last_ps_time = None
                    elif self.last_ps_time is not None and \
                            (now - self.last_ps_time) * 1000 <= DOUBLE_PRESS_MS:
                        # 双击 PS → 弹电量（触发后冷却 1.5 秒）
                        log("PS 双击 -> 弹出电量")
                        self.last_ps_time = None
                        self.ps_cooldown_until = now + 1.5
                        bi, _ = offs
                        if len(data) > bi:
                            if data[0] == 0x11:
                                maybe_dump_bt_report(data)
                                info = decode_bt_report(data, bi)
                            else:
                                info = decode_status(data[bi])
                            # PS 双击同帧：记忆真实电量（无线，或有线档位 ≤10）
                            raw = data[bi]
                            if not (raw & 0x10) or (raw & 0x0F) <= 10:
                                _remember_wireless(info["pct"])
                            self._queue({"kind": "battery",
                                         "reason": "ps", **info})
                        else:
                            self._queue({"kind": "battery", "pct": None,
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
            self.last_ps_time = None   # 重开后清空双击计时，防止首帧误触发

    def _watcher_alive(self):
        """监听句柄是否仍健康。

        判定依据（任一不满足即视为失效 → 重开）：
        1. is_opened()：pywinusb 内部标志；
        2. 内部读取线程 is_active()：设备断开（错误 1167）时线程会退出；
        3. is_plugged()：主动探测设备是否仍在系统里。屏幕共享/语音开黑
           软件抢走设备后，前两项都可能仍为 True，只有主动探测能发现；
        4. 报告静默：曾经收到过报告，但已静默超过 WATCH_QUIET_SEC
           （USB 下 DS4 至少每 5ms 刷一帧，静默即说明底层已卡住）。
        """
        dev = self.watch_dev
        if dev is None:
            return False
        try:
            if not dev.is_opened():
                return False
            reader = getattr(dev, "_HidDevice__reading_thread", None)
            if reader is not None and hasattr(reader, "is_active"):
                if not reader.is_active():
                    return False
            # 主动探测：设备是否还在（被共享软件独占/拔出时为 False）
            try:
                if not dev.is_plugged():
                    self._probe_fail_streak += 1
                    return False
                self._probe_ok_ts = time.monotonic()
                self._probe_fail_streak = 0
            except Exception:
                self._probe_fail_streak += 1
                return False
            # 静默超时：只有当本句柄确实收到过报告时，才把"长时间没报告"当故障
            if self._last_report_ts and \
                    time.monotonic() - self._last_report_ts > WATCH_QUIET_SEC:
                log(f"监听句柄静默超过 {WATCH_QUIET_SEC:.0f} 秒，判定失效并重开")
                self._last_report_ts = 0.0
                return False
            return True
        except Exception:
            return False

    def ensure_watcher(self):
        """维持一个常开手柄句柄，用于监听 PS 键；设备拔出/重插时自动重开。

        必须在后台线程调用（主线程绝不执行 HID 打开/枚举——屏幕共享、语音
        开黑类软件同时操作手柄 HID 时，dev.open()/setupapi 枚举可能阻塞数十
        秒，会卡死 tkinter 主循环）。打开动作本身也带时限，连续失败时指数
        退避（3→6→12→…→60 秒），避免与共享软件互相抢设备形成风暴。
        """
        if self._watcher_busy:
            return
        self._watcher_busy = True
        try:
            now = time.time()
            devices = find_ds4_devices()
            paths = {d.device_path for d in devices}
            if self.watch_dev is not None:
                if self.watch_dev.device_path in paths and self._watcher_alive():
                    self._watch_retry_ts = 0.0
                    self._open_fail_streak = 0
                    return
                if now < self._watch_retry_ts:
                    return      # 退避中，稍后再试
                # 路径对不上，或句柄已失效（被共享软件抢占/快速拔插漏检）→ 重开
                if now - self._reopen_log_ts > 30.0:
                    self._reopen_log_ts = now
                    log("监听句柄失效，重开手柄句柄")
                self.close_watcher()
            if not devices:
                return
            if now < self._watch_retry_ts:
                return
            dev = devices[0]
            # 先给一个保守的退避时间，成功后再清零：即使下面挂住/异常也不会重开风暴
            self._open_fail_streak += 1
            backoff = min(WATCH_FAIL_BACKOFF_BASE * (2 ** (self._open_fail_streak - 1)),
                          WATCH_FAIL_BACKOFF_MAX)
            self._watch_retry_ts = now + backoff
            try:
                dev.set_raw_data_handler(self.ps_handler)
                if _open_device_bounded(dev):
                    if is_bt_device(dev):
                        activate_bt_full_report(dev)
                    self.watch_dev = dev
                    self.ps_prev = False
                    self._last_report_ts = 0.0
                    self._probe_ok_ts = time.monotonic()
                    self._watch_retry_ts = 0.0
                    self._open_fail_streak = 0
                else:
                    log(f"打开手柄句柄失败(第 {self._open_fail_streak} 次)，"
                        f"{backoff:.0f} 秒后重试"
                        f"（若正在使用屏幕共享/语音开黑软件，多半是设备被其占用）")
                    try:
                        dev.close()
                    except Exception:
                        pass
            except Exception:
                log("ensure_watcher 打开失败:\n" + traceback.format_exc())
        finally:
            self._watcher_busy = False

    def _poll_devices(self):
        """后台枚举手柄并更新连接状态。

        绝不能放在 tkinter 主线程执行：屏幕共享/语音开黑软件同时枚举或占用
        手柄 HID 时，setupapi 枚举可能阻塞数秒到数十秒，主线程一卡就是"程序
        假死"。这里由看门狗线程每秒调用一次，主线程只读 self._connected。

        为避免 1 秒一次的无谓枚举，拔掉手柄后逐步放慢探测频率（最长 5 秒），
        插着时保持 1 秒以便快速响应。
        """
        if self._dev_poll_busy:
            return
        # 未连接时降频轮询：省 CPU，同时仍能在数秒内发现手柄接入
        if not self._connected and \
                time.time() - self._last_dev_poll < DEV_POLL_IDLE_SEC:
            return
        self._dev_poll_busy = True
        try:
            self._connected = len(find_ds4_devices()) > 0
            self._last_dev_poll = time.time()
        except Exception:
            self._connected = False
        finally:
            self._dev_poll_busy = False
            self._dev_state_ready = True

    def _sample_resources(self):
        """周期性记录资源占用；内存异常增长时自愈重启，避免长跑崩溃。

        这是"防止使用时崩溃"的可观测性基础：句柄/线程/内存趋势写进日志，
        真出问题时能直接看出是泄漏还是单次峰值。全部走 ctypes，不依赖 pywin32。
        """
        self._res_sample_ts = time.time()
        try:
            mem_mb, handles = _read_proc_stats()
            threads = threading.active_count()
            if mem_mb is not None:
                log("资源监控: 内存 %.1f MB, 线程 %d, 句柄 %s, 待处理任务 %d"
                    % (mem_mb, threads,
                       handles if handles is not None else "n/a",
                       len(self._worker_todo)))
            if mem_mb is not None and mem_mb > MEM_LIMIT_MB:
                log("资源监控: 内存 %.1f MB 超过阈值 %.0f MB，自愈重启"
                    % (mem_mb, MEM_LIMIT_MB))
                try:
                    os.execv(sys.executable, [sys.executable] + sys.argv)
                except Exception:
                    log("自愈重启失败:\n" + traceback.format_exc())
        except Exception:
            pass

    def _watchdog(self):
        """看门狗：后台维护设备连接状态、采样资源占用，并在主循环假死时重启。

        屏幕共享/直播等场景若导致主线程被系统调用阻塞，tkinter 会整体假死
        （不抛异常、不写日志，进程仍在但无响应）。看门狗检测到心跳停跳后
        原地重启进程（os.execv 同进程替换，单实例互斥随之释放），实现自愈。
        """
        while True:
            time.sleep(DEV_POLL_SEC)
            try:
                self._poll_devices()
            except Exception:
                pass
            try:
                if time.time() - self._res_sample_ts >= RES_SAMPLE_SEC:
                    self._sample_resources()
            except Exception:
                pass
            if time.time() - self._last_tick > 30:
                log("看门狗: 主循环疑似卡死(>30秒无心跳)，自动重启")
                try:
                    os.execv(sys.executable, [sys.executable] + sys.argv)
                except Exception:
                    log("看门狗重启失败:\n" + traceback.format_exc())
                    return

    def poll_loop(self):
        """轮询主循环：任何异常都记录日志并继续调度，绝不静默停摆。"""
        try:
            self._poll_tick()
        except Exception:
            log("poll_loop 异常:\n" + traceback.format_exc())
        finally:
            self.root.after(POLL_MS, self.poll_loop)

    def _poll_tick(self):
        self._last_tick = time.time()   # 心跳：看门狗据此判断主循环是否假死
        # 先处理队列消息（主线程，tkinter 线程安全；单轮限次防极端积压）
        try:
            drained = 0
            while True:
                self._dispatch(self.result_q.get_nowait())
                drained += 1
                if drained > 30:
                    break
        except queue.Empty:
            pass

        # 连接状态来自后台枚举缓存：主线程绝不直接做 HID 枚举（会被共享软件拖死）
        connected = self._connected

        if not self._dev_state_ready:
            # 后台首次枚举还没完成：本轮不作为基线，等拿到真实状态再判断，
            # 避免把手柄一直插着的开机场景误判成"未连接"而漏掉启动弹窗
            return
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
                self._queue({"kind": "disconnect"})
                self.low_warned = False
                self.close_watcher()
        self.prev_connected = connected

        # 快速拔插兜底：1 秒轮询可能漏掉瞬时断开，此时连接状态仍是 True，
        # 但监听句柄的读取线程已退出 → 判定为"重插"，重新弹电量并重开句柄。
        # 被屏幕共享/语音软件抢走设备时也走这条路径恢复。
        if connected:
            if self.watch_dev is not None and not self._watcher_alive():
                log("检测到手柄重插/句柄被抢占 -> 重新弹电量")
                self.close_watcher()
                self.on_connect()

        # 低电量周期检查（约每 30 秒一次，避免过度打扰）
        self.poll_count = (self.poll_count + 1) % LOW_CHECK_INTERVAL_POLLS
        if connected and self.poll_count == 0:
            self._spawn_worker("lowcheck")

        # 横条实时刷新（显示时每 5 秒读一次电量）
        if self.bar_visible and self.poll_count % BAR_REFRESH_POLLS == 0:
            self._spawn_worker("bar")

        # 维持 PS 键监听句柄（后台线程执行 HID 打开，主线程绝不阻塞于系统调用）
        if self.watch_dev is None or not self._watcher_alive():
            self._spawn_watcher()

    # ---------- 后台线程调度（常驻线程 + 并发限流 + 事件去重） ----------
    def _spawn_watcher(self):
        """仅在没有重开任务进行中时启动监听句柄维护线程。"""
        if self._watcher_busy:
            return
        threading.Thread(target=self.ensure_watcher, daemon=True).start()

    def _spawn_worker(self, reason):
        """把一次 HID 读取排入常驻工作线程。

        旧实现每次读取都新建一个线程（含节流上限）。改用**单个常驻线程 +
        任务队列**后：线程数恒定、无反复创建/销毁开销，且"已有同类任务待处理"
        时直接跳过，天然完成去重。屏幕共享/语音软件抢占设备时读取可能耗时
        数秒，此时队列也不会堆积。
        """
        with self._worker_lock:
            if reason in self._worker_pending:
                return
            if len(self._worker_pending) >= ACTIVE_WORKERS_MAX:
                return
            self._worker_pending.add(reason)
            self._worker_todo.append(reason)
        self._worker_wake.set()

    def _worker_thread(self):
        """常驻工作线程：串行执行 HID 读取任务。"""
        while True:
            self._worker_wake.wait(1.0)
            self._worker_wake.clear()
            while True:
                with self._worker_lock:
                    if not self._worker_todo:
                        break
                    reason = self._worker_todo.popleft()
                try:
                    self._battery_worker(reason)
                except Exception:
                    log("worker 线程异常:\n" + traceback.format_exc())
                finally:
                    with self._worker_lock:
                        self._worker_pending.discard(reason)

    def _queue(self, payload):
        """入队主线程动作，并对同类事件做时间窗去重。

        防触发风暴：PS 键抖动 / 设备反复重枚举时，同一类提示在
        BURST_WINDOW_SEC 内只响应一次，避免"同一秒弹出 5 个电量窗"。
        """
        kind = payload.get("kind", "")
        if kind in ("battery", "toggle_bar"):
            now = time.monotonic()
            last = self._last_queued.get(kind, 0.0)
            if now - last < BURST_WINDOW_SEC:
                return False
            self._last_queued[kind] = now
        self.result_q.put(payload)
        return True

    def _dispatch(self, payload):
        if payload.get("kind") == "toggle_bar":
            self.toggle_bar()
            return
        if payload.get("kind") == "disconnect":
            self.show_disconnect()
            self.update_bar(None, connected=False)
            return
        if payload.get("kind") == "power_plug":
            self.show_power(True)
            return
        if payload.get("kind") == "power_unplug":
            self.show_power(False)
            return
        pct = payload.get("pct")
        reason = payload.get("reason", "plug")
        if reason == "bar":
            # 横条刷新：只更新横条，不弹窗。
            # 本次读不到电量时沿用"上次已知电量"，避免横条显示成灰轨道。
            if pct is not None:
                self.bar_last_pct = pct
            elif self.bar_last_pct is None:
                bd = self.bar_last_data
                self.bar_last_pct = bd[0] if bd else None
            self.update_bar(pct if pct is not None else self.bar_last_pct,
                            payload.get("charging", False),
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
            # 防过充：插着线且已达阈值 → 提醒拔线（本轮只提醒一次）
            self.check_overcharge(payload)
        else:
            if pct is not None and pct <= LOW_BATTERY_PCT:
                self.low_warned = True
            # PS 双击手动查看：固定显示 2 秒（淡入+淡出合计 0.5 秒）
            hold = HOLD_PS_SECONDS if reason == "ps" else None
            self.show_battery(pct, payload.get("charging", False),
                              payload.get("full", False), hold=hold)
            # 防过充：接入/手动查看时同样检查（复用同一帧数据，不再读设备）
            self.check_overcharge(payload)
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
    if "--version" in sys.argv:
        print("%s v%s" % (APP_NAME, __version__))
        return
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

    # 读取持久化的无线电量记忆（有线充电假象时用于显示真实电量）
    _load_state()

    # DPI 感知，保证文字清晰
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(1)
    except Exception:
        pass

    # 启动自检信息：排查启动慢/启动失败时一眼能看出环境
    log("程序启动 v%s pid=%d python=%s frozen=%s"
        % (__version__, os.getpid(), sys.version.split()[0],
           bool(getattr(sys, "frozen", False))))
    _maybe_register_faulthandler()

    overlay = BatteryOverlay()
    log("界面初始化完成")

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
            overlay._ensure_bar_win()
            overlay.bar_win.deiconify()
            overlay.bar_win.lift()
            overlay.draw_bar(pct, False, False)
        overlay.root.after(300, _preview_bar)

    overlay.root.mainloop()


if __name__ == "__main__":
    # 兜底：任何未捕获异常都写日志，并在 10 秒后自我重启一次，
    # 避免"程序还在但界面没了"这类静默失效。
    tries = 0
    while True:
        try:
            main()
            break
        except SystemExit:
            raise
        except BaseException:
            tries += 1
            try:
                log("顶层异常，准备重启:\n" + traceback.format_exc())
            except Exception:
                pass
            if tries > 2:
                break
            time.sleep(10)
