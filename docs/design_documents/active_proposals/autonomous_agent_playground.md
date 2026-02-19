# Autonomous Agent Playground Design

This proposal outlines a lightweight framework for creating AutoGen-style agents inside TradeSuite. The playground reuses existing modules to let agents plan tasks, gather data and generate reports.

## 1. Architecture

```
Agents -> Sandbox -> TradeSuite Services (Data, AlertBot, Sentinel) -> Storage
```

- **Agents** encapsulate behaviour such as monitoring prices, scraping filings or synthesising reports.
- **Sandbox** coordinates agents asynchronously using a shared event loop.
- **TradeSuite Services** provide data access (InfluxDB, CCXT), rule evaluation and alerts.
- **Storage** can be InfluxDB, SQLite or JSON files for persistent memory.

## 2. Reusable Tools

Existing functionality can be wrapped as agent actions:

- `trade_suite.data.Data` for historical and real-time feeds.
- `sentinel.alert_bot.manager.AlertDataManager` for rule definitions and triggers.
- `scanner` tools for chart analysis and signal generation.
- `cope_net` (planned) for natural language report generation.
- GUI loggers or file outputs for visualisation.

## 3. Agent Types

- **MonitorAgent** – streams market data and updates internal state.
- **ScraperAgent** – polls SEC filings or other external sources.
- **SynthesisAgent** – creates summaries using LLM tools.

Agents can spawn new tasks via the sandbox to pursue sub‑goals.

## 4. Sandbox Environment

A new `agent_playground` package provides:

- `base.Agent` – abstract class with an async `run` method.
- `agents.py` – example agents using TradeSuite modules.
- `sandbox.py` – utility to run a collection of agents concurrently.
- `README.md` – instructions for experimentation.

## 5. Agent Memory

Agents maintain a `memory` dictionary. For persistent state, they may read/write SQLite tables or InfluxDB measurements using existing clients. Simple JSON files can store plans between runs.

## 6. Async Design

Agents are executed with `asyncio.gather` to keep latency low. Shared objects such as `Data` or `AlertDataManager` remain in memory to avoid repeated setup costs.

## 7. Future Growth

LLM agents could modify their own prompts or spawn specialised children that inherit memory from the parent. Over time the sandbox can evolve into a self‑improving workflow manager.
