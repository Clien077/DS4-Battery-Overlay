# -*- coding: utf-8 -*-
"""
DS4 电量提示 · 快捷管理
======================
功能：启动 / 停止 / 重启 常驻程序 ds4_battery_overlay.py，并查看运行状态。

用法：
  双击「管理DS4电量提示.bat」进入交互菜单，或命令行直接执行：
    py -3 ds4_manager.py           交互菜单
    py -3 ds4_manager.py --status  只查看状态
    py -3 ds4_manager.py --start   启动（已在运行则跳过）
    py -3 ds4_manager.py --stop    停止
    py -3 ds4_manager.py --restart 重启
"""
import os
import subprocess
import sys
import time

# ---- 版本号：与主程序保持一致（升级时同步修改三处同名常量）----
__version__ = "1.2.6"
APP_NAME = "DS4 电量提示"

# 程序目录：打包(exe)后用 exe 所在目录，开发(.py)后用脚本所在目录
if getattr(sys, "frozen", False):
    BASE = os.path.dirname(sys.executable)
else:
    BASE = os.path.dirname(os.path.abspath(__file__))

# 启动目标：打包模式下调用同目录 exe；开发模式下用 pythonw + 脚本
SCRIPT_PY = os.path.join(BASE, "ds4_battery_overlay.py")
SCRIPT_EXE = os.path.join(BASE, "ds4_battery_overlay.exe")
MATCH = "ds4_battery_overlay"


def target_command():
    """返回要启动的程序命令（[exe] 或 [pythonw, script]）。"""
    if getattr(sys, "frozen", False) or os.path.exists(SCRIPT_EXE):
        return [SCRIPT_EXE]
    return [pythonw_exe(), SCRIPT_PY]


def pythonw_exe():
    """开发模式：用 pythonw.exe 无窗口后台启动（与开机自启同款）。"""
    exe = sys.executable
    if exe.lower().endswith("python.exe"):
        return exe[: -len("python.exe")] + "pythonw.exe"
    return exe


def find_pids():
    """精确匹配常驻程序进程。

    只认"进程名是 ds4_battery_overlay(.exe)"，或"进程名是 python* 且命令行
    以本程序脚本结尾"这两种情况。

    旧实现只判断"命令行里包含 ds4_battery_overlay 字符串"，会把
    PowerShell 包装进程、导入本模块的调试脚本、甚至自身都算成实例
    （实测曾把 1 个实例误报为 4 个），进而导致状态显示错误、
    "停止"可能误伤无关进程。
    """
    # 单引号包裹脚本、双引号包裹脚本：两种形式都要能识别，且不能匹配到别的脚本名
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
        return [int(line.strip()) for line in out.stdout.splitlines()
                if line.strip().isdigit()]
    except Exception:
        return []


def show_status():
    pids = find_pids()
    if pids:
        print(f"[状态] 运行中：{len(pids)} 个实例  PID={pids}")
        logp = os.path.join(BASE, "ds4_battery_overlay.log")
        if os.path.exists(logp):
            try:
                with open(logp, "r", encoding="utf-8",
                          errors="replace") as f:
                    lines = [l for l in f.read().splitlines() if l.strip()]
                if lines:
                    print(f"[状态] 最近日志：{lines[-1]}")
            except Exception:
                pass
    else:
        print("[状态] 未运行")
    return pids


def do_start():
    if find_pids():
        print("[启动] 已在运行，跳过")
        return
    cmd = target_command()
    if not os.path.exists(cmd[0]):
        print(f"[启动] 找不到程序：{cmd[0]}")
        return
    subprocess.Popen(cmd, cwd=BASE, close_fds=True)
    print("[启动] 已启动，等待 2 秒确认……")
    time.sleep(2)
    show_status()


def do_stop():
    pids = find_pids()
    if not pids:
        print("[停止] 本来就没有在运行")
        return
    for pid in pids:
        subprocess.run(["taskkill", "/PID", str(pid), "/F"],
                       capture_output=True, text=True)
    time.sleep(1)
    left = find_pids()
    if left:
        print(f"[停止] 仍有残留 PID={left}")
    else:
        print("[停止] 已全部停止")


def do_restart():
    do_stop()
    print("[重启] 3 秒后重新启动……")
    time.sleep(3)
    do_start()


def menu():
    while True:
        print()
        print("=" * 46)
        print("  DS4 电量提示 · 快捷管理")
        print("=" * 46)
        print("  [1] 启动程序")
        print("  [2] 停止程序")
        print("  [3] 重启程序")
        print("  [4] 查看运行状态")
        print("  [0] 退出")
        print("=" * 46)
        choice = input("  请选择：").strip()
        if choice == "1":
            do_start()
        elif choice == "2":
            do_stop()
        elif choice == "3":
            do_restart()
        elif choice == "4":
            show_status()
        elif choice == "0":
            print("  再见")
            break
        else:
            print("  无效选项，请重新输入")


if __name__ == "__main__":
    args = sys.argv[1:]
    if "--version" in args:
        print("%s v%s" % (APP_NAME, __version__))
    elif "--status" in args:
        show_status()
    elif "--start" in args:
        do_start()
    elif "--stop" in args:
        do_stop()
    elif "--restart" in args:
        do_restart()
    else:
        menu()
