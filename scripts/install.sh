#!/bin/bash

# Exit on error
set -e

echo "----------------------------------------"
echo "TradeSuite v2 - Installation Script"
echo "----------------------------------------"

# Check if Python is installed
echo "Checking Python version..."
if command -v python3 &>/dev/null; then
    PY_CMD="python3"
elif command -v python &>/dev/null; then
    PY_CMD="python"
else
    echo "Error: Python not found. Please install Python 3.10 or later."
    exit 1
fi

# Check Python version
PY_VERSION=$($PY_CMD -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')")
echo "Found Python $PY_VERSION"

if (( $(echo "$PY_VERSION < 3.10" | bc -l) )); then
    echo "Error: Python 3.10 or later is required."
    exit 1
fi

# Create virtual environment
echo "Creating virtual environment..."
$PY_CMD -m venv .venv

# Activate virtual environment
if [[ "$OSTYPE" == "msys" || "$OSTYPE" == "win32" ]]; then
    echo "Activating virtual environment (Windows)..."
    source .venv/Scripts/activate
else
    echo "Activating virtual environment (Unix)..."
    source .venv/bin/activate
fi

# Install dependencies
echo "Installing dependencies..."
echo "Would you like to use uv for faster installation? (y/n)"
read -r USE_UV

if [[ "$USE_UV" == "y" || "$USE_UV" == "Y" ]]; then
    echo "Installing uv..."
    pip install uv
    echo "Installing dependencies with uv..."
    uv pip install -r requirements.txt
else
    echo "Installing dependencies with pip..."
    pip install -r requirements.txt
fi

# Create .env file from template if it doesn't exist
if [ ! -f .env ]; then
    echo "Creating .env file from template..."
    cp .env.template .env
    echo "Please edit the .env file with your API keys and credentials."
fi

echo "----------------------------------------"
echo "Installation completed successfully!"
echo "----------------------------------------"
echo "To activate the virtual environment:"
if [[ "$OSTYPE" == "msys" || "$OSTYPE" == "win32" ]]; then
    echo "    .venv\\Scripts\\activate"
else
    echo "    source .venv/bin/activate"
fi
echo ""
echo "To run the application:"
echo "    python -m trade_suite"
echo ""
echo "For more options, check the README.md file."
echo "----------------------------------------" 