import inspect
import logging
import dearpygui.dearpygui as dpg
import pandas as pd

from gui.signals import SignalEmitter, Signals
from gui.utils import center_window, timeframe_to_seconds


class Indicators:
    def __init__(
        self, tab, exchange, emitter: SignalEmitter, exchange_settings
    ) -> None:
        self.tab = tab
        self.exchange = exchange
        self.emitter = emitter
        self.exchange_settings = exchange_settings

        self.timeframe_str = (
            self.exchange_settings["last_timeframe"]
            if self.exchange_settings
            else "15m"
        )
        self.timeframe_seconds = timeframe_to_seconds(
            self.timeframe_str
        )  # Timeframe for the candles in seconds

        self.candle_series_yaxis = None

        self.ohlcv = pd.DataFrame(
            columns=["dates", "opens", "highs", "lows", "closes", "volumes"]
        )

        self.show_ema = False
        self.line_series_ids = {}
        self.span = [10, 25, 50, 100, 200]
        self.indicators = {
            "ema": {
                "length": {
                    "default": [10, 25, 50, 100, 200],
                    "source": "close",
                    "type": "int",
                }
            },
            "sma": {
                "length": {
                    "default": [10, 25, 50, 100, 200],
                    "source": "close",
                    "type": "int",
                }
            },
        }

        self._register_event_listeners()

    def _register_event_listeners(self):
        event_mappings = {
            Signals.NEW_TRADE: self._on_new_trade,
            Signals.NEW_CANDLES: self._on_new_candles,
            Signals.UPDATED_CANDLES: self._on_updated_candles,
            Signals.TIMEFRAME_CHANGED: self._on_timeframe_change,
        }

        for signal, handler in event_mappings.items():
            self.emitter.register(signal, handler)

    def _on_timeframe_change(self, tab, exchange, new_timeframe: str):
        if tab != self.tab:
            timeframe_in_minutes = timeframe_to_seconds(new_timeframe)
            self.timeframe_str = new_timeframe
            self.timeframe_seconds = timeframe_in_minutes

    # Listens for initial candle emissions
    def _on_new_candles(self, tab, exchange, candles):
        if isinstance(candles, pd.DataFrame) and tab == self.tab:
            self.ohlcv = candles
            
            if self.show_ema:
                self._recalculate_ema()

    # Always listening for the updated candle stick chart
    def _on_updated_candles(self, tab, exchange, candles):
        if isinstance(candles, pd.DataFrame) and tab == self.tab:
            self.ohlcv = candles

            if self.show_ema:
                self._recalculate_ema()

    def _on_new_trade(self, tab, exchange, trade_data):
        timestamp = trade_data["timestamp"] / 1000  # Convert ms to seconds
        price = trade_data["price"]
        volume = trade_data["amount"]

    def create_indicators_menu(self):
        with dpg.menu(label="Indicators") as menu:
            with dpg.menu(label="Moving Averages"):
                dpg.add_checkbox(
                    label="EMAs", default_value=self.show_ema, callback=self._toggle_ema
                )
                dpg.add_button(label="test", callback=self._toggle_cvd)


    def _toggle_cvd(self, sender, app_data, user_data):
        pass

    def _toggle_ema(self, sender, app_data, user_data):
        self.show_ema = not self.show_ema
        if not self.line_series_ids:
            # If no EMA series exist, recalculate and add them
            self._recalculate_ema()
        else:
            # If EMA series exist, just toggle their visibility
            for line_series_id in self.line_series_ids.values():
                dpg.configure_item(line_series_id, show=self.show_ema)

    def _recalculate_ema(self):
        # Calculate EMA values
        ema_values = [
            self.ohlcv["closes"].ewm(span=x, adjust=False).mean().tolist()
            for x in self.span
        ]

        if self.line_series_ids:
            # If EMAs are already plotted, update them
            for ema, span_value in zip(ema_values, self.span):
                if span_value in self.line_series_ids:
                    line_series_id = self.line_series_ids[span_value]
                    dpg.set_value(
                        line_series_id, [list(self.ohlcv["dates"]), list(ema)]
                    )
        else:
            # If not plotted, add them as new line series
            self._add_line_series(ema_values)

    def _add_line_series(self, ema_values):
        # Add line series for EMAs
        for ema, span_value in zip(ema_values, self.span):
            label = f"EMA {span_value}"
            if span_value not in self.line_series_ids:
                # Add the line series if it doesn't exist
                line_series_id = dpg.add_line_series(
                    list(self.ohlcv["dates"]),
                    list(ema),
                    label=label,
                    parent=self.candle_series_yaxis,
                )
                self.line_series_ids[span_value] = line_series_id
            else:
                # Update the line series if it does exist
                line_series_id = self.line_series_ids[span_value]
                dpg.set_value(line_series_id, [list(self.ohlcv["dates"]), list(ema)])

        # Ensure that the visibility matches the current toggle state
        for line_series_id in self.line_series_ids.values():
            dpg.configure_item(line_series_id, show=self.show_ema)
