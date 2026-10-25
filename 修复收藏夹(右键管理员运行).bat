@echo off
chcp 936 >nul
title 修复收藏夹（需要以管理员身份运行）

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
echo  拖动文件到芙兰身上，她说「动不了」、收藏夹里空空的？
echo.
echo  原因是程序文件夹带了「低完整性」标签：芙兰的进程权限比桌面
echo  上的文件低，能复制进收藏夹、却删不掉原件，于是整次回滚。
echo.
echo  这个脚本只改一样东西——给 芙兰朵露.exe 打上「中完整性」。
echo  程序、贴图、收藏夹里的东西一律不动。
echo ============================================================
echo.
echo  改之前：
icacls "%EXE%"
echo.
icacls "%EXE%" /setintegritylevel Medium
if errorlevel 1 (
  echo.
  echo   [失败] 改不动。确认是右键「以管理员身份运行」打开的。
  pause
  exit /b 1
)
echo.
echo  改之后（不应该再看到低强制级别）：
icacls "%EXE%"
echo.
echo  [OK] 关掉正在跑的芙兰，重新双击 芙兰朵露.exe，再拖个文件试试。
echo.
echo  注意：每次更新 exe 之后要再跑一次这个脚本。
echo  更新前要是发现换不掉 exe，先跑一次「撤销收藏夹修复」。
pause