@echo off
rem Subset NotoSansSC-VF.ttf down to the characters the project actually uses
rem + all GB2312 hanzi, keeping the variable weight axis. Run this after you
rem add new lines to data\dialogue.json, otherwise new characters show as tofu.
cd /d "%~dp0"
"%~dp0..\.venv\Scripts\python.exe" -B "%~dp0font_subset.py"
echo.
if errorlevel 1 (echo [FAILED] see the error above) else (echo [PASSED])
pause
