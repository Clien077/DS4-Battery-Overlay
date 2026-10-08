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
__version__ = "1.2.7"
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
        所以这里展示可实测的真实值，并给出基于标称容量的容量估算。
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
        # 时长估算：放电看"还能用多久"，充电看"还要充多久"（数据不足显示估算中）
        if d.get("full"):
            est = "充电时长：已充满"
        elif d.get("charging") or d.get("cable"):
            est = "充电时长：还需 %s" % (d.get("est_full") or "估算中")
        else:
            est = "预计续航：还能用 %s" % (d.get("est_remaining") or "估算中")
        note = d.get("est_note")
        self._note(
            "电池详情（实测）\n"
            "  真实电量  ：%d%%   （容量估算 %.0f mAh / 标称 %d mAh）\n"
            "  原始档位  ：%s / 15  ← 硬件按 10%% 一档上报，这是精度上限\n"
            "  充电状态  ：%s\n"
            "  连接方式  ：%s\n"
            "  %s\n"
            "  数据时间  ：%s%s"
            % (int(pct), d.get("capacity_mah") or 0, d.get("nominal_mah") or 1000,
               d.get("raw_level") if d.get("raw_level") is not None else "—",
               state, conn, est, d.get("updated") or "—",
               ("\n  ※ %s" % note) if note else ""),
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
