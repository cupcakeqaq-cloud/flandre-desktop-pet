@echo off
chcp 65001 >nul
title Close SmartScreen "Check apps and files"

net session >nul 2>&1
if %errorlevel% neq 0 (
  echo.
  echo [!] Please run this file AS ADMINISTRATOR.
  echo     Right-click it  -^>  "Run as administrator"
  echo.
  pause
  exit /b 1
)

echo ============================================================
echo  This will turn OFF  "Check apps and files"  (SmartScreen)
echo  for the WHOLE machine, for the CURRENT USER settings UI.
echo.
echo  Effect : no more "Windows protected your PC" popups,
echo           not for this app, but for ANY unsigned exe.
echo  Risk   : lower security. Malware downloaded later will
echo           also be allowed to run with less warning.
echo.
echo  You can turn it back on any time in Windows Security.
echo ============================================================
echo.
set /p ok=Type YES to continue:
if /i not "%ok%"=="YES" (
  echo Cancelled.
  pause
  exit /b 0
)

echo.
echo [1/2] Write SmartScreenEnabled = Off
reg add "HKLM\SOFTWARE\Microsoft\Windows\CurrentVersion\Explorer" /v SmartScreenEnabled /t REG_SZ /d Off /f

echo [2/2] Restart Explorer so the change takes effect
taskkill /f /im explorer.exe >nul 2>&1
start "" explorer.exe

echo.
echo Done. Try launching the pet exe now.
echo If it still warns, reboot once, or open
echo   Windows Security - App and browser control - Reputation-based protection
echo and turn "Check apps and files" off there as well.
echo.
pause
