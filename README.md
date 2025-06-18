# TradeSuite - A Multi-Exchange Cryptocurrency Trading Platform

TradeSuite is a multi-exchange cryptocurrency trading platform. It is currently being re-architected into a high-performance, distributed client-server system designed for 24/7 operation and advanced AI-driven analysis.

![image](https://github.com/user-attachments/assets/6f49af6f-3e56-43ce-aba0-24d8aca29b1b)

## Project Evolution: TradeSuite v2

The TradeSuite project is undergoing a significant evolution from a desktop-based application to a modern, client-server architecture. This upgrade will enable 24/7 data processing, advanced AI-powered features, and a flexible web-based interface.

The development environment is being standardized on WSL2, and we will be leveraging Redis for high-performance in-memory data management.

For a detailed overview of the new architecture, technology stack, and implementation plan, please see the full design blueprint: **[Blueprint: TradeSuite v2 - Full System Architecture](docs/design_documents/active_proposals/trade_suite_full_ai_sentinel_integration.md)**.

## Features (Legacy v1)

- Dockable widgets and persistent layouts
- Shared data streams for efficient multi-widget updates
- Real-time candlestick charts, order book and price level DOM
- Optional Sentinel alert bot for automated monitoring

## Sentinel Monitoring Through Grafana
![image](https://github.com/user-attachments/assets/47341fd4-f6e9-4344-9b27-88aa574ab001)

## Documentation

Full documentation lives in the [docs](docs/README.md) directory. The legacy application can be installed by following the original [Getting Started](docs/user_guide/getting_started.md) guide. Documentation for v2 will be updated as development progresses.
See [Autonomous Agent Playground](docs/design_documents/active_proposals/autonomous_agent_playground.md) for the new AutoGen framework blueprint.

## Contributing

Please read [AGENTS.md](AGENTS.md) for project guidelines.

## License

TradeSuite is released under the MIT License. See [LICENSE](LICENSE) for details.
