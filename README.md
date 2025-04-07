# TradeSuite - A Multi-Exchange Cryptocurrency Trading Platform

![TradeSuite Screenshot](https://github.com/pattty847/Trade-Suite-v2/assets/23511285/2f5e732d-87ba-4132-b66e-7dd71e643393)

## Table of Contents
- [Introduction](#introduction)
- [Features](#features)
- [Getting Started](#getting-started)
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

To get started with TradeSuite, follow these steps:

1. Clone the repository:

   ```bash
   git clone https://github.com/yourusername/trade-suite.git
   cd trade-suite
   ```

2. Install the required dependencies:

   ```bash
   pip install -r requirements.txt
   ```

_To do_
3. Add .env file with exchange credentials

3. Run the program:

   ```bash
   python main.py
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
