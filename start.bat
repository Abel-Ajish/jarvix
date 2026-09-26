@echo off
REM jarvix launcher

set PROJECT_DIR=%~dp0
set VENV_DIR=%PROJECT_DIR%\.venv

if not exist "%VENV_DIR%\Scripts\python.exe" (
    echo ERROR: Virtual environment not found. Run install.bat first.
    pause
    exit /b 1
)

echo Starting jarvix...
"%VENV_DIR%\Scripts\python" -m jarvix

if %errorlevel% neq 0 (
    echo.
    echo jarvix exited with code %errorlevel%
    pause
)