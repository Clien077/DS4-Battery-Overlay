@echo off
rem Disable autostart (packaged EXE version)
"%~dp0ds4_battery_overlay.exe" --no-autostart
echo Autostart disabled. / Yi qu xiao kai ji zi qi.
timeout /t 3 >nul
exit /b 0
