@echo off
setlocal
cd /d "%~dp0"
echo Setting up Result Desk for Windows. Initial setup requires an internet connection.
py -3.11 -c "import struct; assert struct.calcsize('P') == 8" >nul 2>&1
if errorlevel 1 (
  echo Install Python 3.11 64-bit from python.org with the Python launcher and Tcl/Tk enabled.
  echo Then run Setup.bat again.
  pause
  exit /b 1
)
if not exist ".venv\Scripts\python.exe" py -3.11 -m venv .venv
if errorlevel 1 goto failed
".venv\Scripts\python.exe" -m pip install --upgrade pip
if errorlevel 1 goto failed
".venv\Scripts\python.exe" -m pip install -r requirements-windows.lock
if errorlevel 1 goto failed
".venv\Scripts\python.exe" -m pip install --no-deps -e .
if errorlevel 1 goto failed
".venv\Scripts\python.exe" scripts\check_offline.py
if errorlevel 1 goto failed
echo Setup complete. Double-click Start.bat to open Result Desk.
pause
exit /b 0
:failed
echo Setup failed. See the error above.
pause
exit /b 1
