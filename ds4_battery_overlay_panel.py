# -*- coding: utf-8 -*-
"""
DS4 电量提示 · 可视化控制面板
==============================
一个窗口按钮化操作常驻程序：启动 / 停止 / 重启 / 查看状态 / 开机自启 / 预览界面。

与 ds4_manager.py 的区别：ds4_manager 是命令行菜单（.bat 里选数字），
本面板是纯图形界面，双击即可操作。

运行：python ds4_battery_overlay_panel.py
打包后可放在 ds4_battery_overlay.exe 同目录使用。
"""
import os
import subprocess
import sys
import tkinter as tk

# 让本脚本无论放在哪都能 import 到同目录的 ds4_manager
BASE = os.path.dirname(os.path.abspath(__file__))
if BASE not in sys.path:
    sys.path.insert(0, BASE)

import ds4_manager as mgr  # noqa: E402

# ---- 版本号：与主程序保持一致（升级时同步修改三处同名常量）----
__version__ = "1.2.6"
APP_NAME = "DS4 电量提示"

EXE = mgr.SCRIPT_EXE
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
    cmd = mgr.target_command()
    return cmd + list(extra or [])


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
            cmd = '"%s"' % (EXE if os.path.exists(EXE) else sys.executable)
            subprocess.run([EXE if os.path.exists(EXE) else sys.executable,
                            "--autostart"], capture_output=True, timeout=20)
            import winreg
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY, 0,
                                winreg.KEY_SET_VALUE) as k:
                winreg.SetValueEx(k, AUTOSTART_NAME, 0, winreg.REG_SZ, cmd)
            return True, "已开启开机自启"
        else:
            exe = EXE if os.path.exists(EXE) else sys.executable
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
        pids = mgr.find_pids()
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
        return os.path.join(mgr.BASE, "ds4_config.json")

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
        path = os.path.join(mgr.BASE, "ds4_battery_info.json")
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
        self._note(
            "电池详情（实测）\n"
            "  真实电量  ：%d%%   （容量估算 %.0f mAh / 标称 %d mAh）\n"
            "  原始档位  ：%s / 15  ← 硬件按 10%% 一档上报，这是精度上限\n"
            "  充电状态  ：%s\n"
            "  连接方式  ：%s\n"
            "  数据时间  ：%s"
            % (int(pct), d.get("capacity_mah") or 0, d.get("nominal_mah") or 1000,
               d.get("raw_level") if d.get("raw_level") is not None else "—",
               state, conn, d.get("updated") or "—"),
            GREEN)

    def _note(self, text, color=SUB):
        self.msg.configure(text=text, fg=color)

    def act(self, what):
        try:
            if what == "start":
                mgr.do_start()
                self._note("已发送启动指令", GREEN)
            elif what == "stop":
                mgr.do_stop()
                self._note("已发送停止指令", RED)
            elif what == "restart":
                mgr.do_restart()
                self._note("已发送重启指令", BLUE)
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
