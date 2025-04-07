#!/bin/bash

echo "Starting TradeSuite..."

# Check if virtual environment exists
if [ ! -d ".venv" ]; then
    echo "Virtual environment not found. Running installation script..."
    bash scripts/install.sh
else
    # Just activate the environment and run
    if [[ "$OSTYPE" == "msys" || "$OSTYPE" == "win32" ]]; then
        source .venv/Scripts/activate
    else
        source .venv/bin/activate
    fi
    
    python -m trade_suite
    deactivate
fi 