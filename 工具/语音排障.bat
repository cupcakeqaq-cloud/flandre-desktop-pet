@echo off
chcp 936 >nul
cd /d "%~dp0.."
if exist "data\_voice_log.txt" del "data\_voice_log.txt"
set FLANDRE_VOICE_LOG=1
echo.
echo  ===== 语音排障 =====
echo  1. 下面会启动芙兰，启动后先别急着说话
echo  2. 去你想试的地方（游戏 / 绘图软件都行），按住说话键说两句话，松开
echo  3. 如果没反应，再按住说一次
echo  4. 回来关掉芙兰，这个窗口会打出日志；把窗口截图发我就行
echo.
start "" "%~dp0..\芙兰朵露.exe"
timeout /t 3 >nul
echo  芙兰已经起来了，现在去按住说话键说话。
pause
echo.
echo  ===== data\_voice_log.txt =====
if exist "data\_voice_log.txt" (type "data\_voice_log.txt") else (echo  （没生成日志 —— 说明她压根没在听，先把设置里的开关打开）)
echo  =================================
pause
