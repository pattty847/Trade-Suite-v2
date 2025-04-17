# TradeSuite - A Multi-Exchange Cryptocurrency Trading Platform

![Screenshot 2025-04-10 155148](https://github.com/user-attachments/assets/2cc68be5-f07e-4484-9d7f-5351b1d2b695)

## (IN THE WORKS)
![image](https://github.com/user-attachments/assets/af3ef9f6-31de-4793-a48b-59c5e78897e3)

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

## Features

- Basic real-time candlestick charting interface
- Real time EMA series for candle sticks
- Real-time order book with price level zoom and aggregation toggle

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

- Basic Real-Time Candlestick Charting Interface: Implemented using DearPyGUI and CCXT PRO.
- Multiple Tabs Feature: Support for numerous instances of the same exchange.
- Real-Time Candlestick Updates and Indicators: Continuous updating of candlestick charts with relevant trading indicators.
- Object-Oriented Design: Ensures ease of scalability and further development.
- ArgParser for Command-Line Entry: To facilitate easier and more flexible program startup through the command line.
- Performance Optimization: Enhanced the efficiency and responsiveness of the application (orderbook processing, chart updating).

## Planned Features

- Separate the Data storage aspect to a new continously running Influx server the client can request data from.
- Trading Capabilities: Enabling actual trading actions (buy, sell, etc.) within the platform.
- Multi-Exchange Portfolio Management: Cross-exchange portfolio aggregation and management system.
- Expansion of Technical Indicators: Adding more indicators for comprehensive technical analysis.
- Order Interface Development: To manage and execute trade orders directly from the platform.
- User Authentication and Security: Implementing secure login and data protection measures.
- Mobile Compatibility: Adapting the platform for use on mobile devices.
- Historical Data Analysis Features: Integrating tools for back-testing strategies with historical data.
- Customizable UI Elements: Allowing users to personalize the interface to suit their preferences.
- Integration with Additional Exchanges: Expanding the range of supported cryptocurrency exchanges.
- Real-Time News and Market Updates: Incorporating a feature to provide live news and market updates.
- Community Features: Adding forums or chatrooms for user interaction and discussion.
- Advanced Charting Tools: Implementing more sophisticated charting options for in-depth analysis.

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
