@echo off
rem Start ProjectHub on Windows. Uses the project's own Python environment
rem directly, so it works without activating the venv (PowerShell's
rem execution policy often blocks Activate.ps1).

cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
    echo Setting up the Python environment, this takes a minute...
    python -m venv .venv || goto :error
)

".venv\Scripts\python.exe" -m pip install --quiet --disable-pip-version-check -r requirements.txt || goto :error

echo.
echo ProjectHub is starting. Open http://127.0.0.1:8000 in your browser.
echo Press Ctrl+C to stop.
echo.
".venv\Scripts\python.exe" -m uvicorn backend.api.main:app --reload --port 8000
goto :eof

:error
echo.
echo Setup failed. Make sure Python 3.10 or newer is installed and on your PATH.
pause
