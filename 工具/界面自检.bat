@echo off
cd /d "%~dp0"
"%~dp0..\.venv\Scripts\python.exe" -B "%~dp0ui_check.py"
echo.
if errorlevel 1 (echo [FAILED] see the error above) else (echo [PASSED])
pause