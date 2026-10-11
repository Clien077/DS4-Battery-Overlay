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

# ---- 版本号：与主程序保持一致（升级时同步修改同名常量）----
__version__ = "1.2.10"


# ---- 手柄图标（base64 内嵌，避免依赖外部文件；打包后同样可用）----
_GAMEPAD_ICO_B64 = (
    "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"
    "tu1ntyJXTgAAAABJRU5ErkJggg=="
)

_gp_ico_path = None


def _apply_gamepad_icon(win):
    """把窗口左上角图标换成手柄样式（失败静默，不影响功能）。"""
    global _gp_ico_path
    try:
        import base64 as _b64
        import os as _os
        import tempfile
        if _gp_ico_path is None:
            d = _os.path.join(tempfile.gettempdir(), "ds4_battery_overlay")
            _os.makedirs(d, exist_ok=True)
            _gp_ico_path = _os.path.join(d, "ds4_gamepad.ico")
            with open(_gp_ico_path, "wb") as f:
                f.write(_b64.b64decode(_GAMEPAD_ICO_B64))
        win.iconbitmap(_gp_ico_path)
        return True
    except Exception:
        return False
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
            return True, "已开启开机自启"
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
            return True, "已取消开机自启"
    except Exception as e:
        return False, "操作失败：%s" % e


class Panel(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("%s v%s · 控制面板" % (APP_NAME, __version__))
        self.configure(bg=BG)
        self.resizable(False, False)
        _apply_gamepad_icon(self)          # 左上角图标 -> 手柄样式
        self._build()
        self.refresh()

    # ---------- 界面 ----------
    def _build(self):
        pad = dict(padx=16)

        tk.Label(self, text="DS4 电量提示", bg=BG, fg=FG,
                 font=("Microsoft YaHei UI", 14, "bold")).pack(anchor="w", pady=(14, 0), **pad)

        card = tk.Frame(self, bg=CARD, highlightthickness=0)
        card.pack(fill="x", pady=(10, 12), **pad)

        self.dot = tk.Label(card, text="●", bg=CARD, fg=SUB, font=("Segoe UI", 16))
        self.dot.grid(row=0, column=0, padx=(14, 6), pady=(12, 2), sticky="w")
        self.state_lbl = tk.Label(card, text="检测中…", bg=CARD, fg=FG,
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

        self._btn(btns, "启动", GREEN, lambda: self.act("start")).grid(
            row=0, column=0, sticky="ew", padx=(0, 5))
        self._btn(btns, "停止", RED, lambda: self.act("stop")).grid(
            row=0, column=1, sticky="ew", padx=5)
        self._btn(btns, "重启", BLUE, lambda: self.act("restart")).grid(
            row=0, column=2, sticky="ew", padx=(5, 0))

        self._btn(btns, "刷新状态", CARD, self.refresh, fg=FG).grid(
            row=1, column=0, sticky="ew", padx=(0, 5), pady=(8, 0))
        self.auto_btn = self._btn(btns, "开机自启：开", CARD, self.toggle_autostart, fg=FG)
        self.auto_btn.grid(row=1, column=1, sticky="ew", padx=5, pady=(8, 0))
        self._btn(btns, "预览外观", CARD, self.preview, fg=FG).grid(
            row=1, column=2, sticky="ew", padx=(5, 0), pady=(8, 0))

        self.over_btn = self._btn(btns, "防过充：开", CARD, self.toggle_overcharge,
                                  fg=FG)
        self.over_btn.grid(row=2, column=0, columnspan=2, sticky="ew",
                           padx=(0, 5), pady=(8, 0))
        self._btn(btns, "电池详情", CARD, self.show_battery_info,
                  fg=FG).grid(row=2, column=2, sticky="ew", pady=(8, 0))

        self.msg = tk.Label(self, text="提示：右键点击弹出的电量窗可退出常驻程序",
                            bg=BG, fg=SUB, font=("Microsoft YaHei UI", 9),
                            wraplength=380, justify="left")
        self.msg.pack(anchor="w", pady=(12, 14), **pad)
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
            self.state_lbl.configure(text="运行中")
            self.pid_lbl.configure(text="进程 PID：" + "、".join(str(p) for p in pids))
        else:
            self.dot.configure(fg=RED)
            self.state_lbl.configure(text="未运行")
            self.pid_lbl.configure(text="进程 PID：—")

        on = autostart_enabled()
        self.auto_lbl.configure(
            text="开机自启：" + ("已开启" if on else "未开启"),
            fg=GREEN if on else SUB)
        # 按钮文案表示"点击后要做的事"：已开启 → 点击可关闭
        self.auto_btn.configure(text="关闭开机自启" if on else "开启开机自启")

        # 防过充状态（阈值与开关存在 ds4_config.json）
        cfg = self._read_config()
        oc_on = bool(cfg.get("overcharge_enabled", True))
        self.over_btn.configure(text=("关闭防过充" if oc_on else "开启防过充")
                                + "(%d%%)" % int(cfg.get("overcharge_pct") or 90))

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
            self._note("写入配置失败：%s" % e, RED)
            return
        self.refresh()
        if cfg["overcharge_enabled"]:
            self._note("防过充已开启：插着线且电量达到 %d%% 时弹窗提醒拔线\n"
                       "（软件无法切断充电电路，只能提醒）"
                       % int(cfg["overcharge_pct"]), GREEN)
        else:
            self._note("防过充已关闭", YELLOW)

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
            self._note("暂无电池数据：请先启动常驻程序并连接手柄"
                       "（数据文件：ds4_battery_info.json）", YELLOW)
            return
        pct = d.get("pct")
        if pct is None:
            self._note("手柄已连接但未读到电量：可能被其它软件独占，"
                       "或刚连接尚未出数", YELLOW)
            return
        if d.get("full"):
            state = "已充满"
        elif d.get("charging"):
            state = "充电中"
        else:
            state = "放电中（无线）"
        conn = "USB 有线" if d.get("cable") else "蓝牙无线"
        # 两个时间都常显：续航（放电速率）+ 充满时长（充电速率）
        rem = d.get("est_remaining")
        full = d.get("est_full")
        if d.get("full"):
            full = "已充满"
        rem_line = "预计续航  ：%s" % (
            ("还能用 %s" % rem) if rem else "估算中（跨过一档后自动出数）")
        if d.get("est_remaining_cached") and rem:
            rem_line += "   ← 按上次无线速率推算"
        full_line = "预计充满  ：%s" % (
            full if full == "已充满" else
            (("还需 %s" % full) if full else "估算中（插线充电跨档后自动出数）"))
        note = d.get("est_note")
        lvl = d.get("raw_level")
        warn = ""
        if d.get("cable") and lvl == 14:
            warn = "\n  ※ 手柄报「电压/温度异常，已暂停充电」（档位 14），故不显示百分比"
        elif d.get("cable") and lvl == 15:
            warn = "\n  ※ 手柄报「充电故障」（档位 15），故不显示百分比"
        self._note(
            "电池详情（实测）\n"
            "  真实电量  ：%d%%\n"
            "  原始档位  ：%s / 15  ← 硬件按 10%% 一档上报，这是精度上限\n"
            "  充电状态  ：%s\n"
            "  连接方式  ：%s\n"
            "  %s\n"
            "  %s\n"
            "  数据时间  ：%s%s%s"
            % (int(pct),
               d.get("raw_level") if d.get("raw_level") is not None else "—",
               state, conn, rem_line, full_line, d.get("updated") or "—",
               ("\n  ※ %s" % note) if note else "", warn),
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
                self._note("已启动常驻程序", GREEN)
            elif what == "stop":
                n = self.stop_overlay()
                self._note("已停止 %d 个实例" % n if n else "程序本来就没在运行", RED)
            elif what == "restart":
                self.stop_overlay()
                time.sleep(1.2)
                self.start_overlay()
                self._note("已重启常驻程序", BLUE)
        except Exception as e:
            self._note("操作出错：%s" % e, RED)
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
            self._note("已预览 66% 弹窗 + 顶部横条（观察屏幕底部/顶部）", BLUE)
        except Exception as e:
            self._note("预览失败：%s" % e, RED)


if __name__ == "__main__":
    Panel().mainloop()
