# sentinel/writers/influx_writer.py
import asyncio
import logging
import os
from typing import List, Union, Any # Union for queue item type, Any for InfluxDB client

from influxdb_client import InfluxDBClient, Point, WritePrecision
from influxdb_client.client.exceptions import InfluxDBError
from influxdb_client.client.write_api import ASYNCHRONOUS, WriteOptions

from sentinel import config

class InfluxWriter:
    def __init__(self, influx_url: str, influx_token: str, influx_org: str):
        """
        Initializes the InfluxWriter with connection details for InfluxDB.

        Args:
            influx_url: URL of the InfluxDB instance.
            influx_token: Authentication token for InfluxDB.
            influx_org: Organization name in InfluxDB.
        """
        self.influx_url = influx_url
        self.influx_token = influx_token
        self.influx_org = influx_org
        self.client: InfluxDBClient | None = None
        self.write_api = None
        self._connect()

    def _connect(self):
        """Establishes connection to InfluxDB and initializes the write_api."""
        try:
            self.client = InfluxDBClient(
                url=self.influx_url,
                token=self.influx_token,
                org=self.influx_org
            )
            # Configure WriteOptions for batching
            # Using batch_size from config, flush_interval from config
            # jitter_interval and retry_interval can be added for more robust retries by the client library
            write_options = WriteOptions(
                batch_size=config.WRITER_BATCH_SIZE_POINTS,
                flush_interval=config.WRITER_FLUSH_INTERVAL_MS,
                write_type=ASYNCHRONOUS
            )
            self.write_api = self.client.write_api(write_options=write_options)
            logging.info("InfluxDB client initialized and write_api configured.")
            # Verify connection (optional, but good for early feedback)
            if not self.client.ping():
                 logging.warning("InfluxDB ping failed. Check connection and credentials.")
        except Exception as e:
            logging.error(f"Failed to connect to InfluxDB or initialize write_api: {e}")
            self.client = None # Ensure client is None if connection fails
            self.write_api = None

    async def write_batch(self, bucket: str, data_points: List[str]):
        """
        Writes a batch of Line Protocol data points to the specified InfluxDB bucket.
        Includes basic retry logic.

        Args:
            bucket: The InfluxDB bucket to write to.
            data_points: A list of strings, where each string is in Line Protocol format.
        """
        if not self.write_api:
            logging.error("InfluxDB write_api not initialized. Cannot write data.")
            return
        if not data_points:
            return

        max_retries = 3
        retry_delay = 2  # seconds

        for attempt in range(max_retries):
            try:
                # The ASYNCHRONOUS write_api handles batching and flushing based on WriteOptions.
                # We are just passing the prepared line protocol strings.
                self.write_api.write(bucket=bucket, org=self.influx_org, record=data_points)
                # logging.debug(f"Successfully wrote {len(data_points)} points to bucket '{bucket}'.")
                return # Success
            except InfluxDBError as e:
                logging.error(f"InfluxDBError writing to bucket '{bucket}' (attempt {attempt + 1}/{max_retries}): {e}")
                if e.response and e.response.status == 401:
                    logging.error("InfluxDB authentication error (401). Check token.")
                    break # No point retrying auth error
                if e.response and e.response.status == 404:
                    logging.error(f"InfluxDB bucket '{bucket}' not found (404).")
                    break # No point retrying if bucket doesn't exist
                # For other errors, retry after a delay
                if attempt < max_retries - 1:
                    await asyncio.sleep(retry_delay * (2 ** attempt)) # Exponential backoff
                else:
                    logging.error(f"Failed to write to bucket '{bucket}' after {max_retries} attempts.")
            except Exception as e:
                logging.error(f"Unexpected error writing to bucket '{bucket}' (attempt {attempt + 1}/{max_retries}): {e}")
                if attempt < max_retries - 1:
                    await asyncio.sleep(retry_delay * (2 ** attempt))
                else:
                    logging.error(f"Failed to write to bucket '{bucket}' after {max_retries} attempts due to unexpected error.")

    async def run_queue_consumer(self, data_queue: asyncio.Queue, bucket_name: str, stop_event: asyncio.Event):
        """
        Continuously consumes data from an asyncio.Queue and writes it to InfluxDB.
        Manages batching based on size or time.

        Args:
            data_queue: The asyncio.Queue to read data from.
                       Expected items: single LP string for trades, list of LP strings for order books.
            bucket_name: The InfluxDB bucket to write the data to.
            stop_event: An asyncio.Event to signal when to stop the consumer.
        """
        if not self.write_api:
            logging.error(f"InfluxWriter not connected. Cannot start consumer for bucket '{bucket_name}'.")
            return

        logging.info(f"Starting InfluxDB writer for bucket: {bucket_name}")
        local_batch = []
        last_flush_time = asyncio.get_event_loop().time()

        try:
            while not stop_event.is_set():
                try:
                    # Wait for an item from the queue with a timeout
                    # This allows the loop to check stop_event and flush interval periodically
                    item = await asyncio.wait_for(data_queue.get(), timeout=0.05) # 50ms timeout
                    
                    if isinstance(item, str): # Single trade LP
                        local_batch.append(item)
                    elif isinstance(item, list): # List of order book LPs
                        local_batch.extend(item)
                    else:
                        logging.warning(f"Received unexpected data type in queue for bucket {bucket_name}: {type(item)}")
                        data_queue.task_done()
                        continue

                    data_queue.task_done()

                except asyncio.TimeoutError:
                    # No item received, proceed to check flush conditions
                    pass 
                except asyncio.CancelledError:
                    logging.info(f"Writer for bucket '{bucket_name}' received cancellation.")
                    break # Exit if the task is cancelled
                except Exception as e:
                    logging.error(f"Error getting item from queue for bucket {bucket_name}: {e}")
                    # Potentially add a small sleep to prevent tight loop on persistent queue errors
                    await asyncio.sleep(0.1)
                    continue

                current_time = asyncio.get_event_loop().time()
                time_since_last_flush_ms = (current_time - last_flush_time) * 1000

                # Flush conditions
                if local_batch and \
                   (len(local_batch) >= config.WRITER_BATCH_SIZE_POINTS or \
                    time_since_last_flush_ms >= config.WRITER_FLUSH_INTERVAL_MS):
                    
                    logging.debug(f"Flushing batch to '{bucket_name}'. Size: {len(local_batch)}, Interval: {time_since_last_flush_ms:.0f}ms")
                    await self.write_batch(bucket_name, list(local_batch)) # Pass a copy
                    local_batch.clear()
                    last_flush_time = current_time
            
            # Final flush for any remaining items after stop_event is set
            if local_batch:
                logging.info(f"Flushing remaining {len(local_batch)} items from '{bucket_name}' before shutdown.")
                await self.write_batch(bucket_name, list(local_batch))
                local_batch.clear()

        except asyncio.CancelledError:
            logging.info(f"Writer for bucket '{bucket_name}' task cancelled externally.")
            # Final flush for any remaining items
            if local_batch:
                logging.info(f"Flushing remaining {len(local_batch)} items from '{bucket_name}' due to cancellation.")
                await self.write_batch(bucket_name, list(local_batch))
                local_batch.clear()
        finally:
            logging.info(f"InfluxDB writer for bucket '{bucket_name}' stopped.")

    def close(self):
        """Closes the InfluxDB client and write_api."""
        if self.write_api:
            try:
                self.write_api.close() # Flushes any pending writes and closes
                logging.info("InfluxDB write_api closed.")
            except Exception as e:
                logging.error(f"Error closing InfluxDB write_api: {e}")
            self.write_api = None
        if self.client:
            try:
                self.client.close()
                logging.info("InfluxDB client closed.")
            except Exception as e:
                logging.error(f"Error closing InfluxDB client: {e}")
            self.client = None

# Example usage (for testing, typically part of supervisor.py)
async def main_writer_test():
    # Ensure INFLUXDB_TOKEN_LOCAL is set in your environment for this test
    influx_token = os.getenv("INFLUXDB_TOKEN_LOCAL")
    if not influx_token:
        print("INFLUXDB_TOKEN_LOCAL environment variable not set. Skipping writer test.")
        return

    writer = InfluxWriter(
        influx_url=config.INFLUX_URL_LOCAL,
        influx_token=influx_token,
        influx_org=config.INFLUX_ORG
    )

    if not writer.write_api:
        print("InfluxWriter failed to initialize. Exiting test.")
        return

    test_trade_queue = asyncio.Queue()
    stop_event = asyncio.Event()

    # Start the consumer task
    writer_task = asyncio.create_task(
        writer.run_queue_consumer(test_trade_queue, config.INFLUX_BUCKET_TR, stop_event)
    )

    # Simulate putting some data
    await test_trade_queue.put("trades,exchange=test,symbol=BTC-USD,side=buy price=1.0,size=1.0 1678886400000000000")
    await test_trade_queue.put("trades,exchange=test,symbol=BTC-USD,side=sell price=2.0,size=0.5 1678886400000001000")
    
    # Test with list for order book data (if bucket is configured)
    # await test_trade_queue.put(["test_ob,level=1 price=1,amount=1 1678886400000000000", "test_ob,level=2 price=2,amount=2 1678886400000000000"])

    await asyncio.sleep(2) # Let it process

    stop_event.set() # Signal the writer to stop
    await writer_task # Wait for the writer to finish
    writer.close()
    print("Writer test completed.")

if __name__ == "__main__":
    logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(levelname)s - %(message)s')
    # To run this test: python -m sentinel.writers.influx_writer
    # Ensure InfluxDB is running locally and INFLUXDB_TOKEN_LOCAL is set.
    asyncio.run(main_writer_test()) 