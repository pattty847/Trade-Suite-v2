# Testing Guidance for `data_source.py`

This document summarizes the main components of `data_source.py` and outlines possible unit tests using `pytest`.

## Data Class Overview

`Data` serves as a facade over the lower level helpers:

- **`CCXTInterface`** – loads and manages `ccxt.pro` exchange instances.
- **`MarketAggregator`** – calculates trade statistics.
- **`CacheStore`** – simple CSV cache for OHLCV data.
- **`CandleFetcher`** – fetches historical candles, using `CacheStore` and `InfluxDB`.
- **`Streamer`** – manages live streams for trades, order books and tickers.
- **`SignalEmitter`** – dispatches GUI/events.

`Data` exposes convenience wrappers such as `watch_trades` or `fetch_candles` which simply delegate to these helpers after ensuring exchanges are loaded.

## Testable Units

1. **Exchange loading** – verify that `load_exchanges` updates `fetcher` and `streamer` with the loaded `exchange_list`.
2. **Delegation wrappers** – each `watch_*` method should call the corresponding method on `Streamer` with the same arguments.
3. **Fetching candles** – `fetch_candles` should call `CandleFetcher.fetch_candles` and return its result.
4. **UI loop configuration** – `set_ui_loop` forwards the event loop to `Streamer`.

Lower level helpers (`CandleFetcher`, `Streamer`, `CacheStore`) contain business logic that can be tested in isolation by mocking network calls or using sample data.

## Suggested Unit Tests

The following tests use `pytest` and `unittest.mock` to isolate async behaviour.
Detailed comments in the code explain each step.

```python
import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from trade_suite.data.data_source import Data
from trade_suite.data.ccxt_interface import CCXTInterface

@pytest.fixture
def data_instance():
    """Create a Data object with mocked subcomponents."""
    emitter = MagicMock()
    influx = MagicMock()
    data = Data(influx=influx, emitter=emitter, exchanges=[])
    # Replace heavy helpers with mocks
    data.fetcher = MagicMock()
    data.streamer = MagicMock()
    return data

@pytest.mark.asyncio
async def test_load_exchanges_propagates_exchange_list(data_instance):
    """`load_exchanges` should populate helper exchange lists."""
    # Patch the CCXTInterface method so no real network calls happen
    with patch.object(CCXTInterface, "load_exchanges", new=AsyncMock()) as loader:
        data_instance.exchange_list = {"coinbase": object()}
        await data_instance.load_exchanges(["coinbase"])
        loader.assert_awaited_once_with(["coinbase"])
    data_instance.fetcher.set_exchange_list.assert_called_once_with(data_instance.exchange_list)
    data_instance.streamer.set_exchange_list.assert_called_once_with(data_instance.exchange_list)

@pytest.mark.asyncio
async def test_set_ui_loop_passes_through(data_instance):
    """Ensure the loop is forwarded to `Streamer`."""
    loop = asyncio.get_event_loop()
    data_instance.set_ui_loop(loop)
    data_instance.streamer.set_ui_loop.assert_called_once_with(loop)

@pytest.mark.asyncio
async def test_watch_trades_delegates(data_instance):
    """Wrapper should await `Streamer.watch_trades` with same parameters."""
    stop = asyncio.Event()
    await data_instance.watch_trades(
        symbol="BTC/USD",
        exchange="coinbase",
        stop_event=stop,
        track_stats=True,
        write_trades=False,
        write_stats=False,
        sink=None,
        queue=None,
    )
    data_instance.streamer.watch_trades.assert_awaited_once()

@pytest.mark.asyncio
async def test_fetch_candles_returns_fetcher_result(data_instance):
    """`fetch_candles` should return whatever the fetcher yields."""
    expected = {"coinbase": {"BTC-1m": MagicMock()}}
    data_instance.fetcher.fetch_candles = AsyncMock(return_value=expected)
    result = await data_instance.fetch_candles([
        "coinbase"], ["BTC/USD"], "2023-01-01T00:00:00Z", ["1m"], False)
    assert result == expected
    data_instance.fetcher.fetch_candles.assert_awaited_once()
```

### Setup & Teardown

The fixture `data_instance` constructs a `Data` object with mocked dependencies so tests do not access the network. No explicit teardown is required because the objects are lightweight.

### Additional Integration Tests

A higher level test could instantiate a real `SignalEmitter` and a dummy widget. By emitting a trade event through `Streamer`, the test would assert that the widget receives the `NEW_TRADE` signal and updates its state. Such tests require an event loop and may mock the ccxt exchange to feed synthetic trade data.
