import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from trade_suite.data.data_source import Data
from trade_suite.data.ccxt_interface import CCXTInterface


@pytest.fixture
def data_instance():
    """Return a Data object with mocked subcomponents."""
    emitter = MagicMock()
    influx = MagicMock()
    data = Data(influx=influx, emitter=emitter, exchanges=[])
    data.fetcher = MagicMock()
    data.streamer = MagicMock()
    return data


@pytest.mark.asyncio
async def test_load_exchanges_propagates_exchange_list(data_instance):
    """`load_exchanges` should update helper exchange lists."""
    with patch.object(CCXTInterface, "load_exchanges", new=AsyncMock()) as loader:
        data_instance.exchange_list = {"binance": object()}
        await data_instance.load_exchanges(["binance"])
        loader.assert_awaited_once_with(["binance"])
    data_instance.fetcher.set_exchange_list.assert_called_once_with(data_instance.exchange_list)
    data_instance.streamer.set_exchange_list.assert_called_once_with(data_instance.exchange_list)


@pytest.mark.asyncio
async def test_set_ui_loop_passes_through(data_instance):
    """Ensure `set_ui_loop` forwards the loop to the streamer."""
    loop = asyncio.get_event_loop()
    data_instance.set_ui_loop(loop)
    data_instance.streamer.set_ui_loop.assert_called_once_with(loop)


@pytest.mark.asyncio
async def test_watch_trades_delegates(data_instance):
    """Wrapper should await `Streamer.watch_trades` with same parameters."""
    stop = asyncio.Event()
    await data_instance.watch_trades(
        symbol="BTC/USDT",
        exchange="binance",
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
    expected = {"binance": {"BTC-1m": MagicMock()}}
    data_instance.fetcher.fetch_candles = AsyncMock(return_value=expected)
    result = await data_instance.fetch_candles(
        ["binance"], ["BTC/USDT"], "2023-01-01T00:00:00Z", ["1m"], False
    )
    assert result == expected
    data_instance.fetcher.fetch_candles.assert_awaited_once()

