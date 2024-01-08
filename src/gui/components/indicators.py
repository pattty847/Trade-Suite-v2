import dearpygui.dearpygui as dpg
import pandas as pd

from src.gui.signals import SignalEmitter, Signals

class Indicators:
    
    def __init__(self, emitter: SignalEmitter) -> None:
        self.emitter = emitter
        self.in_trade_mode = False
        self.trade_mode_drag_line_tag = False
        self.candle_series_yaxis = None # tag to candle stick plot
        self.last_candle_timestamp = None
        
        self.ohlcv = pd.DataFrame(columns=['dates', 'opens', 'highs', 'lows', 'closes', 'volumes'])
        
        self.register_event_listeners()
        
    def register_event_listeners(self):
        event_mappings = {
            Signals.NEW_TRADE: self.on_new_trade,
            Signals.NEW_CANDLES: self.on_new_candles,
        }
        for signal, handler in event_mappings.items():
            self.emitter.register(signal, handler)
            
    def on_new_candles(self, candles):
        if isinstance(candles, pd.DataFrame):
            self.ohlcv = candles
        
    def on_new_trade(self, exchange, trade_data):
        timestamp = trade_data['timestamp'] / 1000  # Convert ms to seconds
        price = trade_data['price']
        volume = trade_data['amount']
            
        
    def setup_trading_actions_menu(self):
        with dpg.menu(label="Trading Actions"):
            dpg.add_checkbox(label="Trade Line", callback=self.toggle_drag_line)
            dpg.add_menu_item(label="Trade", callback=self.toggle_place_order)

            # Adding a tooltip to the menu to give users more information
            with dpg.tooltip(dpg.last_item()):
                dpg.add_text("Use these options to manage trading on the chart.\n"
                            "'Trade Line' will show or hide the line where you can place your trade.\n"
                            "'Trade' will open the trade window at the line's price.")
                
    def setup_line_series_menu(self):
        with dpg.menu(label="Indicators"):
            with dpg.menu(label="Moving Averages"):
                dpg.add_menu_item(label="EMAs", callback=self.add_line_series)
    
    def add_line_series(self):
        span = [10, 25, 50, 100, 200]
        ema_values = [self.ohlcv['closes'].ewm(span=x, adjust=False).mean().tolist() for x in span]
        
        for ema, span_value in zip(ema_values, span):
            label = f"EMA {span_value}"
            dpg.add_line_series(list(self.ohlcv['dates']), list(ema), label=label, parent=self.candle_series_yaxis)
            
    def toggle_drag_line(self):
        self.in_trade_mode = not self.in_trade_mode
        if self.in_trade_mode: 
            dpg.configure_item(self.trade_mode_drag_line_tag, show=True, default_value=self.ohlcv['closes'].tolist()[-1])
        else: 
            dpg.configure_item(self.trade_mode_drag_line_tag, show=False)
    
    def toggle_place_order(self):
        price = dpg.get_value(self.trade_mode_drag_line_tag)
        
        def apply_percentage(profit_pct):
            percentage = dpg.get_value(profit_pct) / 100
            take_profit_price = price * (1 + percentage)
            dpg.set_value(profit_pct, take_profit_price)

        if not dpg.does_item_exist("order_window"):
            # Create the window once
            width, height = 400, 200
            with dpg.window(
                label="Place Order", 
                modal=True, 
                tag="order_window",
                width=width, height=height,
                pos=(dpg.get_viewport_width() / 2 - width/2, dpg.get_viewport_height() / 2 - height/2), 
                show=False):
                price_ = dpg.add_input_float(label="Price", default_value=price)
                stop = dpg.add_input_float(label="Stop Loss")
                profit_pct = dpg.add_input_float(label="Take Profit")
                size = dpg.add_input_int(label="Size")

                # Quick buttons for setting take profit percentage
                with dpg.group(horizontal=True):
                    for percent in [2, 3, 5]:
                        dpg.add_button(label=f"{percent}%", callback=lambda: apply_percentage(profit_pct), user_data=percent)

                order = (price_, stop, profit_pct, size)
                with dpg.group(horizontal=True):
                    dpg.add_button(label="Long", callback=self.place_order, user_data=(order, "Long"))
                    dpg.add_button(label="Short", callback=self.place_order, user_data=(order, "Short"))

        # Show or hide the window
        if dpg.is_item_shown("order_window"):
            dpg.hide_item("order_window")
        else:
            dpg.show_item("order_window")
            
    
    def place_order(self, sender, app_data, user_data):
        price, stop, profit_pct, size = [dpg.get_value(item) for item in user_data[0]]
        side = user_data[1]
        
        print(price, stop, profit_pct, size, side)
        # Set the color based on the value of 'side'
        if side == "Short":
            color = (255, 0, 0, 255)  # Red color for 'Short'
        elif side == "Long":
            color = (0, 255, 0, 255)  # Green color for 'Long'
        else:
            color = (255, 255, 255, 255)  # Default to white if side is neither

        # Add a drag line with the specified color
        dpg.add_drag_line(label=f"{side}|{price}", default_value=price, vertical=False, parent=self.candle_series_yaxis, color=color)