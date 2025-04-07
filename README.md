# TradeSuite - A Multi-Exchange Cryptocurrency Trading Platform

![TradeSuite Screenshot](https://github.com/pattty847/Trade-Suite-v2/assets/23511285/2f5e732d-87ba-4132-b66e-7dd71e643393)

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
- CCXT Pro license (for professional use)

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

You can run the application in two ways:

1. Using the main script (recommended, works on all platforms):
   ```bash
   python main.py
   ```

2. As a module (alternative method):
   ```bash
   python -m trade_suite
   ```

Both methods support the following command-line arguments:
```bash
# With specific exchanges
python main.py --exchanges coinbase binance

# With debug logging
python main.py --level DEBUG
```

## Implemented Features

- Basic Real-Time Candlestick Charting Interface: Implemented using DearPyGUI and CCXT PRO.
- Multiple Tabs Feature: Support for numerous instances of the same exchange.
- Real-Time Candlestick Updates and Indicators: Continuous updating of candlestick charts with relevant trading indicators.
- Object-Oriented Design: Ensures ease of scalability and further development.

## Planned Features

- Separate the Data storage aspect to a new continously running Influx server the client can request data from.
- ArgParser for Command-Line Entry: To facilitate easier and more flexible program startup through the command line.
- Trading Capabilities: Enabling actual trading actions (buy, sell, etc.) within the platform.
- Multi-Exchange Portfolio Management: Cross-exchange portfolio aggregation and management system.
- Expansion of Technical Indicators: Adding more indicators for comprehensive technical analysis.
- Order Interface Development: To manage and execute trade orders directly from the platform.
- Performance Optimization: Enhancing the efficiency and responsiveness of the application.
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
