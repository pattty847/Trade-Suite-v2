import dearpygui.dearpygui as dpg

from src.config import ConfigManager
from src.data.data_source import Data
from src.gui.signals import SignalEmitter, Signals


class OrderBook:
    def __init__(self, emitter: SignalEmitter, data: Data, config: ConfigManager):
        self.emitter = emitter
        self.data = data
        self.config = config
        
        self.emitter.register(Signals.ORDER_BOOK_UPDATE, self.on_order_book_update)

        self.aggregated_order_book = True
        self.order_book_levels = 100
        self.tick_size = 10

        self.create_order_book_ui()

    def create_order_book_ui(self):
        with dpg.group(width=300, tag='order_book_group'):
            dpg.add_checkbox(label="Aggregate", default_value=self.aggregated_order_book, callback=self.toggle_aggregated_order_book)
            dpg.add_slider_int(label="Levels", default_value=self.order_book_levels, min_value=5, max_value=1000, callback=self.set_ob_levels)
            with dpg.plot(label="Orderbook", no_title=True, height=-1):
                dpg.add_plot_legend()
                self.ob_xaxis = dpg.add_plot_axis(dpg.mvXAxis)
                with dpg.plot_axis(dpg.mvYAxis, label="Volume") as self.ob_yaxis:
                    self.bids_tag = dpg.add_line_series([], [])
                    self.asks_tag = dpg.add_line_series([], [])

    # Rest of the methods related to order book (update_order_book, set_ob_levels, etc.)

    def on_order_book_update(self, exchange, orderbook):
        bids_df, ask_df, price_column = self.data.agg.on_order_book_update(exchange, orderbook, self.tick_size, self.aggregated_order_book, self.order_book_levels)
        self.update_order_book(bids_df, ask_df, price_column)
    
    def update_order_book(self, bids_df, asks_df, price_column):
        dpg.configure_item(self.bids_tag, x=bids_df[price_column].tolist(), y=bids_df['cumulative_quantity'].tolist())
        dpg.configure_item(self.asks_tag, x=asks_df[price_column].tolist(), y=asks_df['cumulative_quantity'].tolist())
        
        # Find the midpoint
        worst_bid_price = bids_df[price_column].min()
        worst_ask_price = asks_df[price_column].max()
        worst_bid_size = bids_df['cumulative_quantity'].min()
        worst_ask_size = asks_df['cumulative_quantity'].max()

        # Update the x-axis limits
        dpg.set_axis_limits(axis=self.ob_xaxis, ymin=worst_bid_price, ymax=worst_ask_price)
        dpg.set_axis_limits(axis=self.ob_yaxis, ymin=worst_bid_size, ymax=worst_ask_size)
    
    def toggle_aggregated_order_book(self):
        self.aggregated_order_book = not self.aggregated_order_book
                            
    def set_ob_levels(self, levels):
        self.order_book_levels = levels