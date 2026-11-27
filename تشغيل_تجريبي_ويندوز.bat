@echo off
chcp 65001 >nul
setlocal
cd /d "%~dp0"

echo ==========================================
echo   Student Affairs - Windows Preview
echo ==========================================
echo.

where py >nul 2>nul
if errorlevel 1 (
  echo ERROR: Python Launcher not found.
  echo Install Python 3.12 or 3.11 and enable "Add Python to PATH".
  pause
  exit /b 1
)

if not exist ".venv\Scripts\python.exe" (
  echo Creating virtual environment...
  py -3.12 -m venv .venv 2>nul
  if errorlevel 1 py -3.11 -m venv .venv 2>nul
  if errorlevel 1 py -3 -m venv .venv
  if errorlevel 1 (
    echo ERROR: Could not create virtual environment. Install Python 3.11 or 3.12.
    pause
    exit /b 1
  )
)

call ".venv\Scripts\activate.bat"
if errorlevel 1 (
  echo ERROR: Could not activate virtual environment.
  pause
  exit /b 1
)

python -m pip install --upgrade pip
if errorlevel 1 goto :error
python -m pip install "Django>=5.1,<6.0" "openpyxl>=3.1" "whitenoise>=6.8"
if errorlevel 1 goto :error

set DEBUG=1
set SECRET_KEY=local-preview-only-key-do-not-use-in-production-2026
set ALLOWED_HOSTS=localhost,127.0.0.1,0.0.0.0
set TIME_ZONE=Africa/Cairo

echo.
echo Applying database migrations (local SQLite preview)...
python manage.py migrate
if errorlevel 1 goto :error

echo.
echo Create the first administrator account.
python manage.py createsuperuser
if errorlevel 1 (
  echo Admin creation was skipped or failed. You can run it later with:
  echo .venv\Scripts\python.exe manage.py createsuperuser
)

echo.
echo Preview server is starting.
echo On this computer: http://127.0.0.1:8000
echo From another LAN computer: http://SERVER-IP:8000
echo Stop the server with CTRL+C.
echo NOTE: This is a preview using SQLite and Django development server.
echo Do NOT use this mode for official multi-user production operation.
echo.
python manage.py runserver 0.0.0.0:8000
goto :eof

:error
echo.
echo Setup failed. Read the error above, check your internet/package cache,
echo then run this file again.
pause
exit /b 1
