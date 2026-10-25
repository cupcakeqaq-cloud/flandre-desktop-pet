@echo off
chcp 936 >nul
cd /d "%~dp0"

if not exist "芙兰朵露_发布包.zip" (
  echo 没找到 芙兰朵露_发布包.zip。先让程序员跑一次 工具\打发布包.py 再来。
  echo.
  pause
  exit /b 1
)

copy /y "芙兰朵露_发布包.zip" "%USERPROFILE%\Desktop\芙兰朵露_发布包.zip" >nul
if errorlevel 1 (
  echo 拷不过去。桌面上要是有同名文件被占着，先关掉再试。
) else (
  echo 好了，桌面上有个 芙兰朵露_发布包.zip，解压出来就能玩。
)
echo.
pause
