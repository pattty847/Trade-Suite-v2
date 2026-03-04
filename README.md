# Sentinel - Qt Trading Workstation

Sentinel is the actively developed PySide6/pyqtgraph desktop workstation in this repository.  
Legacy DearPyGUI code remains in-repo as reference, but Sentinel is the primary runtime.

![ezgif-8fe9048b423618](https://github.com/user-attachments/assets/e703a1f7-d0be-487e-bdfb-695e34073d53)
![image](https://github.com/user-attachments/assets/6f49af6f-3e56-43ce-aba0-24d8aca29b1b)

## Project Evolution: TradeSuite v2

The TradeSuite project is undergoing a significant evolution from a desktop-based application to a modern, client-server architecture. This upgrade will enable 24/7 data processing, advanced AI-powered features, and a flexible web-based interface.

The development environment is being standardized on WSL2, and we will be leveraging Redis for high-performance in-memory data management.

For a detailed overview of the new architecture, technology stack, and implementation plan, please see the full design blueprint: **[Blueprint: TradeSuite v2 - Full System Architecture](docs/design_documents/active_proposals/trade_suite_full_ai_sentinel_integration.md)**.

## Quick Start

```bash
uv sync
uv run python -m sentinel
```

## Current Scope

- Dockable Qt widgets with persistent layout restore
- Real-time chart and orderbook widgets
- Shared async market data runtime via `trade_suite.core`
- `sentinel_ops` package retained for collector/alert-bot workflows

## Sentinel Monitoring Through Grafana
![image](https://github.com/user-attachments/assets/fc11ca26-ec19-43ca-8739-b9b1972db1f7)

## Documentation

Full docs live under [docs](docs/README.md).  
Sentinel runtime path: `python -m sentinel`  
Collector/ops runtime path: `python -m sentinel_ops.run`

## Contributing

Please read [AGENTS.md](AGENTS.md) for project guidelines.

## License

TradeSuite is released under the MIT License. See [LICENSE](LICENSE) for details.
