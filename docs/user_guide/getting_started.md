# Getting Started

This guide walks you through installing TradeSuite, configuring your environment
and launching the application. The following instructions mirror the original
`README.md` but have been moved here for clarity.

## Prerequisites

- Python 3.10+
- InfluxDB (local or cloud instance)
- Exchange API keys (e.g. Coinbase)
- SEC EDGAR API name and email for the SEC modules

## Installation

The fastest way to get up and running is to use the provided installation
scripts.

### macOS / Linux

```bash
# Clone the repository
git clone https://github.com/pattty847/Trade-Suite-v2.git
cd Trade-Suite-v2

# Make the installation script executable
chmod +x scripts/install.sh

# Run the installation script
./scripts/install.sh
```

### Windows

```batch
# Clone the repository
git clone https://github.com/pattty847/Trade-Suite-v2.git
cd Trade-Suite-v2

# Run the installation script
scripts\install.bat
```

The script checks your Python version, creates a virtual environment and installs
all dependencies using **uv** (recommended) or pip. It also sets up your `.env`
file.

<details>
<summary>Manual Installation (Alternative)</summary>

1. Clone the repository:
   ```bash
   git clone https://github.com/pattty847/Trade-Suite-v2.git
   cd Trade-Suite-v2
   ```

2. Set up a virtual environment:
   ```bash
   python -m venv .venv

   # Windows
   .venv\Scripts\activate

   # macOS/Linux
   source .venv/bin/activate
   ```

3. Install dependencies (using uv is recommended):
   ```bash
   pip install uv
   uv pip install -r requirements.txt
   ```

4. **Important:** TA‑Lib requires native libraries.
   - **Windows:** install the wheel from <https://www.lfd.uci.edu/~gohlke/pythonlibs/#ta-lib>
   - **macOS:** `brew install ta-lib`
   - **Linux:** `apt-get install ta-lib`
</details>

## Environment Setup

1. Copy the template and edit your credentials:
   ```bash
   cp .env.template .env
   ```
2. Configure InfluxDB buckets (`trades`, `market_data`, `candles`, `orderbook`)
   and update the tokens and organisation in `.env`.

## Running the Application

### Option 1: One-Click Startup

Run the convenience script for your OS:

- **Windows:** `run.bat`
- **macOS/Linux:** `./run.sh`

These scripts verify your setup and launch TradeSuite with default settings.

<details>
<summary>Option 2: Command Line</summary>

You can also run TradeSuite directly with Python:

```bash
python -m trade_suite

# Select specific exchanges
python -m trade_suite --exchanges coinbase binance

# Enable debug logging
python -m trade_suite --level DEBUG

# Reset to the default layout
python -m trade_suite --reset-layout
```
</details>
