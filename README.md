# Sentinel

Sentinel is a desktop trading workstation built with `PySide6`, `PyQtGraph`, and `qasync`.

Current scope:
- live candlestick charting
- DOM / orderbook widgets
- dockable Qt layout with persistence
- shared async market-data runtime

## Run

```bash
uv sync --group dev
uv run python -m sentinel
```

## Stack

- `PySide6`
- `PyQtGraph`
- `qasync`
- `ccxt`
- `pandas`

## Project Layout

- `/Users/copeharder/Programming/Trade-Suite-v2/sentinel/app`: Qt shell, layout management, runtime wiring
- `/Users/copeharder/Programming/Trade-Suite-v2/sentinel/widgets`: chart, DOM, and orderbook widgets
- `/Users/copeharder/Programming/Trade-Suite-v2/sentinel/core`: data access, streaming, task/runtime management
- `/Users/copeharder/Programming/Trade-Suite-v2/sentinel/analysis`: shared analytics and processors

## Development

- Runtime entrypoint: `python -m sentinel`
- Test entrypoint: `uv run python -m pytest`
- Dependencies are managed in `/Users/copeharder/Programming/Trade-Suite-v2/pyproject.toml`

## Status

This repository has been reduced to the active Sentinel application. Legacy DearPyGUI-era code has been removed from the runtime path.

## Contributing

Project operating guidance lives in `/Users/copeharder/Programming/Trade-Suite-v2/AGENTS.md`.

## License

MIT. See `/Users/copeharder/Programming/Trade-Suite-v2/LICENSE`.
