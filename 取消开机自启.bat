@echo off
chcp 65001 >nul
rem Disable autostart (packaged EXE version)
"%~dp0ds4_battery_overlay.exe" --no-autostart
pause
