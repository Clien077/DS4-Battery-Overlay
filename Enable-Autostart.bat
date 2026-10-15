@echo off
rem Enable autostart on Windows logon (packaged EXE version)
"%~dp0ds4_battery_overlay.exe" --autostart
echo Autostart enabled. / Yi kai qi kai ji zi qi.
timeout /t 3 >nul
exit /b 0
