import dearpygui.dearpygui as dpg
import pandas as pd
import pandas_ta

from trade_suite.gui.signals import SignalEmitter, Signals
from trade_suite.gui.utils import timeframe_to_seconds


class Indicators:
    def __init__(self, exchange, emitter: SignalEmitter, exchange_settings) -> None:
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

        self.register_event_listeners()

    def register_event_listeners(self):
        event_mappings = {
            Signals.NEW_TRADE: self.on_new_trade,
            Signals.NEW_CANDLES: self.on_new_candles,
            Signals.TIMEFRAME_CHANGED: self.on_timeframe_change,
        }

        for signal, handler in event_mappings.items():
            self.emitter.register(signal, handler)

    def on_timeframe_change(self, exchange, new_timeframe: str):
        if exchange == self.exchange:
            timeframe_in_minutes = timeframe_to_seconds(new_timeframe)
            self.timeframe_str = new_timeframe
            self.timeframe_seconds = timeframe_in_minutes

            if self.show_ema:
                self.recalculate_ema()

    def on_new_candles(self, exchange, candles):
        if isinstance(candles, pd.DataFrame) and exchange == self.exchange:
            self.ohlcv = candles

        if self.show_ema:
            self.recalculate_ema()

    def on_new_trade(self, exchange, trade_data):
        timestamp = trade_data["timestamp"] / 1000  # Convert ms to seconds
        price = trade_data["price"]
        volume = trade_data["amount"]

    def create_indicators_menu(self):
        with dpg.menu(label="Indicators"):
            with dpg.menu(label="Moving Averages"):
                dpg.add_checkbox(
                    label="EMAs", default_value=self.show_ema, callback=self.toggle_ema
                )

            self.create_test_menu()

    def toggle_ema(self, sender, app_data, user_data):
        self.show_ema = not self.show_ema
        if not self.line_series_ids:
            # If no EMA series exist, recalculate and add them
            self.recalculate_ema()
        else:
            # If EMA series exist, just toggle their visibility
            for line_series_id in self.line_series_ids.values():
                dpg.configure_item(line_series_id, show=self.show_ema)

    def recalculate_ema(self):
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
            self.add_line_series(ema_values)

    def add_line_series(self, ema_values):
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

    def create_test_menu(self):
        indicators = pandas_ta.Category
        with dpg.menu(label="Indicators (Testing)"):
            for category, indicators in indicators.items():
                with dpg.menu(label=category.capitalize()):
                    for indicator in indicators:
                        dpg.add_checkbox(
                            label=indicator,
                            callback=lambda s, a, u: print(s, a, indicator),
                        )

    def add_indicator_to_chart(self, indicator_name, **kwargs):
        # Retrieve the indicator function from pandas_ta
        indicator_function = getattr(pandas_ta, indicator_name, None)

        if indicator_function is None:
            print(f"No indicator found with name: {indicator_name}")
            return

        # Calculate the indicator values. You may need to pass additional parameters depending on the indicator.
        indicator_values = indicator_function(self.ohlcv, **kwargs)

        # Convert the result to a format suitable for the chart if necessary
        # Some indicators return a DataFrame, others might return a Series
        if isinstance(indicator_values, pd.DataFrame):
            for column in indicator_values.columns:
                self.plot_indicator_series(
                    indicator_values[column], label=f"{indicator_name} {column}"
                )
        elif isinstance(indicator_values, pd.Series):
            self.plot_indicator_series(indicator_values, label=indicator_name)
        else:
            print(f"Unhandled indicator result type: {type(indicator_values)}")

    def plot_indicator_series(self, values, label):
        # Assuming 'values' is a pandas Series with the indicator results
        # This function should add the line series to the chart using the DearPyGUI API
        line_series_id = dpg.add_line_series(
            list(self.ohlcv.index), list(values), label=label
        )
        self.line_series_ids[
            label
        ] = line_series_id  # Store the line series ID for future reference

    def toggle_indicator(self, u):
        print(u)
