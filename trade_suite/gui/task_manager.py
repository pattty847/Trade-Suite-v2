import asyncio
import logging
import threading
import dearpygui.dearpygui as dpg

from trade_suite.data.data_source import Data
from trade_suite.gui.signals import Signals
from trade_suite.gui.utils import calculate_since, create_loading_modal


class TaskManager:
    def __init__(self, data: Data):
        self.loop = asyncio.new_event_loop()
        self.thread = threading.Thread(target=self.run_loop, daemon=True)
        self.thread.start()
        self.tasks = {}
        self.data = data
        self.active_symbol = None
        self.visable_tab = None
        self.tabs = {}

    def set_visable_tab(self, sender, app_data, user_data):
        self.visable_tab = app_data

    def run_loop(self):
        logging.info(f"Starting async thread.")
        asyncio.set_event_loop(self.loop)
        self.loop.run_forever()

    def start_task(self, name: str, coro):
        task = asyncio.run_coroutine_threadsafe(coro, self.loop)
        self.tasks[name] = task
        task.add_done_callback(lambda t: self.tasks.pop(name, None))

    def start_stream_for_chart(self, tab, exchange, symbol, timeframe):
        
        trades_task = f"trades_{exchange}_{symbol}_{tab}"
        orderbook_task = f"orderbook_{exchange}_{symbol}_{tab}"

        # We want to stop the old symbol's tasks for the tab when requesting a new stream
        if tab in self.tabs:
            for task in self.tabs[tab]:
                logging.info(f"stopping {task}")
                self.stop_task(task)
                self.stop_task(task)

        self.get_candles_for_market(
            tab, exchange, symbol, timeframe
        )  # This will emit the candles to listeners

        self.start_task(
            trades_task,
            coro=self.data.watch_trades(
                tab=tab, exchange=exchange, symbol=symbol, track_stats=True
            ),
        )

        self.start_task(
            orderbook_task,
            coro=self.data.watch_orderbook(
                tab=tab,
                exchange=exchange,
                symbol=symbol,
            ),
        )

        self.tabs[tab] = [trades_task, orderbook_task]

    def get_candles_for_market(self, tab, exchange, symbol, timeframe):
        # TODO: Make number of candles variable
        since = calculate_since(
            self.data.exchange_list[exchange]["ccxt"], timeframe, num_candles=365
        )

        self.run_task_until_complete(
            self.data.fetch_candles(
                tab=tab,
                exchanges=[exchange],
                symbols=[symbol],
                timeframes=[timeframe],
                since=since,
                write_to_db=False,
            )
        )

    def run_task_until_complete(self, coro):
        future = asyncio.run_coroutine_threadsafe(coro, self.loop)
        try:
            return future.result()
        except asyncio.CancelledError:
            logging.error("Task was cancelled.")
            # Handle task cancellation, if needed
        except Exception as e:
            logging.error(f"An unexpected error occurred: {e}")
            # Handle other exceptions
        
    def run_task_with_loading_popup(self, coro, message="Please wait..."):
        future = asyncio.run_coroutine_threadsafe(coro, self.loop)
        # Display the loading modal
        create_loading_modal(message)

        def on_task_complete(fut):
            # This function will be called when the future completes
            dpg.delete_item("loading_modal")
            try:
                return fut.result()
            except asyncio.CancelledError:
                logging.error("Task was cancelled.")
                # Handle task cancellation, if needed
            except Exception as e:
                logging.error(f"An unexpected error occurred: {e}")
                # Handle other exceptions

        # Add the completion callback to the future
        future.add_done_callback(on_task_complete)
        return future.result()


    def stop_task(self, name: str):
        if name in self.tasks:
            logging.info(f"Stopping task {name}")
            self.tasks[name].cancel()

    def stop_all_tasks(self):
        if not self.tasks:
            return
        logging.info(f"Stopping all async tasks: {list(self.tasks.keys())}")
        tasks_copy = dict(self.tasks)  # Create a copy of the dictionary
        for task in tasks_copy.values():
            task.cancel()
        self.tasks.clear()
