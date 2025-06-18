# sentinel/collectors/coinbase.py
import asyncio
import logging
from typing import Callable # For type hinting the sink

from trade_suite.data.data_source import Data # Assuming Data class is accessible
from sentinel import schema # For LP building
from sentinel import config # For constants like CADENCE_MS

async def stream_data_to_queues(
    data_source: Data,
    symbol: str,
    stop_event: asyncio.Event,
    trade_queue: asyncio.Queue,
    order_book_queue: asyncio.Queue,
    is_raw_enabled: bool, # New: To control raw book processing
    raw_order_book_queue: asyncio.Queue | None = None, # New: Queue for raw order book LP
    exchange_name: str = config.TARGET_EXCHANGE,
    order_book_cadence_ms: int = config.CADENCE_MS,
    max_queue_retries: int = 3, # Max retries for putting on queue if full
    queue_retry_delay: float = 0.01 # Delay between retries in seconds
):
    """
    Uses the Data class to watch trades and order books, 
    formats them into Line Protocol, and puts them onto asyncio Queues.
    Includes queue overflow checks and optional raw order book processing.

    Args:
        data_source: An initialized instance of the Data class.
        symbol: The trading symbol (e.g., 'BTC/USD').
        stop_event: asyncio.Event to signal when to stop streaming.
        trade_queue: asyncio.Queue to send trade Line Protocol strings to.
        order_book_queue: asyncio.Queue to send binned order book Line Protocol strings to.
        is_raw_enabled: Boolean indicating if raw order book data should be processed.
        raw_order_book_queue: Optional asyncio.Queue for raw order book LP strings.
        exchange_name: The name of the exchange to stream from.
        order_book_cadence_ms: The cadence for order book updates in milliseconds.
        max_queue_retries: How many times to retry putting on a full queue.
        queue_retry_delay: Delay between queue put retries.
    """
    logger = logging.getLogger(__name__) # Get a logger specific to this module/function
    dropped_trades_count = 0
    dropped_binned_books_count = 0
    dropped_raw_books_count = 0
    last_order_book_nonce = None # State for gap audit

    if is_raw_enabled and raw_order_book_queue is None:
        logger.warning(f"[{exchange_name.upper()}] Raw order book is enabled, but no raw_order_book_queue provided. Raw data will not be processed.")
        is_raw_enabled = False # Disable if queue is missing

    logger.info(f"[{exchange_name.upper()}] Starting data collection for {symbol}. Raw enabled: {is_raw_enabled}")

    async def _safe_put_to_queue(q: asyncio.Queue, item: any, item_type: str) -> bool:
        nonlocal dropped_trades_count, dropped_binned_books_count, dropped_raw_books_count
        for attempt in range(max_queue_retries):
            if q.full():
                logger.warning(f"Queue for {item_type} is full (size: {q.qsize()}). Attempt {attempt + 1}/{max_queue_retries}. Retrying after {queue_retry_delay}s...")
                if attempt == max_queue_retries - 1: # Last attempt failed
                    logger.critical(f"CRITICAL: Queue for {item_type} remained full after {max_queue_retries} attempts. Dropping data for {symbol} on {exchange_name}.")
                    if item_type == 'trade': dropped_trades_count += 1
                    elif item_type == 'binned_book': dropped_binned_books_count += 1
                    elif item_type == 'raw_book': dropped_raw_books_count += 1
                    # TODO: Expose these counts to healthz or metrics
                    return False # Failed to put
                await asyncio.sleep(queue_retry_delay)
            else:
                await q.put(item)
                return True # Successfully put
        return False # Should be unreachable if loop logic is correct

    async def trade_sink(trade_event_dict):
        try:
            exchange = trade_event_dict['exchange']
            trade = trade_event_dict['trade_data']
            
            # Extract sequence if available (though typically not in simple trade data from watch_trades)
            # sequence = trade.get('info', {}).get('sequence') # Example path, adjust as needed
            
            timestamp_ns = int(trade['timestamp']) * 1_000_000
            lp = schema.build_trade_lp(
                exchange=exchange,
                symbol=trade['symbol'],
                side=trade['side'],
                size=trade['amount'],
                price=trade['price'],
                trade_id=str(trade['id']),
                timestamp_ns=timestamp_ns
            )
            logger.debug(f"[{exchange_name.upper()}] Trade LP generated: {lp}")
            await _safe_put_to_queue(trade_queue, lp, 'trade')
        except Exception as e:
            logger.error(f"[{exchange_name.upper()}] Error processing trade data for sink: {e} - Data: {trade_event_dict}", exc_info=True)

    async def order_book_sink(order_book_event_dict):
        nonlocal last_order_book_nonce
        try:
            exchange = order_book_event_dict['exchange']
            book = order_book_event_dict['orderbook']
            timestamp_ms = book['timestamp']
            timestamp_ns = int(timestamp_ms) * 1_000_000
            
            # Attempt to get sequence number (highly exchange-specific for full books from watchOrderBook)
            # For Coinbase, `nonce` is often the sequence for snapshots, or info.sequence for L2 updates.
            # This needs verification for what `watch_order_book` provides from `trade_suite.data_source`
            sequence = book.get('nonce') # Common for CCXT snapshots
            if sequence is None and 'info' in book and isinstance(book['info'], dict):
                sequence = book['info'].get('sequence') # Try info.sequence (e.g. Coinbase Pro REST snapshot)
            
            # --- GAP AUDIT LOGIC ---
            if sequence is not None:
                if last_order_book_nonce is not None:
                    if sequence <= last_order_book_nonce:
                        logger.critical(
                            f"[{exchange_name.upper()}-{book['symbol']}] Stale or out-of-order book received! "
                            f"Last Nonce: {last_order_book_nonce}, Current Nonce: {sequence}. Resync may be needed."
                        )
                        # In a more advanced system, we might trigger a full resync here.
                        # For now, we log critically and continue, assuming CCXT will handle it.
                    elif sequence > last_order_book_nonce + 1:
                        missed_count = sequence - last_order_book_nonce - 1
                        logger.warning(
                            f"[{exchange_name.upper()}-{book['symbol']}] GAP DETECTED in order book stream. "
                            f"Missed {missed_count} update(s). "
                            f"Last Nonce: {last_order_book_nonce}, Current Nonce: {sequence}."
                        )
                last_order_book_nonce = sequence
            else:
                logger.debug(f"[{exchange_name.upper()}-{book['symbol']}] No nonce found in order book data. Cannot perform gap audit.")
            
            # Binned order book processing
            binned_lp_lines = schema.build_book_lp(
                exchange=exchange,
                symbol=book['symbol'],
                bids=book['bids'],
                asks=book['asks'],
                timestamp_ns=timestamp_ns,
                sequence=sequence
            )
            if binned_lp_lines:
                await _safe_put_to_queue(order_book_queue, binned_lp_lines, 'binned_book')

            # Raw order book processing (if enabled)
            if is_raw_enabled and raw_order_book_queue:
                raw_lp_lines = schema.build_raw_book_lp(
                    exchange=exchange,
                    symbol=book['symbol'],
                    bids=book['bids'],
                    asks=book['asks'],
                    timestamp_ns=timestamp_ns,
                    top_n=config.RAW_BOOK_TOP_N,
                    sequence=sequence
                )
                if raw_lp_lines:
                    logger.debug(f"[{exchange_name.upper()}] Raw LP lines generated for {book['symbol']}: {raw_lp_lines}")
                    await _safe_put_to_queue(raw_order_book_queue, raw_lp_lines, 'raw_book')
                    
        except Exception as e:
            logger.error(f"[{exchange_name.upper()}] Error processing order book data for sink: {e} - Data: {order_book_event_dict}", exc_info=True)

    # Create tasks for watching trades and order books
    # NOTE: data_source.watch_trades and data_source.watch_orderbook need to be updated
    # to accept `sink` and `cadence_ms` parameters respectively.
    trade_watcher_task = asyncio.create_task(
        data_source.watch_trades(
            symbol=symbol,
            exchange=exchange_name, 
            stop_event=stop_event,
            track_stats=False, # Sentinel does not need stats from data_source
            write_trades=False, # Sentinel handles its own writing
            write_stats=False, # Sentinel handles its own writing
            sink=trade_sink
        )
    )
    # Pass the specific cadence for order books to watch_orderbook
    order_book_watcher_task = asyncio.create_task(
        data_source.watch_orderbook(
            exchange=exchange_name,
            symbol=symbol,
            stop_event=stop_event,
            sink=order_book_sink,
            cadence_ms=order_book_cadence_ms
        )
    )

    logger.info(f"[{exchange_name.upper()}] Trade and order book watchers for {symbol} started.")

    try:
        # Wait for tasks to complete or stop_event to be set
        # This can be managed by the supervisor which calls this function
        await asyncio.gather(trade_watcher_task, order_book_watcher_task)
    except asyncio.CancelledError:
        logger.info(f"[{exchange_name.upper()}] Data collection for {symbol} cancelled.")
    finally:
        if not trade_watcher_task.done():
            trade_watcher_task.cancel()
        if not order_book_watcher_task.done():
            order_book_watcher_task.cancel()
        logger.info(f"[{exchange_name.upper()}] Data collection for {symbol} stopped.")

# Placeholder for Binance or other exchange collectors
# async def stream_btc_binance(queue: asyncio.Queue):
#     pass 