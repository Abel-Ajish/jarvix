@echo off
REM jarvix installer for Windows
REM Creates virtual environment, installs dependencies, sets up folders

set PROJECT_DIR=%~dp0
set VENV_DIR=%PROJECT_DIR%\.venv

echo =========================================
echo  jarvix Installation
echo =========================================
echo.

REM Check Python
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo ERROR: Python not found. Please install Python 3.12+ from python.org
    pause
    exit /b 1
)

echo [1/5] Creating virtual environment...
python -m venv "%VENV_DIR%"
if %errorlevel% neq 0 (
    echo ERROR: Failed to create virtual environment
    pause
    exit /b 1
)

echo [2/5] Upgrading pip...
"%VENV_DIR%\Scripts\pip" install --upgrade pip

echo [3/5] Installing dependencies...
"%VENV_DIR%\Scripts\pip" install -r "%PROJECT_DIR%\requirements.txt"
if %errorlevel% neq 0 (
    echo ERROR: Failed to install dependencies
    pause
    exit /b 1
)

echo [4/5] Installing Playwright browsers...
"%VENV_DIR%\Scripts\playwright" install msedge
if %errorlevel% neq 0 (
    echo WARNING: Playwright browser install failed (will retry on first run)
)

echo [5/5] Creating data directories...
set APPDATA_DIR=%APPDATA%\jarvix
if not exist "%APPDATA_DIR%" mkdir "%APPDATA_DIR%"
if not exist "%APPDATA_DIR%\logs" mkdir "%APPDATA_DIR%\logs"
if not exist "%APPDATA_DIR%\settings" mkdir "%APPDATA_DIR%\settings"
if not exist "%APPDATA_DIR%\secrets" mkdir "%APPDATA_DIR%\secrets"
if not exist "%APPDATA_DIR%\plugins" mkdir "%APPDATA_DIR%\plugins"

echo.
echo =========================================
echo  Installation complete!
echo =========================================
echo.
echo To start jarvix, run: start.bat
echo Or manually: %VENV_DIR%\Scripts\python -m jarvix
echo.
pause