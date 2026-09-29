@echo off
chcp 65001 >nul
rem Enable autostart (packaged EXE version)
"%~dp0ds4_battery_overlay.exe" --autostart
pause
