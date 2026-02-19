# Agent Playground

This directory provides a minimal sandbox for experimenting with autonomous agents.

## Usage

```python
from trade_suite.data.data_source import Data
from sentinel.alert_bot.manager import AlertDataManager
from agent_playground.agents import MonitorAgent, ScraperAgent
from agent_playground.sandbox import run_playground

# Instantiate TradeSuite components

data = Data()
alert_manager = AlertDataManager(data)

agents = [
    MonitorAgent("monitor", data),
    ScraperAgent("scraper", alert_manager),
]

run_playground(agents)
```

This is a starting point for building more complex AutoGen-style agents that leverage existing TradeSuite modules.
