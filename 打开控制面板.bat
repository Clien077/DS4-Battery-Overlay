@echo off
chcp 65001 >nul
rem DS4 battery overlay visual control panel (GUI)
if exist "%~dp0ds4_panel.exe" (
  start "" "%~dp0ds4_panel.exe"
) else (
  start "" pythonw "%~dp0ds4_battery_overlay_panel.py"
)
