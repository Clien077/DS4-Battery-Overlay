# -*- coding: utf-8 -*-
"""
DS4 电量提示 · 可视化控制面板
==============================
一个窗口按钮化操作常驻程序：启动 / 停止 / 重启 / 查看状态 / 开机自启 /
防过充开关 / 电池详情（含续航与充满时长估算）/ 预览界面。

本面板**自包含**：启停与进程识别都在本文件内实现，不再依赖 ds4_manager。

运行：python ds4_battery_overlay_panel.py
打包后可放在 ds4_battery_overlay.exe 同目录使用。
"""
import os
import subprocess
import sys
import time
import tkinter as tk

# 面板自身所在目录（打包 exe 后为本 exe 所在目录）
BASE = os.path.dirname(sys.executable) if getattr(sys, "frozen", False) \
    else os.path.dirname(os.path.abspath(__file__))
# 配置文件路径（防过充开关 / 语言设置），与常驻程序共用同一份
CONFIG_FILE = os.path.join(BASE, "ds4_config.json")

# ==============================================================
# 多语言（i18n）：中文 / 英文
# ==============================================================
LANG_FILE = os.path.join(BASE, '_lang.signal')

_TEXTS = {
    "bar.charging": ('充电中', 'Charging'),
    "bar.disconnected": ('未连接', 'Offline'),
    "bar.ds4": ('DS4', 'DS4'),
    "bar.full": ('已充满', 'Full'),
    "panel.app": ('DS4 电量提示', 'DS4 Battery Overlay'),
    "panel.autostart.disable": ('关闭开机自启', 'Disable autostart'),
    "panel.autostart.enable": ('开启开机自启', 'Enable autostart'),
    "panel.autostart.off": ('开机自启：未开启', 'Autostart: off'),
    "panel.autostart.on": ('开机自启：已开启', 'Autostart: on'),
    "panel.btn.details": ('电池详情', 'Battery details'),
    "panel.btn.lang": ('语言：中文', 'Language: English'),
    "panel.btn.lang_hint": ('点击切换为英文', 'Click to switch to Chinese'),
    "panel.btn.preview": ('预览外观', 'Preview'),
    "panel.btn.refresh": ('刷新状态', 'Refresh'),
    "panel.btn.restart": ('重启', 'Restart'),
    "panel.btn.start": ('启动', 'Start'),
    "panel.btn.stop": ('停止', 'Stop'),
    "panel.hint": ('提示：右键点击弹出的电量窗可退出常驻程序', 'Tip: right-click the popup to exit the resident program'),
    "panel.info.charging": ('充电状态  ：%s', 'Charging   ：%s'),
    "panel.info.conn": ('连接方式  ：%s', 'Link       ：%s'),
    "panel.info.conn.bt": ('蓝牙无线', 'Bluetooth'),
    "panel.info.conn.usb": ('USB 有线', 'USB wired'),
    "panel.info.full_line": ('预计充满  ：%s', 'Charge time：%s'),
    "panel.info.full_none": ('估算中（插线充电跨档后自动出数）', 'Estimating (appears after one charging step)'),
    "panel.info.full_val": ('还需 %s', 'about %s to full'),
    "panel.info.level": ('真实电量  ：%d%%', 'Real level ：%d%%'),
    "panel.info.no_data": ('暂无电池数据：请先启动常驻程序并连接手柄（数据文件：ds4_battery_info.json）', 'No battery data yet: start the resident program and connect the controller (file: ds4_battery_info.json)'),
    "panel.info.no_level": ('手柄已连接但未读到电量：可能被其它软件独占，或刚连接尚未出数', 'Controller connected but no level read yet: it may be exclusively held by another app, or just connected'),
    "panel.info.raw": ('原始档位  ：%s / 15  ← 硬件按 10%% 一档上报，这是精度上限', 'Raw step   ：%s / 15  ← hardware reports in 10%% steps (accuracy ceiling)'),
    "panel.info.remain": ('预计续航  ：%s', 'Runtime    ：%s'),
    "panel.info.remain_cached": ('   ← 按上次无线速率推算', '   ← from last wireless rate'),
    "panel.info.remain_none": ('估算中（跨过一档后自动出数）', 'Estimating (appears after one full step)'),
    "panel.info.remain_val": ('还能用 %s', 'about %s left'),
    "panel.info.state.charging": ('充电中', 'Charging'),
    "panel.info.state.discharging": ('放电中（无线）', 'Discharging (wireless)'),
    "panel.info.state.full": ('已充满', 'Fully charged'),
    "panel.info.time": ('数据时间  ：%s%s%s', 'Updated    ：%s%s%s'),
    "panel.info.title": ('电池详情（实测）', 'Battery details (measured)'),
    "panel.info.warn14": ('\n  ※ 手柄报「电压/温度异常，已暂停充电」（档位 14），故不显示百分比', '\n  * Controller reports voltage/temperature anomaly (step 14), charging paused — no percentage shown'),
    "panel.info.warn15": ('\n  ※ 手柄报「充电故障」（档位 15），故不显示百分比', '\n  * Controller reports a charging fault (step 15) — no percentage shown'),
    "panel.lang.en": ('英文', 'English'),
    "panel.lang.zh": ('中文', 'Chinese'),
    "panel.note.autostart_off": ('已取消开机自启', 'Autostart disabled'),
    "panel.note.autostart_on": ('已开启开机自启', 'Autostart enabled'),
    "panel.note.cfg_fail": ('写入配置失败：%s', 'Failed to write config: %s'),
    "panel.note.error": ('操作出错：%s', 'Error: %s'),
    "panel.note.fail": ('操作失败：%s', 'Failed: %s'),
    "panel.note.lang": ('语言已切换为%s（顶部与底部电量显示同步切换）', 'Language switched to %s (top & bottom displays updated)'),
    "panel.note.not_running": ('程序本来就没在运行', 'It was not running'),
    "panel.note.oc_off": ('防过充已关闭', 'Overcharge guard off'),
    "panel.note.oc_on": ('防过充已开启：插着线且电量达到 %d%% 时弹窗提醒拔线\n（软件无法切断充电电路，只能提醒）', 'Overcharge guard on: warns you to unplug when the battery reaches %d%%\n(software cannot cut the charging circuit)'),
    "panel.note.preview": ('已预览 66% 弹窗 + 顶部横条（观察屏幕底部/顶部）', 'Previewed 66% popup + top bar (check screen top/bottom)'),
    "panel.note.preview_fail": ('预览失败：%s', 'Preview failed: %s'),
    "panel.note.restarted": ('已重启常驻程序', 'Resident program restarted'),
    "panel.note.started": ('已启动常驻程序', 'Resident program started'),
    "panel.note.stopped": ('已停止 %d 个实例', 'Stopped %d instance(s)'),
    "panel.overcharge.off": ('开启防过充(%d%%)', 'Enable guard (%d%%)'),
    "panel.overcharge.on": ('关闭防过充(%d%%)', 'Disable guard (%d%%)'),
    "panel.pid": ('进程 PID：', 'PID: '),
    "panel.pid.none": ('进程 PID：—', 'PID: —'),
    "panel.state.checking": ('检测中…', 'Checking…'),
    "panel.state.running": ('运行中', 'Running'),
    "panel.state.stopped": ('未运行', 'Not running'),
    "panel.window": ('%s v%s · 控制面板', '%s v%s · Control Panel'),
    # 窗口标题里的程序名单独取词，保证标题栏与顶部标题语言一致（不留中英混显）
    "panel.window_name": ('DS4 电量提示', 'DS4 Battery Overlay'),
    "popup.charging": ('充电中', 'Charging'),
    "popup.disconnected_sub": ('DS4', 'DS4'),
    "popup.disconnected_title": ('手柄已断开', 'Controller disconnected'),
    "popup.dualshock": ('DUALSHOCK 4', 'DUALSHOCK 4'),
    "popup.full": ('已充满', 'Fully charged'),
    "popup.low": ('低电量 · 请及时充电', 'Low battery · please charge'),
    "popup.overcharge_sub": ('电量 %s%% · 防过充（已达 %d%%）', 'Battery %s%% · overcharge guard (%d%%)'),
    "popup.overcharge_title": ('请拔掉充电线', 'Please unplug the charger'),
    "popup.power_off": ('已断开电源', 'Power disconnected'),
    "popup.power_on": ('接入电源', 'Power connected'),
    "time.estimating": ('估算中', 'Estimating'),
    "time.estimating_long": ('估算中（手柄按 10% 一档上报，需累积到跨档才能算速率）', 'Estimating (DS4 reports in 10% steps; needs a full step to compute a rate)'),
    "time.full": ('已充满', 'Full'),
    "time.hours": ('约 %d 小时 %d 分钟', '~%dh %dm'),
    "time.lt1min": ('不到 1 分钟', '< 1 min'),
    "time.minutes": ('约 %d 分钟', '~%d min'),
}


def _norm_lang(v):
    v = (v or "").strip().lower()
    return "en" if v.startswith("en") else "zh"


def _load_lang():
    """语言取自 ds4_config.json 的 lang 字段；缺省中文。"""
    try:
        import json
        with open(CONFIG_FILE, "r", encoding="utf-8") as f:
            return _norm_lang((json.load(f) or {}).get("lang"))
    except Exception:
        return "zh"


def _t(key, *args):
    """取当前语言文案；带 %s/%d 占位时自动格式化。"""
    pair = _TEXTS.get(key)
    if not pair:
        return key
    s = pair[1] if _LANG == "en" else pair[0]
    try:
        return s % args if args else s
    except Exception:
        return s


def _lang_signal():
    """返回语言信号文件的修改时间；面板切换语言后会重写它。"""
    try:
        return os.path.getmtime(LANG_FILE)
    except OSError:
        return 0.0


_LANG = "zh"
_LANG_SIG = 0.0


# ---- 版本号：与主程序保持一致（升级时同步修改同名常量）----
__version__ = "1.3.1"


# ---- 手柄图标（base64 内嵌，避免依赖外部文件；打包后同样可用）----
_GAMEPAD_ICO_B64 = (
    "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"
    "tu1ntyJXTgAAAABJRU5ErkJggg=="
)

_gp_ico_path = None


def _apply_gamepad_icon(win):
    """把窗口左上角与任务栏图标换成手柄样式。

    Tk 的 iconbitmap() 只设置**窗口图标**（WM_GETICON），而任务栏按钮在部分
    情况下显示的是**窗口类图标**（GCLP_HICON），因此这里两者都显式设置；
    失败静默，不影响功能。
    """
    global _gp_ico_path
    try:
        import base64 as _b64
        import ctypes
        import os as _os
        import tempfile
        if _gp_ico_path is None:
            d = _os.path.join(tempfile.gettempdir(), "ds4_battery_overlay")
            _os.makedirs(d, exist_ok=True)
            _gp_ico_path = _os.path.join(d, "ds4_gamepad.ico")
            with open(_gp_ico_path, "wb") as f:
                f.write(_b64.b64decode(_GAMEPAD_ICO_B64))
        win.iconbitmap(_gp_ico_path)
        win.update_idletasks()
        u32 = ctypes.windll.user32
        u32.LoadImageW.restype = ctypes.c_void_p
        u32.LoadImageW.argtypes = [ctypes.c_void_p, ctypes.c_wchar_p,
                                   ctypes.c_uint, ctypes.c_int, ctypes.c_int,
                                   ctypes.c_uint]
        u32.GetAncestor.restype = ctypes.c_void_p
        IMAGE_ICON, LR_LOADFROMFILE, LR_DEFAULTSIZE = 1, 0x10, 0x40
        ICON_BIG, ICON_SMALL = 1, 0
        WM_SETICON = 0x0080
        GCLP_HICON, GCLP_HICONSM = -14, -34
        big = u32.LoadImageW(None, _gp_ico_path, IMAGE_ICON, 32, 32,
                             LR_LOADFROMFILE)
        small = u32.LoadImageW(None, _gp_ico_path, IMAGE_ICON, 16, 16,
                               LR_LOADFROMFILE) or big
        hwnd = u32.GetAncestor(win.winfo_id(), 2) or win.winfo_id()
        if big:
            u32.SendMessageW(ctypes.c_void_p(hwnd), WM_SETICON, ICON_BIG,
                             ctypes.c_void_p(big))
        if small:
            u32.SendMessageW(ctypes.c_void_p(hwnd), WM_SETICON, ICON_SMALL,
                             ctypes.c_void_p(small))
        # 同时设置窗口类图标：任务栏部分场景读的是它
        if big:
            u32.SetClassLongPtrW(ctypes.c_void_p(hwnd), GCLP_HICON,
                                 ctypes.c_void_p(big))
        if small:
            u32.SetClassLongPtrW(ctypes.c_void_p(hwnd), GCLP_HICONSM,
                                 ctypes.c_void_p(small))
        _icon_log("ok hwnd=%s big=%s small=%s iconbitmap=%s"
                  % (hwnd, big, small, _gp_ico_path))
        return True
    except Exception as e:
        _icon_log("fail %s: %s" % (type(e).__name__, e))
        return False


def _icon_log(msg):
    """图标设置诊断日志（写到程序目录，便于排查 frozen 下的问题）。"""
    try:
        import time as _t
        with open(os.path.join(BASE, "ds4_panel_icon.log"), "a",
                  encoding="utf-8") as f:
            f.write("[%s] %s\n" % (_t.strftime("%Y-%m-%d %H:%M:%S"), msg))
    except Exception:
        pass
APP_NAME = "DS4 电量提示"

OVERLAY_EXE = os.path.join(BASE, "ds4_battery_overlay.exe")
OVERLAY_PY = os.path.join(BASE, "ds4_battery_overlay.py")
AUTOSTART_NAME = "DS4BatteryOverlay"
RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"

BG = "#161A1E"
CARD = "#1E242B"
FG = "#EDF1F6"
SUB = "#9AA3AD"
GREEN = "#3DDC84"
RED = "#E5484D"
YELLOW = "#F5B700"
BLUE = "#4C8DFF"


def target_cmd(extra=None):
    """返回要启动的命令行（打包 exe 优先，否则 pythonw + 脚本）。"""
    if os.path.exists(OVERLAY_EXE):
        cmd = [OVERLAY_EXE]
    else:
        exe = sys.executable
        if exe.lower().endswith("python.exe"):
            exe = exe[:-len("python.exe")] + "pythonw.exe"
        cmd = [exe, OVERLAY_PY]
    return cmd + list(extra or [])


def find_overlay_pids():
    """精确匹配常驻主程序进程（不依赖 ds4_manager）。

    只认"进程名是 ds4_battery_overlay(.exe)"，或"进程名是 python(w).exe 且
    命令行以本程序脚本全文结尾"。旧写法只判断命令行是否包含该字符串，
    会把 PowerShell 包装进程、调试脚本、自身都算成实例（实测 1 个误报为 4 个）。
    """
    ps_cmd = (
        "Get-CimInstance Win32_Process | Where-Object { "
        "$n = $_.Name; $c = $_.CommandLine; "
        "if (-not $c) { $false } "
        "elseif ($n -match '^(?i)ds4_battery_overlay(\\.exe)?$') { $true } "
        "elseif ($n -match '^(?i)pythonw?(\\.exe)?$') { "
        "$c -match 'ds4_battery_overlay\\.py[\"''\\s]*$' } "
        "else { $false } "
        "} | Select-Object -ExpandProperty ProcessId"
    )
    try:
        out = subprocess.run(
            ["powershell", "-NoProfile", "-NonInteractive", "-Command", ps_cmd],
            capture_output=True, text=True, timeout=30)
        return [int(x.strip()) for x in out.stdout.splitlines() if x.strip().isdigit()]
    except Exception:
        return []


def autostart_enabled():
    """查询注册表里是否已开启开机自启。"""
    import winreg
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY) as k:
            winreg.QueryValueEx(k, AUTOSTART_NAME)
        return True
    except OSError:
        return False


def set_autostart(on):
    """开关开机自启，返回 (是否成功, 说明文字)。"""
    try:
        if on:
            cmd = '"%s"' % (OVERLAY_EXE if os.path.exists(OVERLAY_EXE)
                            else sys.executable)
            subprocess.run([OVERLAY_EXE if os.path.exists(OVERLAY_EXE)
                            else sys.executable,
                            "--autostart"], capture_output=True, timeout=20)
            import winreg
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY, 0,
                                winreg.KEY_SET_VALUE) as k:
                winreg.SetValueEx(k, AUTOSTART_NAME, 0, winreg.REG_SZ, cmd)
            return True, _t("panel.note.autostart_on")
        else:
            exe = OVERLAY_EXE if os.path.exists(OVERLAY_EXE) else sys.executable
            subprocess.run([exe, "--no-autostart"], capture_output=True, timeout=20)
            import winreg
            try:
                with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY, 0,
                                    winreg.KEY_SET_VALUE) as k:
                    winreg.DeleteValue(k, AUTOSTART_NAME)
            except FileNotFoundError:
                pass
            return True, _t("panel.note.autostart_off")
    except Exception as e:
        return False, _t("panel.note.fail", e)


class Panel(tk.Tk):
    def __init__(self):
        super().__init__()
        # 按配置里的语言启动（与常驻程序共用 ds4_config.json 的 lang 字段）
        global _LANG, _LANG_SIG
        _LANG = _load_lang()
        _LANG_SIG = _lang_signal()
        self.title(_t("panel.window", _t("panel.window_name"), __version__))
        self.configure(bg=BG)
        self.resizable(False, False)
        _apply_gamepad_icon(self)          # 左上角图标 -> 手柄样式
        # 窗口映射后 Tk 会重建部分窗口属性，此时再补打一次图标，
        # 否则任务栏按钮会退回默认图标（实测 WM_GETICON 会变回 0）。
        self.after(200, lambda: _apply_gamepad_icon(self))
        self._build()
        self.refresh()

    # ---------- 界面 ----------
    def _build(self):
        pad = dict(padx=16)

        # 顶部大标题：保存引用，切换语言时直接改文案（不再靠字号去猜控件）
        self.app_lbl = tk.Label(self, text=_t("panel.app"), bg=BG, fg=FG,
                                font=("Microsoft YaHei UI", 14, "bold"))
        self.app_lbl.pack(anchor="w", pady=(14, 0), **pad)

        card = tk.Frame(self, bg=CARD, highlightthickness=0)
        card.pack(fill="x", pady=(10, 12), **pad)

        self.dot = tk.Label(card, text="●", bg=CARD, fg=SUB, font=("Segoe UI", 16))
        self.dot.grid(row=0, column=0, padx=(14, 6), pady=(12, 2), sticky="w")
        self.state_lbl = tk.Label(card, text=_t("panel.state.checking"), bg=CARD, fg=FG,
                                  font=("Microsoft YaHei UI", 12, "bold"))
        self.state_lbl.grid(row=0, column=1, columnspan=2, pady=(12, 2), sticky="w")

        self.pid_lbl = tk.Label(card, text="", bg=CARD, fg=SUB,
                                font=("Microsoft YaHei UI", 9))
        self.pid_lbl.grid(row=1, column=0, columnspan=3, padx=14, pady=(0, 6), sticky="w")

        self.auto_lbl = tk.Label(card, text="", bg=CARD, fg=SUB,
                                 font=("Microsoft YaHei UI", 9))
        self.auto_lbl.grid(row=2, column=0, columnspan=3, padx=14, pady=(0, 12), sticky="w")

        btns = tk.Frame(self, bg=BG)
        btns.pack(fill="x", **pad)
        for i in range(3):
            btns.columnconfigure(i, weight=1)

        self.start_btn = self._btn(btns, _t("panel.btn.start"), GREEN,
                                   lambda: self.act("start"))
        self.start_btn.grid(row=0, column=0, sticky="ew", padx=(0, 5))
        self.stop_btn = self._btn(btns, _t("panel.btn.stop"), RED,
                                  lambda: self.act("stop"))
        self.stop_btn.grid(row=0, column=1, sticky="ew", padx=5)
        self.restart_btn = self._btn(btns, _t("panel.btn.restart"), BLUE,
                                     lambda: self.act("restart"))
        self.restart_btn.grid(row=0, column=2, sticky="ew", padx=(5, 0))

        self.refresh_btn = self._btn(btns, _t("panel.btn.refresh"), CARD,
                                     self.refresh, fg=FG)
        self.refresh_btn.grid(row=1, column=0, sticky="ew", padx=(0, 5), pady=(8, 0))
        self.auto_btn = self._btn(btns, _t("panel.autostart.enable"), CARD,
                                  self.toggle_autostart, fg=FG)
        self.auto_btn.grid(row=1, column=1, sticky="ew", padx=5, pady=(8, 0))
        self.preview_btn = self._btn(btns, _t("panel.btn.preview"), CARD,
                                     self.preview, fg=FG)
        self.preview_btn.grid(row=1, column=2, sticky="ew", padx=(5, 0), pady=(8, 0))

        self.over_btn = self._btn(btns, _t("panel.overcharge.off", 90), CARD,
                                  self.toggle_overcharge, fg=FG)
        self.over_btn.grid(row=2, column=0, columnspan=2, sticky="ew",
                           padx=(0, 5), pady=(8, 0))
        self.detail_btn = self._btn(btns, _t("panel.btn.details"), CARD,
                                    self.show_battery_info, fg=FG)
        self.detail_btn.grid(row=2, column=2, sticky="ew", pady=(8, 0))

        # 语言切换：点击即在中文 / 英文之间切换（会同步通知常驻程序重绘两条显示条）
        self.lang_btn = self._btn(btns, _t("panel.btn.lang"), CARD,
                                  self.toggle_language, fg=FG)
        self.lang_btn.grid(row=3, column=0, columnspan=3, sticky="ew", pady=(8, 0))

        self.msg = tk.Label(self, text=_t("panel.hint"),
                            bg=BG, fg=SUB, font=("Microsoft YaHei UI", 9),
                            wraplength=380, justify="left")
        self.msg.pack(anchor="w", pady=(12, 14), **pad)

    def _btn(self, parent, text, color, cmd, fg=None):
        b = tk.Button(parent, text=text, command=cmd, bg=color,
                      fg=fg or "#0C1014", activebackground=color,
                      font=("Microsoft YaHei UI", 10, "bold"),
                      relief="flat", bd=0, height=2, cursor="hand2")
        return b

    # ---------- 行为 ----------
    def refresh(self):
        pids = find_overlay_pids()
        if pids:
            self.dot.configure(fg=GREEN)
            self.state_lbl.configure(text=_t("panel.state.running"))
            self.pid_lbl.configure(text=_t("panel.pid")
                                   + "、".join(str(p) for p in pids))
        else:
            self.dot.configure(fg=RED)
            self.state_lbl.configure(text=_t("panel.state.stopped"))
            self.pid_lbl.configure(text=_t("panel.pid.none"))

        on = autostart_enabled()
        self.auto_lbl.configure(
            text=_t("panel.autostart.on") if on else _t("panel.autostart.off"),
            fg=GREEN if on else SUB)        # 按钮文案表示"点击后要做的事"：已开启 → 点击可关闭
        self.auto_btn.configure(text=_t("panel.autostart.disable") if on
                                else _t("panel.autostart.enable"))

        # 防过充状态（阈值与开关存在 ds4_config.json）
        cfg = self._read_config()
        oc_on = bool(cfg.get("overcharge_enabled", True))
        pct = int(cfg.get("overcharge_pct") or 90)
        self.over_btn.configure(text=_t("panel.overcharge.on" if oc_on
                                        else "panel.overcharge.off", pct))

        # 语言按钮：显示"点击后要切换到的语言"
        self.lang_btn.configure(text=_t("panel.btn.lang"))

    # ---------- 语言切换 ----------
    def toggle_language(self):
        """在中文 / 英文之间切换，并通知常驻程序立即重绘两条显示条。"""
        import json
        global _LANG
        cfg = self._read_config()
        target = "en" if _LANG == "zh" else "zh"
        cfg["lang"] = target
        try:
            with open(self._config_path(), "w", encoding="utf-8") as f:
                json.dump(cfg, f, ensure_ascii=False, indent=2)
            # 写语言信号：常驻程序轮询到变化后立即用新语言重绘弹窗与顶栏
            with open(LANG_FILE, "w", encoding="utf-8") as f:
                f.write("%s %.6f\n" % (target, time.time()))
        except Exception as e:
            self._note(_t("panel.note.cfg_fail", e), RED)
            return
        _LANG = target
        self._retranslate()
        self.refresh()
        self._note(_t("panel.note.lang",
                      _t("panel.lang.en" if target == "en" else "panel.lang.zh")),
                   GREEN)

    def _retranslate(self):
        """按当前语言重刷面板上所有静态文案。"""
        try:
            self.title(_t("panel.window", _t("panel.window_name"), __version__))
            self.app_lbl.configure(text=_t("panel.app"))
            self.start_btn.configure(text=_t("panel.btn.start"))
            self.stop_btn.configure(text=_t("panel.btn.stop"))
            self.restart_btn.configure(text=_t("panel.btn.restart"))
            self.refresh_btn.configure(text=_t("panel.btn.refresh"))
            self.preview_btn.configure(text=_t("panel.btn.preview"))
            self.detail_btn.configure(text=_t("panel.btn.details"))
            self.lang_btn.configure(text=_t("panel.btn.lang"))
            self.msg.configure(text=_t("panel.hint"))
        except Exception:
            pass

    # ---------- 配置（防过充） ----------
    @staticmethod
    def _config_path():
        return os.path.join(BASE, "ds4_config.json")

    def _read_config(self):
        import json
        try:
            with open(self._config_path(), "r", encoding="utf-8") as f:
                d = json.load(f) or {}
        except Exception:
            d = {}
        d.setdefault("overcharge_enabled", True)
        d.setdefault("overcharge_pct", 90)
        return d

    def toggle_overcharge(self):
        import json
        cfg = self._read_config()
        cfg["overcharge_enabled"] = not bool(cfg.get("overcharge_enabled", True))
        try:
            with open(self._config_path(), "w", encoding="utf-8") as f:
                json.dump(cfg, f, ensure_ascii=False, indent=2)
        except Exception as e:
            self._note(_t("panel.note.cfg_fail", e), RED)
            return
        self.refresh()
        if cfg["overcharge_enabled"]:
            self._note(_t("panel.note.oc_on", int(cfg["overcharge_pct"])), GREEN)
        else:
            self._note(_t("panel.note.oc_off"), YELLOW)

    def show_battery_info(self):
        """电池详情：读取常驻程序写下的最新实测数据。

        DS4 不提供 mAh 容量/健康度（硬件只按 10% 一档上报），
        因此这里只展示**可实测的真实值**（电量 / 原始档位 / 充电状态 / 连接方式 / 时长估算），
        不做容量估算。
        """
        import json
        path = os.path.join(BASE, "ds4_battery_info.json")
        try:
            with open(path, "r", encoding="utf-8") as f:
                d = json.load(f)
        except Exception:
            self._note(_t("panel.info.no_data"), YELLOW)
            return
        pct = d.get("pct")
        if pct is None:
            self._note(_t("panel.info.no_level"), YELLOW)
            return
        if d.get("full"):
            state = _t("panel.info.state.full")
        elif d.get("charging"):
            state = _t("panel.info.state.charging")
        else:
            state = _t("panel.info.state.discharging")
        conn = _t("panel.info.conn.usb") if d.get("cable") else _t("panel.info.conn.bt")
        # 两个时间都常显：续航（放电速率）+ 充满时长（充电速率）
        rem = d.get("est_remaining")
        full = d.get("est_full")
        if d.get("full"):
            full = _t("time.full")
        rem_line = _t("panel.info.remain",
                      (_t("panel.info.remain_val", rem) if rem
                       else _t("panel.info.remain_none")))
        if d.get("est_remaining_cached") and rem:
            rem_line += _t("panel.info.remain_cached")
        full_line = _t("panel.info.full_line",
                       full if full == _t("time.full") else
                       (_t("panel.info.full_val", full) if full
                        else _t("panel.info.full_none")))
        note = d.get("est_note")
        lvl = d.get("raw_level")
        warn = ""
        if d.get("cable") and lvl == 14:
            warn = _t("panel.info.warn14")
        elif d.get("cable") and lvl == 15:
            warn = _t("panel.info.warn15")
        self._note(
            (_t("panel.info.title") + "\n"
             + _t("panel.info.level", int(pct)) + "\n"
             + _t("panel.info.raw",
                  d.get("raw_level") if d.get("raw_level") is not None else "—")
             + "\n"
             + _t("panel.info.charging", state) + "\n"
             + _t("panel.info.conn", conn) + "\n"
             + rem_line + "\n"
             + full_line + "\n"
             + _t("panel.info.time", d.get("updated") or "—",
                  ("\n  ※ %s" % note) if note else "", warn)),
            GREEN)

    def _note(self, text, color=SUB):
        self.msg.configure(text=text, fg=color)

    # ---------- 启停控制（自包含，不依赖 ds4_manager） ----------
    @staticmethod
    def start_overlay():
        """启动常驻程序（已在运行则由其单实例保护自行退出）。"""
        if find_overlay_pids():
            return False
        subprocess.Popen(target_cmd(), close_fds=True)
        return True

    @staticmethod
    def stop_overlay():
        """停止常驻程序：只结束精确匹配到的实例。"""
        pids = find_overlay_pids()
        for pid in pids:
            subprocess.run(["taskkill", "/F", "/PID", str(pid)],
                           capture_output=True)
        return len(pids)

    def act(self, what):
        try:
            if what == "start":
                self.start_overlay()
                self._note(_t("panel.note.started"), GREEN)
            elif what == "stop":
                n = self.stop_overlay()
                self._note(_t("panel.note.stopped", n) if n
                           else _t("panel.note.not_running"), RED)
            elif what == "restart":
                self.stop_overlay()
                time.sleep(1.2)
                self.start_overlay()
                self._note(_t("panel.note.restarted"), BLUE)
        except Exception as e:
            self._note(_t("panel.note.error", e), RED)
        self.after(600, self.refresh)

    def toggle_autostart(self):
        ok, text = set_autostart(not autostart_enabled())
        self._note(text, GREEN if ok else RED)
        self.refresh()

    def preview(self):
        """无需手柄，预览弹窗与顶部电量横条外观。"""
        try:
            subprocess.Popen(target_cmd(["--preview", "66"]), close_fds=True)
            self.after(1200, lambda: subprocess.Popen(
                target_cmd(["--preview-bar", "66"]), close_fds=True))
            self._note(_t("panel.note.preview"), BLUE)
        except Exception as e:
            self._note(_t("panel.note.preview_fail", e), RED)


# ---------- 单实例保护 ----------
# 面板是可反复双击打开的 GUI，若不限制会出现多个窗口（用户反馈：
# "切换语言后打开了一个新的控制面板窗口" —— 实为重复启动所致）。
# 与主程序一样用命名互斥体：已有实例则本次退出，并把已有窗口置前。
_PANEL_MUTEX = None
_PANEL_MUTEX_NAME = "Global\\DS4BatteryOverlayPanel_SingleInstance"


def _single_instance_ok():
    """返回 True 表示本实例可以继续；False 表示已有实例在运行。"""
    global _PANEL_MUTEX
    try:
        import ctypes
        k32 = ctypes.windll.kernel32
        k32.CreateMutexW.restype = ctypes.c_void_p
        k32.CreateMutexW.argtypes = [ctypes.c_void_p, ctypes.c_bool,
                                     ctypes.c_wchar_p]
        k32.GetLastError.restype = ctypes.c_ulong
        _PANEL_MUTEX = k32.CreateMutexW(None, False, _PANEL_MUTEX_NAME)
        ERROR_ALREADY_EXISTS = 183
        if k32.GetLastError() == ERROR_ALREADY_EXISTS:
            _focus_existing_panel()
            return False
        return True
    except Exception:
        return True          # 互斥体不可用时不阻碍使用


def _focus_existing_panel():
    """把已在运行的面板窗口置前（给重复启动的用户一个明确反馈）。"""
    try:
        import ctypes
        u32 = ctypes.windll.user32
        u32.FindWindowW.restype = ctypes.c_void_p
        u32.FindWindowW.argtypes = [ctypes.c_wchar_p, ctypes.c_wchar_p]
        # Tk 顶层窗口类名固定为 TkTopLevel，标题前缀固定；按标题找不到时
        # 退化为枚举可见窗口并匹配标题里的版本串
        for cls in ("TkTopLevel", None):
            for title in (None,):
                h = u32.FindWindowW(cls, title)
                if h:
                    buf = ctypes.create_unicode_buffer(256)
                    u32.GetWindowTextW(ctypes.c_void_p(h), buf, 256)
                    if "DS4" in buf.value and ("控制面板" in buf.value
                                               or "Control Panel" in buf.value):
                        u32.ShowWindow(ctypes.c_void_p(h), 9)      # SW_RESTORE
                        u32.SetForegroundWindow(ctypes.c_void_p(h))
                        return
    except Exception:
        pass


if __name__ == "__main__":
    if not _single_instance_ok():
        raise SystemExit(0)
    Panel().mainloop()
