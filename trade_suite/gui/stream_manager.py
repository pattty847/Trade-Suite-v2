from __future__ import annotations

import asyncio
import logging
from collections import defaultdict
from typing import Dict, Set

from trade_suite.gui.signals import Signals
from trade_suite.data.data_source import Data


class StreamManager:
    """Manage hot-reloadable market data streams per exchange."""

    def __init__(self, data: Data) -> None:
        self.data = data
        self.trade_symbols: Dict[str, Set[str]] = defaultdict(set)
        self.orderbook_symbols: Dict[str, Set[str]] = defaultdict(set)
        self.ref_counts: Dict[tuple[str, str, str], int] = defaultdict(int)
        self._stop = asyncio.Event()
        self._lock = asyncio.Lock()
        self._tasks: list[asyncio.Task] = []

    async def run(self) -> None:
        """Run persistent watch loops for all exchanges."""
        for exchange in self.data.exchange_list.keys():
            self._tasks.append(asyncio.create_task(self._watch_trades_loop(exchange)))
            self._tasks.append(asyncio.create_task(self._watch_order_books_loop(exchange)))
        await self._stop.wait()
        for task in self._tasks:
            task.cancel()
        await asyncio.gather(*self._tasks, return_exceptions=True)

    async def stop(self) -> None:
        self._stop.set()

    async def subscribe_to_asset(self, exchange: str, symbol: str, stream_type: str) -> None:
        """Increment ref count and add symbol to active list."""
        key = (stream_type, exchange, symbol)
        async with self._lock:
            self.ref_counts[key] += 1
            if stream_type == "trades":
                self.trade_symbols[exchange].add(symbol)
            elif stream_type == "orderbook":
                self.orderbook_symbols[exchange].add(symbol)

    async def unsubscribe_from_asset(self, exchange: str, symbol: str, stream_type: str) -> None:
        """Decrement ref count and remove symbol if unused."""
        key = (stream_type, exchange, symbol)
        async with self._lock:
            if self.ref_counts[key] > 0:
                self.ref_counts[key] -= 1
                if self.ref_counts[key] == 0:
                    del self.ref_counts[key]
                    if stream_type == "trades":
                        self.trade_symbols[exchange].discard(symbol)
                    elif stream_type == "orderbook":
                        self.orderbook_symbols[exchange].discard(symbol)

    async def _watch_trades_loop(self, exchange_id: str) -> None:
        exchange = self.data.exchange_list[exchange_id]
        logging.info(f"StreamManager trade loop for {exchange_id} started")
        while not self._stop.is_set():
            symbols = list(self.trade_symbols[exchange_id])
            if not symbols:
                await asyncio.sleep(0.5)
                continue
            try:
                trades = await exchange.watchTradesForSymbols(symbols)
                if trades:
                    trade = trades[0]
                    if self.data.streamer._ui_loop:
                        self.data.emitter.emit_threadsafe(
                            self.data.streamer._ui_loop,
                            Signals.NEW_TRADE,
                            exchange=exchange_id,
                            trade_data=trade,
                        )
                    else:
                        self.data.emitter.emit(
                            Signals.NEW_TRADE,
                            exchange=exchange_id,
                            trade_data=trade,
                        )
            except asyncio.CancelledError:
                break
            except Exception as e:
                logging.error(f"Error in trade loop for {exchange_id}: {e}", exc_info=True)
        logging.info(f"Trade loop for {exchange_id} stopped")

    async def _watch_order_books_loop(self, exchange_id: str) -> None:
        exchange = self.data.exchange_list[exchange_id]
        logging.info(f"StreamManager order book loop for {exchange_id} started")
        while not self._stop.is_set():
            symbols = list(self.orderbook_symbols[exchange_id])
            if not symbols:
                await asyncio.sleep(0.5)
                continue
            try:
                if exchange.has.get("watchOrderBookForSymbols"):
                    orderbook = await exchange.watchOrderBookForSymbols(symbols)
                    if orderbook:
                        if self.data.streamer._ui_loop:
                            self.data.emitter.emit_threadsafe(
                                self.data.streamer._ui_loop,
                                Signals.ORDER_BOOK_UPDATE,
                                exchange=exchange_id,
                                orderbook=orderbook,
                            )
                        else:
                            self.data.emitter.emit(
                                Signals.ORDER_BOOK_UPDATE,
                                exchange=exchange_id,
                                orderbook=orderbook,
                            )
            except asyncio.CancelledError:
                break
            except Exception as e:
                logging.error(f"Error in order book loop for {exchange_id}: {e}", exc_info=True)
        logging.info(f"Order book loop for {exchange_id} stopped")
