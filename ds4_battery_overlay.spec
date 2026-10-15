# -*- mode: python ; coding: utf-8 -*-
# DS4 电量提示 v1.0.2 · 常驻主程序打包规格
# onedir 布局：dist/ds4_battery_overlay/ds4_battery_overlay.exe
#              dist/ds4_battery_overlay/ds4_overlay_data/（运行库，与 v1.0.1 一致）

import os

ROOT = os.path.dirname(os.path.abspath(SPEC))
SRC = os.path.join(ROOT, 'src')

a = Analysis(
    [os.path.join(SRC, 'ds4_battery_overlay.py')],
    pathex=[SRC],
    binaries=[],
    datas=[],
    hiddenimports=[],
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
    name='ds4_battery_overlay',
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
    contents_directory='ds4_overlay_data',
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name='ds4_battery_overlay',
)
