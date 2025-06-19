# sentinel/supervisor.py
import asyncio
import logging
import os
import signal # For graceful shutdown
import logging.handlers # For RotatingFileHandler
from typing import Optional

from sentinel.collectors.coinbase import stream_data_to_queues
from sentinel.config import INFLUX_CONFIG, WS_RECONNECT_BACKOFF
from sentinel.writers.influx_writer import InfluxWriter
from trade_suite.core.data.data_source import Data as TradeSuiteData # Alias to avoid confusion
from sentinel import config

# Basic logging setup - consider using structlog as planned for richer logs
# Get the root logger
root_logger = logging.getLogger() 
root_logger.setLevel(getattr(logging, config.LOG_LEVEL.upper(), logging.INFO))

# Quieten noisy libraries if root is DEBUG
if root_logger.level == logging.DEBUG:
    for lib_name in ["ccxt", "aiohttp", "websockets"]:
        logging.getLogger(lib_name).setLevel(logging.INFO)

# File Handler with Rotation
file_handler = logging.handlers.RotatingFileHandler(
    config.LOG_FILE, 
    maxBytes=10*1024*1024, # e.g., 10 MB per file
    backupCount=5          # Keep 5 backup files
)
file_formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
file_handler.setFormatter(file_formatter)
root_logger.addHandler(file_handler)

# Console Handler
console_handler = logging.StreamHandler()
console_formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s') # Simpler format for console
console_handler.setFormatter(console_formatter)
root_logger.addHandler(console_handler)

logger = logging.getLogger(__name__) # Supervisor specific logger

class Supervisor:
    def __init__(self, is_raw_enabled: bool = False, data_source: Optional[TradeSuiteData] = None): # Accept data_source
        self.is_raw_enabled = is_raw_enabled
        self.trade_queue = asyncio.Queue(maxsize=10000)
        self.order_book_queue = asyncio.Queue(maxsize=10000)
        self.raw_order_book_queue = asyncio.Queue(maxsize=10000) if self.is_raw_enabled else None
        self.stop_event = asyncio.Event()
        self.tasks = []

        # For healthz
        self.dropped_trades_count = 0
        self.dropped_binned_books_count = 0
        self.dropped_raw_books_count = 0
        # The collector will have its own counters, this is illustrative
        # The actual counters should be accessed from collector or passed via a shared mechanism if needed here

        # Initialize InfluxWriter
        influx_token = os.getenv("INFLUXDB_TOKEN_LOCAL")
        if not influx_token:
            logger.critical("INFLUXDB_TOKEN_LOCAL environment variable not set. Sentinel cannot start.")
            raise ValueError("InfluxDB token not found in environment.")
        
        self.influx_writer = InfluxWriter(
            influx_url=config.INFLUX_URL_LOCAL,
            influx_token=influx_token,
            influx_org=config.INFLUX_ORG
        )

        # Initialize TradeSuiteData (DataSource)
        if data_source:
            self.data_source = data_source
            logger.info("Supervisor is using a provided DataSource instance.")
        else:
            logger.info("No DataSource provided. Supervisor is creating its own instance for standalone operation.")
            # No emitter needed for sentinel's use case. Influx client is managed by InfluxWriter.
            self.data_source = TradeSuiteData(influx=None, emitter=None, exchanges=[config.TARGET_EXCHANGE], force_public=True)
        
        self._is_standalone = data_source is None

    async def _run_with_restart(self, coro_func, *args, name="UnnamedTask"):
        """Runs a coroutine and restarts it with exponential backoff on failure."""
        backoff_times = config.WS_RECONNECT_BACKOFF
        attempt = 0
        while not self.stop_event.is_set():
            try:
                logger.info(f"Starting task: {name}")
                await coro_func(*args)
                # If the coro_func returns normally, it might mean it completed (e.g. stop_event was set internally)
                # or an unexpected exit. If it's not due to stop_event, we might want to restart.
                if self.stop_event.is_set():
                    logger.info(f"Task {name} stopped gracefully via stop_event.")
                    break
                else:
                    logger.warning(f"Task {name} exited unexpectedly. Restarting after delay...")
                    # This case might need specific handling based on why a task would exit normally
                    # without stop_event being set.
            except asyncio.CancelledError:
                logger.info(f"Task {name} was cancelled.")
                break # Do not restart if explicitly cancelled
            except Exception as e:
                logger.error(f"Task {name} failed with error: {e}. Attempt {attempt + 1}.")
            
            if self.stop_event.is_set():
                break

            if attempt < len(backoff_times):
                delay = backoff_times[attempt]
                logger.info(f"Restarting {name} in {delay} seconds...")
                await asyncio.sleep(delay)
                attempt += 1
            else:
                logger.error(f"Task {name} failed maximum restart attempts. Giving up.")
                self.stop_event.set() # Signal other tasks to stop as a critical component failed
                break
        logger.info(f"Task {name} has finished its lifecycle.")

    async def _healthz(self, interval_seconds: int = 30):
        """Periodically logs queue sizes and other health metrics."""
        logger.info("Healthz monitor started.")
        while not self.stop_event.is_set():
            try:
                # Note: Accessing internal collector counters directly isn't clean.
                # Ideally, collector exposes these or healthz is part of the collector, 
                # or metrics are pushed to a central place (like Prometheus later).
                # For now, logging queue sizes is a good start.
                trade_q_size = self.trade_queue.qsize()
                binned_book_q_size = self.order_book_queue.qsize()
                raw_book_q_size = self.raw_order_book_queue.qsize() if self.raw_order_book_queue else 'N/A'
                
                logger.info(
                    f"[Healthz] Queues - Trades: {trade_q_size}, BinnedBooks: {binned_book_q_size}, RawBooks: {raw_book_q_size}"
                    # f", Dropped - Trades: {self.dropped_trades_count}, Binned: {self.dropped_binned_books_count}, Raw: {self.dropped_raw_books_count}"
                )
                # Resetting supervisor-level counters would require collector to update them.
                # For simplicity, we'll rely on collector logs for drops for now.
                
                await asyncio.sleep(interval_seconds)
            except asyncio.CancelledError:
                logger.info("Healthz monitor cancelled.")
                break
            except Exception as e:
                logger.error(f"Healthz monitor encountered an error: {e}", exc_info=True)
                # Avoid healthz crashing the supervisor; wait and continue
                await asyncio.sleep(interval_seconds) 
        logger.info("Healthz monitor stopped.")

    async def start(self, duration_seconds: float | None = None):
        """Starts the collector and writer tasks and manages them."""
        logger.info("Supervisor starting...")
        if not self.influx_writer or not self.influx_writer.write_api:
            logger.critical("InfluxWriter not properly initialized. Supervisor cannot start data flow.")
            return

        # If running standalone, we need to load the exchanges ourselves.
        if self._is_standalone:
            await self.data_source.load_exchanges() 
            
        if config.TARGET_EXCHANGE not in self.data_source.exchange_list:
            logger.critical(f"Target exchange '{config.TARGET_EXCHANGE}' not loaded in DataSource. Aborting.")
            return

        # Collector task
        collector_task = asyncio.create_task(
            self._run_with_restart(
                stream_data_to_queues,
                self.data_source,
                config.TARGET_SYMBOL_CCXT,
                self.stop_event,
                self.trade_queue,
                self.order_book_queue,
                self.is_raw_enabled, # Pass is_raw_enabled
                self.raw_order_book_queue, # Pass raw queue
                config.TARGET_EXCHANGE,
                config.CADENCE_MS,
                name="DataCollector"
            )
        )
        self.tasks.append(collector_task)

        # Writer task for trades
        trade_writer_task = asyncio.create_task(
            self._run_with_restart(
                self.influx_writer.run_queue_consumer,
                self.trade_queue,
                config.INFLUX_BUCKET_TR,
                self.stop_event,
                name="TradeInfluxWriter"
            )
        )
        self.tasks.append(trade_writer_task)

        # Writer task for order books
        ob_writer_task = asyncio.create_task(
            self._run_with_restart(
                self.influx_writer.run_queue_consumer,
                self.order_book_queue,
                config.INFLUX_BUCKET_OB,
                self.stop_event,
                name="OrderBookInfluxWriter"
            )
        )
        self.tasks.append(ob_writer_task)

        # Writer task for raw order books (if enabled)
        if self.is_raw_enabled and self.raw_order_book_queue:
            raw_ob_writer_task = asyncio.create_task(
                self._run_with_restart(
                    self.influx_writer.run_queue_consumer,
                    self.raw_order_book_queue,
                    config.INFLUX_BUCKET_OB_RAW, # Use the new raw bucket config
                    self.stop_event,
                    name="RawOrderBookInfluxWriter"
                )
            )
            self.tasks.append(raw_ob_writer_task)
            logger.info("Raw order book writer task created.")

        # Healthz task
        healthz_task = asyncio.create_task(self._healthz())
        self.tasks.append(healthz_task)

        logger.info("All tasks created. Supervisor is running.")

        if duration_seconds:
            logger.info(f"Running for a specified duration: {duration_seconds} seconds.")
            await asyncio.sleep(duration_seconds)
            logger.info("Specified duration ended. Initiating shutdown.")
            await self.stop()
        else:
            # Keep running until stop_event is set (e.g., by signal handler or error)
            await self.stop_event.wait()
            logger.info("Stop event received. Initiating shutdown.")
            # Ensure stop is called if loop exited due to stop_event
            # This path is taken if stop() is called from elsewhere, like a signal handler

        # Fallback: if duration_seconds was None and stop_event was set, ensure cleanup
        # await self.stop() # This might be redundant if stop() is what set the event

    async def stop(self):
        logger.info("Supervisor stopping... Setting stop event.")
        self.stop_event.set()

        # Wait for tasks to complete with a timeout
        # Give some time for tasks to handle the stop_event and flush
        logger.info(f"Waiting for {len(self.tasks)} tasks to finish...")
        done, pending = await asyncio.wait(self.tasks, timeout=10.0) # 10s timeout for graceful shutdown

        for task in pending:
            logger.warning(f"Task {task.get_name()} did not finish in time. Cancelling...")
            task.cancel()
        
        # Re-await pending tasks to process cancellations
        if pending:
             await asyncio.wait(pending, timeout=5.0) 

        logger.info("Closing InfluxWriter...")
        if self.influx_writer:
            self.influx_writer.close()
        
        logger.info("Closing DataSource connections...")
        await self.data_source.close_all_exchanges() # Ensure data_source has this method or adapt

        logger.info("Supervisor stopped.")

# Main execution / CLI entry point would typically be in run.py
# This is just for structure
async def main_supervisor_test(duration=10, is_raw_enabled_test=False):
    s = Supervisor(is_raw_enabled=is_raw_enabled_test)
    try:
        await s.start(duration_seconds=duration)
    except ValueError as e:
        logger.critical(f"Supervisor initialization failed: {e}")
    except KeyboardInterrupt:
        logger.info("Keyboard interrupt received. Stopping supervisor...")
        await s.stop()
    except Exception as e:
        logger.exception(f"Unhandled exception in supervisor main: {e}")
        await s.stop() # Attempt graceful shutdown
    finally:
        # Ensure cleanup happens even if start() wasn't awaited (e.g. init error)
        if not s.stop_event.is_set(): 
            await s.stop() # Call stop if it wasn't called yet)

if __name__ == "__main__":
    # This is a basic test run
    # In a real scenario, run.py would handle argparse and call this.
    asyncio.run(main_supervisor_test(duration=20, is_raw_enabled_test=True)) # Run for 20s for testing with raw enabled 