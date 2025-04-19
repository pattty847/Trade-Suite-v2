import pytest
import pandas as pd
from unittest.mock import MagicMock
from datetime import datetime, timezone

from trade_suite.data.candle_factory import CandleFactory
from trade_suite.gui.utils import timeframe_to_seconds
from trade_suite.gui.signals import Signals

# --- Test Setup ---

@pytest.fixture
def mock_dependencies():
    """Provides mock objects for CandleFactory dependencies."""
    emitter = MagicMock()
    task_manager = MagicMock()
    # Mock the Data object and its exchange_list lookup
    mock_data = MagicMock()
    mock_exchange = MagicMock()
    # Ensure market method returns a dict with precision
    mock_market = MagicMock(return_value={'precision': {'price': 0.01}}) # Example precision
    mock_exchange.market.side_effect = lambda symbol: mock_market() if symbol == "BTC/USDT" else None
    mock_data.exchange_list = {"binance": mock_exchange}
    return emitter, task_manager, mock_data

@pytest.fixture
def candle_factory(mock_dependencies):
    """Provides a CandleFactory instance with mock dependencies."""
    emitter, task_manager, data = mock_dependencies
    factory = CandleFactory(
        exchange="binance",
        emitter=emitter,
        task_manager=task_manager,
        data=data,
        symbol="BTC/USDT",
        timeframe_str="1m",
    )
    # Set initial state explicitly for predictability
    factory.ohlcv = pd.DataFrame(columns=["dates", "opens", "highs", "lows", "closes", "volumes"])
    factory.last_candle_timestamp = None
    return factory

# --- Test Cases ---

def test_process_trade_creates_first_candle(candle_factory):
    """
    Test that processing the first trade correctly initializes the first candle
    in the ohlcv DataFrame.
    """
    # Arrange: Define the first trade data
    # Timestamp for 2023-01-01 10:00:30 UTC (within the 10:00:00 candle)
    trade_ts_ms = int(datetime(2023, 1, 1, 10, 0, 30, tzinfo=timezone.utc).timestamp() * 1000)
    first_trade = {
        "timestamp": trade_ts_ms,
        "price": 50000.0,
        "amount": 0.5,
        "symbol": "BTC/USDT", # Make sure symbol matches factory
        # other fields like 'id', 'side', 'takerOrMaker' might exist but aren't used by _process_trade
    }

    # Act: Process the first trade
    updated = candle_factory._process_trade(first_trade)

    # Assert: Check if the candle was created and has the correct values
    assert updated is True # The method should report an update
    assert len(candle_factory.ohlcv) == 1 # One candle should exist

    first_candle = candle_factory.ohlcv.iloc[0]

    # Calculate expected candle start timestamp (floored to the minute)
    expected_candle_start_ts = trade_ts_ms / 1000 - (trade_ts_ms / 1000 % candle_factory.timeframe_seconds)

    assert first_candle["dates"] == expected_candle_start_ts
    assert first_candle["opens"] == 50000.0
    assert first_candle["highs"] == 50000.0
    assert first_candle["lows"] == 50000.0
    assert first_candle["closes"] == 50000.0
    assert first_candle["volumes"] == 0.5
    assert candle_factory.last_candle_timestamp == expected_candle_start_ts # Ensure internal timestamp is updated

def test_process_trade_updates_existing_candle(candle_factory):
    """
    Test that processing a second trade within the same candle interval
    correctly updates the existing candle's H, L, C, V values.
    """
    # --- Arrange: First Trade (establish the initial candle) ---
    trade_ts_1_ms = int(datetime(2023, 1, 1, 10, 0, 30, tzinfo=timezone.utc).timestamp() * 1000)
    first_trade = {
        "timestamp": trade_ts_1_ms,
        "price": 50000.0,
        "amount": 0.5,
        "symbol": "BTC/USDT",
    }
    candle_factory._process_trade(first_trade) # Process the first trade

    # Ensure the first candle was created as expected
    assert len(candle_factory.ohlcv) == 1
    initial_candle = candle_factory.ohlcv.iloc[0]
    assert initial_candle["closes"] == 50000.0
    assert initial_candle["volumes"] == 0.5

    # --- Arrange: Second Trade (within the same 1m interval) ---
    # Timestamp for 2023-01-01 10:00:45 UTC (still within the 10:00:00 candle)
    trade_ts_2_ms = int(datetime(2023, 1, 1, 10, 0, 45, tzinfo=timezone.utc).timestamp() * 1000)
    second_trade = {
        "timestamp": trade_ts_2_ms,
        "price": 50100.0, # Higher price
        "amount": 0.3,   # Different amount
        "symbol": "BTC/USDT",
    }

    # --- Act: Process the second trade ---
    updated = candle_factory._process_trade(second_trade)

    # --- Assert: Check if the existing candle was updated correctly ---
    assert updated is True # The method should report an update
    assert len(candle_factory.ohlcv) == 1 # Should still only have one candle

    updated_candle = candle_factory.ohlcv.iloc[0] # Get the (only) candle

    # Calculate expected candle start timestamp (should be the same as before)
    expected_candle_start_ts = trade_ts_1_ms / 1000 - (trade_ts_1_ms / 1000 % candle_factory.timeframe_seconds)

    assert updated_candle["dates"] == expected_candle_start_ts
    assert updated_candle["opens"] == 50000.0  # Open remains from the first trade
    assert updated_candle["highs"] == 50100.0  # High updated to the second trade's price
    assert updated_candle["lows"] == 50000.0   # Low remains from the first trade's price
    assert updated_candle["closes"] == 50100.0 # Close updated to the second trade's price
    assert updated_candle["volumes"] == 0.5 + 0.3 # Volume is accumulated
    assert candle_factory.last_candle_timestamp == expected_candle_start_ts # Internal timestamp unchanged

def test_process_trade_creates_new_bar(candle_factory):
    """
    Test that processing a trade falling into the next interval
    correctly creates a new candle bar.
    """
    # --- Arrange: First Trade (establish the 10:00 candle) ---
    trade_ts_1_ms = int(datetime(2023, 1, 1, 10, 0, 30, tzinfo=timezone.utc).timestamp() * 1000)
    first_trade = {
        "timestamp": trade_ts_1_ms, "price": 50000.0, "amount": 0.5, "symbol": "BTC/USDT",
    }
    candle_factory._process_trade(first_trade)
    first_candle_ts = candle_factory.last_candle_timestamp
    assert len(candle_factory.ohlcv) == 1

    # --- Arrange: Second Trade (falls into the 10:01 candle interval) ---
    # Timestamp for 2023-01-01 10:01:15 UTC
    trade_ts_2_ms = int(datetime(2023, 1, 1, 10, 1, 15, tzinfo=timezone.utc).timestamp() * 1000)
    second_trade = {
        "timestamp": trade_ts_2_ms,
        "price": 50200.0,
        "amount": 0.2,
        "symbol": "BTC/USDT",
    }

    # --- Act: Process the second trade ---
    updated = candle_factory._process_trade(second_trade)

    # --- Assert: Check that a new candle was created ---
    assert updated is True # The method should report an update
    assert len(candle_factory.ohlcv) == 2 # Should now have two candles

    # --- Assert: Check the properties of the *new* (second) candle ---
    new_candle = candle_factory.ohlcv.iloc[1] # Get the second candle

    # Calculate expected timestamp for the new candle (start of the 10:01 interval)
    expected_new_candle_ts = first_candle_ts + candle_factory.timeframe_seconds

    assert new_candle["dates"] == expected_new_candle_ts
    # New candle OHLCV should be based *only* on the second trade
    assert new_candle["opens"] == 50200.0
    assert new_candle["highs"] == 50200.0
    assert new_candle["lows"] == 50200.0
    assert new_candle["closes"] == 50200.0
    assert new_candle["volumes"] == 0.2
    # Check that the factory's internal timestamp tracker was updated
    assert candle_factory.last_candle_timestamp == expected_new_candle_ts

    # --- Assert: Check the properties of the *first* candle remain unchanged ---
    # (Optional but good practice)
    first_candle_recheck = candle_factory.ohlcv.iloc[0]
    assert first_candle_recheck["dates"] == first_candle_ts
    assert first_candle_recheck["closes"] == 50000.0
    assert first_candle_recheck["volumes"] == 0.5

def test_on_new_trade_filters_correctly(candle_factory: CandleFactory, mock_dependencies):
    """
    Test that _on_new_trade only queues trades matching the factory's
    exchange and symbol.
    """
    emitter, task_manager, data = mock_dependencies # We might need the emitter later

    # Arrange: Define trades - one matching, one with wrong symbol, one with wrong exchange
    trade_ts_ms = int(datetime(2023, 1, 1, 10, 0, 30, tzinfo=timezone.utc).timestamp() * 1000)

    matching_trade = {
        "timestamp": trade_ts_ms, "price": 50000.0, "amount": 0.5, "symbol": "BTC/USDT",
    }
    wrong_symbol_trade = {
        "timestamp": trade_ts_ms, "price": 2000.0, "amount": 1.0, "symbol": "ETH/USDT", # Wrong symbol
    }
    wrong_exchange_trade = {
        "timestamp": trade_ts_ms, "price": 51000.0, "amount": 0.1, "symbol": "BTC/USDT",
    }

    # Mock _process_trade_batch to prevent it from running automatically for now
    # We only want to check the queue state after _on_new_trade
    candle_factory._process_trade_batch = MagicMock()

    # Act: Send trades to the handler
    candle_factory._on_new_trade(exchange="binance", trade_data=matching_trade)
    candle_factory._on_new_trade(exchange="binance", trade_data=wrong_symbol_trade)
    candle_factory._on_new_trade(exchange="kraken", trade_data=wrong_exchange_trade) # Wrong exchange

    # Assert: Check the internal queue content
    # Should only contain the trade that matched both exchange and symbol
    assert len(candle_factory._trade_queue) == 1
    queued_trade = candle_factory._trade_queue[0]
    assert queued_trade["symbol"] == "BTC/USDT"
    assert queued_trade["price"] == 50000.0

    # Assert that _process_trade_batch was NOT called because the queue didn't reach the threshold (default 5)
    # If the threshold was 1, this would be called once.
    candle_factory._process_trade_batch.assert_not_called()

def test_process_trade_batch_emits_signal(candle_factory: CandleFactory, mock_dependencies):
    """
    Test that _process_trade_batch emits the UPDATED_CANDLES signal
    after successfully processing trades that update a candle.
    """
    emitter, _, _ = mock_dependencies # Get the mock emitter

    # Arrange: Manually add a trade to the queue that will cause an update
    trade_ts_ms = int(datetime(2023, 1, 1, 10, 0, 30, tzinfo=timezone.utc).timestamp() * 1000)
    trade = {
        "timestamp": trade_ts_ms, "price": 50000.0, "amount": 0.5, "symbol": "BTC/USDT",
    }
    candle_factory._trade_queue.append(trade)

    # Arrange: Ensure the internal state allows for an update (e.g., empty ohlcv)
    assert len(candle_factory.ohlcv) == 0

    # Act: Call the batch processing method directly
    candle_factory._process_trade_batch()

    # Assert: Check that the emitter was called
    emitter.emit.assert_called_once()

    # Assert: Check the arguments passed to the emitter
    # call_args[0] are positional args, call_args[1] are keyword args
    args, kwargs = emitter.emit.call_args
    expected_signal = Signals.UPDATED_CANDLES
    expected_exchange = candle_factory.exchange
    expected_symbol = candle_factory.symbol
    expected_timeframe = candle_factory.timeframe_str

    # The emitted candle should be the last (and only, in this case) candle in the dataframe
    assert not candle_factory.ohlcv.empty # Ensure a candle was actually created
    expected_candles_df = candle_factory.ohlcv.iloc[-1:] # Get last row as DataFrame

    assert len(args) == 1 # Only the signal name is positional
    assert args[0] == expected_signal
    assert kwargs.get("exchange") == expected_exchange
    assert kwargs.get("symbol") == expected_symbol
    assert kwargs.get("timeframe") == expected_timeframe

    # Compare the DataFrame content
    emitted_candles_df = kwargs.get("candles")
    assert isinstance(emitted_candles_df, pd.DataFrame)
    pd.testing.assert_frame_equal(emitted_candles_df, expected_candles_df)

    # Assert: Check that the queue is now empty
    assert len(candle_factory._trade_queue) == 0

# More tests to follow...
# def test_multiple_trades_within_interval():
#     pass
# def test_trades_spanning_multiple_intervals():
#     pass
# def test_process_trade_batch_emits_signal(): # Test the signal emission
#     pass 