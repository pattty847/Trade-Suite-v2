@echo off
echo ----------------------------------------
echo TradeSuite v2 - Installation Script
echo ----------------------------------------

REM Check if Python is installed
echo Checking Python version...
where python >nul 2>&1
if %ERRORLEVEL% neq 0 (
    echo Error: Python not found. Please install Python 3.10 or later.
    exit /b 1
)

REM Check Python version
for /f "tokens=*" %%a in ('python -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')"') do set PY_VERSION=%%a
echo Found Python %PY_VERSION%

REM Create virtual environment
echo Creating virtual environment...
python -m venv .venv

REM Activate virtual environment
echo Activating virtual environment...
call .venv\Scripts\activate.bat

REM Install dependencies
echo Installing dependencies...
set /p USE_UV=Would you like to use uv for faster installation? (y/n): 

if /i "%USE_UV%"=="y" (
    echo Installing uv...
    pip install uv
    echo Installing dependencies with uv...
    uv pip install -r requirements.txt
) else (
    echo Installing dependencies with pip...
    pip install -r requirements.txt
)

REM Create .env file from template if it doesn't exist
if not exist .env (
    echo Creating .env file from template...
    copy .env.template .env
    echo Please edit the .env file with your API keys and credentials.
)

echo ----------------------------------------
echo Installation completed successfully!
echo ----------------------------------------
echo To activate the virtual environment:
echo     .venv\Scripts\activate
echo.
echo To run the application:
echo     python -m trade_suite
echo.
echo For more options, check the README.md file.
echo ----------------------------------------

pause 