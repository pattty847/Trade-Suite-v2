@echo off
echo Starting TradeSuite...

:: Check if virtual environment exists
if not exist .venv\ (
    echo Virtual environment not found. Running installation script...
    call scripts\install.bat
) else (
    :: Just activate the environment and run
    call .venv\Scripts\activate.bat
    python -m trade_suite
    call deactivate
) 