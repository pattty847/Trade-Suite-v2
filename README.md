# TradeSuite - A Multi-Exchange Cryptocurrency Trading Platform

# 🚧 WIP: Multi-Widget Streaming for Same Market

![Screenshot](https://github.com/user-attachments/assets/80dcbe6b-ecdf-45e2-a9fa-f0b542088655)

> across **different timeframes**, all sharing a unified data stream.


## Architecture
![image](https://github.com/user-attachments/assets/4d6c7474-0fcc-4ca7-891c-be9fe1077737)


## Table of Contents
- [Introduction](#introduction)
- [Features](#features)
- [Getting Started](#getting-started)
  - [Prerequisites](#prerequisites)
  - [Installation](#installation)
  - [Environment Setup](#environment-setup)
  - [Running the Application](#running-the-application)
- [Implemented Features](#implemented-features)
- [Planned Features](#planned-features)
- [Contributing](#contributing)
- [License](#license)
- [For Developers](#for-developers)
  - [Packaging the Application](#packaging-the-application)
    - [Option 1: Creating a Standalone Executable](#option-1-creating-a-standalone-executable)
    - [Option 2: Using UV for Package Management](#option-2-using-uv-for-package-management)
- [For End Users](#for-end-users)

## Introduction

TradeSuite is a multi-exchange cryptocurrency trading platform built using DearPyGUI and CCXT PRO. It provides a real-time streaming interface for multiple instances of the same exchange, with features such as real-time candlestick charting and a real-time order book with price level zoom and aggregation toggle.

**Note:** A major architectural refactoring, introducing a fully dockable widget system and optimized data flow, is complete and available in a dedicated feature branch. This update significantly enhances performance and user interface flexibility.

## Features

- **Flexible Dockable Widget UI:** Build your personalized trading dashboard by docking, undocking, tabbing, and resizing widgets.
- **Persistent & Customizable Layouts:** Save your workspace layout and restore it automatically between sessions. Reset to a default layout anytime.
- **Efficient Multi-Exchange Data Streaming:** Real-time trades and order book updates via CCXT PRO WebSockets.
- **Optimized Shared Data Streams:** Display the same market (e.g., BTC/USDT) on multiple widgets (e.g., 1-minute chart, 1-hour chart, order book) simultaneously using a single, shared data connection for maximum efficiency.
- **Real-Time Candlestick Charting:** View live candlestick charts with configurable timeframes and indicators (e.g., EMA).
- **Real-Time Order Book:** Analyze market depth with price level aggregation and zoom capabilities.
- **Real-Time Price Level / DOM View:** Visualize aggregated market depth through the dedicated Price Level widget.
- **Modular Architecture:** Decoupled components for data handling, UI widgets, and external API integrations (like SEC EDGAR).

## Getting Started

### Prerequisites

- Python 3.10+ 
- InfluxDB (local or cloud instance)
- Crypto Exchange key (for trading)
- SEC EDGAR API name and email (for their API requirements)

### Installation

The easiest way to install TradeSuite is using our automated installation script. Choose the appropriate method for your operating system:

#### macOS / Linux
```bash
# Clone the repository
git clone https://github.com/pattty847/Trade-Suite-v2.git
cd Trade-Suite-v2

# Make the installation script executable
chmod +x scripts/install.sh

# Run the installation script
./scripts/install.sh
```

#### Windows
```batch
# Clone the repository
git clone https://github.com/pattty847/Trade-Suite-v2.git
cd Trade-Suite-v2

# Run the installation script
scripts\install.bat
```

The installation script will:
- Check your Python version
- Create and activate a virtual environment
- Install dependencies using UV (recommended) or pip
- Set up your environment file

> **Note**: The script will prompt you to choose between UV (recommended) or pip for package installation. UV is significantly faster and more reliable, especially for packages that require compilation.

#### Manual Installation (Alternative)

If you prefer to install manually, follow these steps:

1. Clone the repository:
   ```bash
   git clone https://github.com/pattty847/Trade-Suite-v2.git
   cd Trade-Suite-v2
   ```

2. Set up a virtual environment:
   ```bash
   # Using venv (standard)
   python -m venv .venv
   
   # On Windows
   .venv\Scripts\activate
   
   # On macOS/Linux
   source .venv/bin/activate
   ```

3. Install dependencies:
   ```bash
   # Install uv (recommended for faster installation)
   pip install uv
   
   # Install dependencies using uv
   uv pip install -r requirements.txt
   ```

4. **Important**: TA-Lib requires C++ libraries:
   - **Windows**: Download and install the wheel from [here](https://www.lfd.uci.edu/~gohlke/pythonlibs/#ta-lib)
   - **macOS**: `brew install ta-lib`
   - **Linux**: `apt-get install ta-lib`

### Environment Setup

1. Configure your environment variables:

   ```bash
   # Copy the template file
   cp .env.template .env
   
   # Edit the .env file with your API keys and credentials
   ```

2. Required API services:
   - InfluxDB (for data storage)
   - Exchange API keys (Coinbase, etc.)
   - Any additional services used

3. Configure InfluxDB:
   - Make sure InfluxDB is running locally (or you have cloud access)
   - Create buckets: "trades", "market_data", "candles", "orderbook"
   - Update your .env file with the correct tokens and organization

### Running the Application

#### Option 1: One-Click Startup (Recommended for New Users)

Simply double-click the appropriate script for your operating system:

- **Windows**: Double-click `run.bat`
- **macOS/Linux**: Double-click `run.sh` (or run `./run.sh` in terminal)

These scripts will automatically:
- Check if your setup is complete
- Run the installation script if needed
- Start the application with default settings

#### Option 2: Command Line (Advanced Users)

You can run the application manually:

```bash
# Run as a Python module (recommended)
python -m trade_suite

# With specific exchanges
python -m trade_suite --exchanges coinbase binance

# With debug logging
python -m trade_suite --level DEBUG

# To reset to the default layout
python -m trade_suite --reset-layout
```

## Implemented Features

- **Complete UI Overhaul:** Fully dockable widget system built with DearPyGUI, allowing flexible user layouts.
- **Optimized Data Architecture:** Decoupled data flow managed by a central `TaskManager`, enabling shared WebSocket streams and efficient multi-widget updates. Significantly reduces resource consumption compared to previous versions.
- **Centralized Task Management:** Robust handling of asynchronous data streams and background processing tasks.
- **Real-Time Candlestick Widget:** Displays live charts with EMA indicators, updated directly from trade streams.
- **Real-Time Order Book Widget:** Shows live market depth with controls for price aggregation and zoom.
- **Real-Time Price Level (DOM) Widget:** A new widget providing a clear view of aggregated buy/sell pressure at different price levels.
- **Layout Persistence:** User-defined layouts are automatically saved (`user_layout.ini`) and restored. Factory default layout (`factory_layout.ini`) provided with reset capability.
- **Modular Component Design:** Refactored codebase with clear separation of concerns (Data Source, Task Manager, Widgets, SEC API Module).
- **Command-Line Interface:** Flexible application startup using `argparse` for setting exchanges, logging level, and layout reset.
- **Basic Multi-Exchange Support:** Foundation laid for connecting to and displaying data from multiple exchanges simultaneously (e.g., Binance, Coinbase).

## Planned Features

- **Trading Capabilities:** Execute buy/sell orders directly through the platform interface.
- **Order Interface Development:** Dedicated widgets/panels for managing open orders, positions, and trade history.
- **Multi-Exchange Portfolio Management:** Aggregate and track assets across multiple connected exchanges.
- **Expansion of Technical Indicators:** Add a wider variety of popular technical indicators to the charting widget.
- **Advanced Charting Tools:** Implement drawing tools, more chart types, and deeper analysis features.
- **Historical Data Integration & Analysis:** Fetch, store, and visualize historical market data for back-testing and analysis.
- **User Authentication and Security:** Implement secure login and potentially encrypt sensitive API key storage.
- **Integration with Additional Exchanges:** Expand the range of supported cryptocurrency exchanges via CCXT PRO.
- **Real-Time News and Market Updates:** Incorporate relevant news feeds or market sentiment indicators.
- **Widget-Specific Customization:** Allow finer-grained configuration within individual widget settings.
- **Community Features:** Potential integration of chat or shared analysis features.

## Contributing

We welcome contributions to TradeSuite! If you'd like to contribute, please follow these steps:

1. Fork the repository on GitHub.
2. Create a new branch from the main branch for your work.
3. Make your changes, commit them, and push them to your fork.
4. Submit a pull request to the main repository.

Please make sure to follow our [contribution guidelines](CONTRIBUTING.md).

## License

TradeSuite is released under the MIT License. See the [LICENSE](LICENSE) file for details.

## For Developers

![image](https://github.com/user-attachments/assets/157c17e5-b3ec-4433-91ab-fba92765f868)

### Packaging the Application

#### Option 1: Creating a Standalone Executable

The easiest way for end users to run the application is with a standalone executable:

1. Install PyInstaller:
   ```bash
   pip install pyinstaller
   ```

2. Run the build script:
   ```bash
   # On Windows
   python build_executable.py
   
   # On macOS/Linux
   python3 build_executable.py
   ```

3. The executable will be created in the `dist` folder, ready to distribute to users.

#### Option 2: Using UV for Package Management

UV is a modern Python packaging tool that offers significant performance improvements over pip:

1. Install UV:
   ```bash
   pip install uv
   ```

2. Use UV for dependency management:
   ```bash
   # Install dependencies
   uv pip install -r requirements.txt
   
   # Create a lockfile for reproducible builds
   uv pip compile --output-file requirements.lock requirements.txt
   
   # Install from lockfile
   uv pip install -r requirements.lock
   ```

3. UV Virtual Environments:
   ```bash
   # Create and activate a virtual environment
   uv venv
   source .venv/bin/activate  # Linux/macOS
   .venv\Scripts\activate     # Windows
   ```

4. Export consolidated dependencies:
   ```bash
   uv pip freeze > requirements-frozen.txt
   ```

UV offers faster installation times, better dependency resolution, and is 100% compatible with pip. For more information, visit the [UV documentation](https://github.com/astral-sh/uv).

## For End Users

If you're not familiar with Python or command-line tools, we provide pre-built executables for Windows and macOS:

1. Download the latest release from the [Releases page](https://github.com/pattty847/Trade-Suite-v2/releases)
2. Extract the zip file to a folder of your choice
3. Double-click the TradeSuite executable to run the application
4. No installation or configuration is required for basic usage

The application works with public cryptocurrency data by default, no API keys required!
