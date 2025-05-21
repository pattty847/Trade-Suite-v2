#!/usr/bin/env python3
# Crypto Price Alert Bot

A modular, configurable system for monitoring cryptocurrency prices and sending alerts based on various conditions.

## Features

- **Modular Design**: Separate components for configuration, data fetching, rule evaluation, and notifications
- **Multiple Alert Types**:
  - Price Level (above/below specific price)
  - Percentage Change
  - Volatility
- **Async Architecture**:
  - Non-blocking data fetching with asyncio
  - Concurrent price and OHLCV data streaming
  - Event-based rule evaluation
  - Queued, asynchronous notifications
- **Notification Options**:
  - Email alerts (async with retry capability)
  - Console logging
- **Metrics & Monitoring**:
  - Prometheus metrics for rule evaluations, alerts, and notifications
  - Performance tracking for critical operations
  - Exposed HTTP metrics endpoint
- **Configurable**:
  - YAML-based configuration with validation using Pydantic
  - Per-rule cooldown periods
  - Custom timeframes

## Installation

```bash
pip install -r requirements.txt
```

## Configuration

Create a YAML configuration file (see `alerts_config.yaml` for an example):

```yaml
BTC/USD:
  price_levels:
    - price: 50000
      condition: above
      cooldown: 3600  # seconds
    - price: 45000
      condition: below
  percentage_changes:
    - percentage: 5
      timeframe: 10   # minutes
      cooldown: 1800  # seconds

ETH/USD:
  price_levels:
    - price: 3000
      condition: above
    - price: 2500
      condition: below
  volatility:
    - threshold: 3
      timeframe: 5    # minutes
      cooldown: 3600  # seconds
```

## Email Configuration

Set these environment variables for email notifications:

```bash
export SMTP_SERVER=smtp.gmail.com
export SMTP_PORT=587
export SMTP_USERNAME=your-email@gmail.com
export SMTP_PASSWORD=your-app-password
export ALERT_EMAIL=recipient@example.com
```

## Usage

```bash
# Basic usage with default settings
python -m sentinel.alert_bot.main

# Specify config file and ticker update interval
python -m sentinel.alert_bot.main --config path/to/config.yaml --interval 10

# Test email configuration
python -m sentinel.alert_bot.main --test-email

# Use different exchange
python -m sentinel.alert_bot.main --exchange binance

# Debug level logging
python -m sentinel.alert_bot.main --log-level DEBUG

# Prometheus metrics on non-default port
python -m sentinel.alert_bot.main --metrics-port 8080

# Disable metrics collection
python -m sentinel.alert_bot.main --disable-metrics
```

## Metrics

The application exposes Prometheus metrics on port 9090 by default. Available metrics include:

- **Rule evaluation counts**: Number of rule evaluations by symbol and rule type
- **Alert triggers**: Number of alerts triggered by symbol and rule type
- **Rule evaluation duration**: Timing statistics for rule evaluations
- **Current prices**: Latest price for each monitored symbol
- **Notification stats**: Counts and timing for notification delivery
- **Queue sizes**: Size of notification queues

These metrics can be scraped by Prometheus and visualized with Grafana.

## Project Structure

```
alert_bot/
├── config/
│   ├── __init__.py
│   ├── alerts_config.yaml
│   └── loader.py           # Pydantic models for config validation
├── rules/
│   ├── __init__.py
│   ├── base.py             # Abstract base class for rules
│   ├── engine.py           # Rule evaluation engine
│   ├── price_level.py      # Price level rule implementation
│   ├── percentage_change.py # Percentage change rule implementation
│   └── volatility.py       # Volatility rule implementation
├── fetcher/
│   ├── __init__.py
│   ├── ccxt_fetcher.py     # Synchronous CCXT fetcher (legacy)
│   ├── async_ccxt_fetcher.py # Async CCXT fetcher
│   ├── ticker.py           # Async ticker streamer
│   └── ohlcv.py            # Async OHLCV data streamer
├── notifier/
│   ├── __init__.py
│   ├── base.py             # Base notifier interface with queue support
│   ├── console_notifier.py # Console output notifier (sync version)
│   ├── email_notifier.py   # Email notifier (sync version)
│   ├── async_console_notifier.py # Async console notifier
│   └── async_email_notifier.py   # Async email notifier
├── state/
│   ├── __init__.py
│   └── manager.py          # State management for rule cooldowns
├── metrics.py              # Prometheus metrics collection
├── main.py                 # Application entry point with async event loop
├── requirements.txt        # Project dependencies
└── README.md
```

## Architecture

The application follows an event-driven architecture:

1. **Initialization**: Config is loaded, rules are instantiated, and data streamers are set up
2. **Data Streaming**: Async streamers fetch price and OHLCV data at configurable intervals
3. **Events**: When new data arrives, callbacks are triggered
4. **Rule Evaluation**: Rules are evaluated against the latest data
5. **Notifications**: If rules trigger, notifications are queued and processed in the background
6. **Metrics**: Performance and operational metrics are collected and exposed via HTTP

## Future Enhancements

- WebSocket support for real-time price data
- Additional alert types (MA crosses, RSI levels, etc.)
- Additional notification methods (SMS, Telegram, Discord)
- Web UI for monitoring and configuration
- Persistence for rule state
- Hot-reloading of configuration
- Backtest mode for testing rules against historical data 