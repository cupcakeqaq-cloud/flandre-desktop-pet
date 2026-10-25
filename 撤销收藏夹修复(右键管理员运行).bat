@echo off
chcp 936 >nul
title 撤销收藏夹修复（需要以管理员身份运行）

net session >nul 2>&1
if %errorlevel% neq 0 (
  echo.
  echo   [!] 请右键这个文件，选「以管理员身份运行」。
  echo.
  pause
  exit /b 1
)

set "EXE=%~dp0芙兰朵露.exe"
if not exist "%EXE%" (
  echo   [!] 没找到 芙兰朵露.exe，请把这个脚本放在程序文件夹里再运行。
  pause
  exit /b 1
)

echo ============================================================
echo  把 芙兰朵露.exe 的标签改回「低完整性」，也就是出厂状态。
echo  只在一种情况下用：换新 exe 时提示拒绝访问、旧文件换不掉。
echo  改回去之后收藏夹又会「动不了」，更新完记得再跑一次修复。
echo ============================================================
echo.
icacls "%EXE%" /setintegritylevel Low
if errorlevel 1 (
  echo.
  echo   [失败] 改不动。确认是右键「以管理员身份运行」打开的。
  pause
  exit /b 1
)
echo.
echo  [OK] 已改回低完整性，现在可以让程序更新 exe 了。
pause