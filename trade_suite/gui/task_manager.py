import asyncio
import logging
import threading

from trade_suite.data.data_source import Data
from trade_suite.gui.signals import Signals
from trade_suite.gui.utils import calculate_since


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
        print(self.visable_tab)

    def run_loop(self):
        logging.info(f"Starting async thread.")
        asyncio.set_event_loop(self.loop)
        self.loop.run_forever()

    def start_task(self, name: str, coro):
        logging.info(f"Starting new task {name}")
        task = asyncio.run_coroutine_threadsafe(coro, self.loop)
        self.tasks[name] = task
        task.add_done_callback(lambda t: self.tasks.pop(name, None))

    def start_stream_for_chart(self, tab, exchange, symbol, timeframe):
        print(exchange, symbol, timeframe)
        trades_task = f"trades_{symbol}_{exchange}"
        orderbook_task = f"orderbook_{symbol}_{exchange}"

        if tab in self.tabs:
            for task in self.tabs[tab]:
                print(f"stopping {task}")
                self.stop_task(task)
                self.stop_task(task)

        self.get_candles_for_market(
            exchange, symbol, timeframe
        )  # This will emit the candles to listeners

        self.start_task(
            trades_task,
            coro=self.data.watch_trades(
                exchange=exchange, symbol=symbol, track_stats=True
            ),
        )

        self.start_task(
            orderbook_task,
            coro=self.data.watch_orderbook(
                exchange=exchange,
                symbol=symbol,
            ),
        )

        self.tabs[tab] = [trades_task, orderbook_task]
        print(self.tabs)

    def get_candles_for_market(self, exchange, symbol, timeframe):
        since = calculate_since(
            self.data.exchange_list[exchange]["ccxt"], timeframe, 365
        )
        # We need to fetch the candles (wait for them), this emits 'Signals.NEW_CANDLES', func 'on_new_candles' should set them
        self.run_task_until_complete(
            self.data.fetch_candles(
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
