# -*- mode: python ; coding: utf-8 -*-
# DS4 电量提示 v1.1.0 · 可视化控制面板打包规格
# onedir 布局：dist/ds4_panel/ds4_panel.exe
#              dist/ds4_panel/ds4_panel_data/（运行库）
# 依赖 src/ds4_manager.py（随包一起编译，用于复用启动/停止/状态逻辑）

import os
import sys

ROOT = os.path.dirname(os.path.abspath(SPEC))
SRC = os.path.join(ROOT, 'src')

# 面板需要 ctypes 调用 Win32 API 设置任务栏图标。_ctypes 是 C 扩展，
# 仅靠 hiddenimports 不会被收集（PyInstaller 对纯 Python 模块才有效），
# 必须把 _ctypes.pyd 与它依赖的 libffi-8.dll 显式打进运行库；
# 否则打包后 import ctypes 抛 ModuleNotFoundError: No module named '_ctypes'，
# 图标设置被静默跳过，任务栏按钮退回默认图标（实测现象）。
_PYDIR = os.path.dirname(sys.executable)
_DLLDIR = os.path.join(_PYDIR, 'DLLs')
_ctypes_bins = []
for _name in ('_ctypes.pyd', 'libffi-8.dll'):
    _p = os.path.join(_DLLDIR, _name)
    if not os.path.exists(_p):
        _p = os.path.join(_PYDIR, _name)
    if os.path.exists(_p):
        _ctypes_bins.append((_p, '.'))

a = Analysis(
    [os.path.join(SRC, 'ds4_battery_overlay_panel.py')],
    pathex=[SRC],
    binaries=_ctypes_bins,
    datas=[],
    hiddenimports=['ds4_manager', 'ctypes', '_ctypes'],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='ds4_panel',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    contents_directory='ds4_panel_data',
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name='ds4_panel',
)
