@echo off
chcp 65001 >nul
title Speed up Flandre startup - add Windows Defender exclusion

net session >nul 2>&1
if %errorlevel% neq 0 (
  echo.
  echo [!] Please run this file AS ADMINISTRATOR.
  echo     Right-click it  -^>  "Run as administrator"
  echo.
  pause
  exit /b 1
)

set "TARGET=%~dp0"

echo ============================================================
echo  Flandre starts slowly on the FIRST launch after an update
echo  because Windows Defender scans the whole 55 MB program
echo  folder every time the exe changes.
echo.
echo  This adds ONE folder to the Defender exclusion list:
echo    %TARGET%
echo.
echo  Effect : first launch after an update stops taking 1.5-3.5 s
echo  Risk   : files in this folder are no longer scanned.
echo           Only do this for a folder you trust.
echo.
echo  Undo any time with:
echo    Remove-MpPreference -ExclusionPath "%TARGET%"
echo ============================================================
echo.

powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "try { Add-MpPreference -ExclusionPath '%TARGET%' -ErrorAction Stop; Write-Host '[OK] exclusion added' -ForegroundColor Green } catch { Write-Host ('[FAIL] ' + $_.Exception.Message) -ForegroundColor Red }"

echo.
echo  Current exclusions:
powershell -NoProfile -Command "(Get-MpPreference).ExclusionPath"
echo.
pause
