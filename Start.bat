@echo off
setlocal
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  echo Run Setup.bat first.
  pause
  exit /b 1
)
echo Result Desk opens at http://127.0.0.1:8000
echo Keep this terminal open while using the website. Press Ctrl+C to stop.
".venv\Scripts\python.exe" -m result_automation %*
if errorlevel 1 pause
