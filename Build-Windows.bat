@echo off
setlocal
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  echo Run Setup.bat first.
  pause
  exit /b 1
)
".venv\Scripts\python.exe" -m pip install ".[dev]"
if errorlevel 1 goto failed
".venv\Scripts\python.exe" scripts\build_windows.py
if errorlevel 1 goto failed
echo Build complete: dist\ResultDesk\ResultDesk.exe
echo Copy the whole ResultDesk folder to another Windows 10 64-bit computer.
pause
exit /b 0
:failed
echo Build failed. See the error above.
pause
exit /b 1
