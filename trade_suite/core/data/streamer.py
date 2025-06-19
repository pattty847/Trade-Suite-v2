import asyncio
import logging
from typing import Any, Awaitable, Callable, Dict, List, Optional
import ccxt

from .influx import InfluxDB
from trade_suite.analysis.market_aggregator import MarketAggregator
from ..signals import SignalEmitter, Signals


class Streamer:
    """Live streaming helper for trades, order books and tickers."""

    def __init__(self, emitter: SignalEmitter, aggregator: MarketAggregator, influx: InfluxDB) -> None:
        self.emitter = emitter
        self.agg = aggregator
        self.influx = influx
        self.exchange_list: Dict[str, ccxt.Exchange] = {}
        self._ui_loop: asyncio.AbstractEventLoop | None = None

    def set_exchange_list(self, exchange_list: Dict[str, ccxt.Exchange]) -> None:
        self.exchange_list = exchange_list

    def set_ui_loop(self, loop: asyncio.AbstractEventLoop) -> None:
        self._ui_loop = loop

    async def watch_trades_list(
        self,
        symbols: List[str],
        stop_event: asyncio.Event,
        track_stats: bool = False,
        write_trades: bool = False,
        write_stats: bool = False,
    ) -> None:
        for exchange_id in self.exchange_list.keys():
            exchange_object = self.exchange_list[exchange_id]
            logging.info(f"Starting trade stream for {symbols} on {exchange_id}")
            while not stop_event.is_set():
                try:
                    trades = await exchange_object.watchTradesForSymbols(symbols)
                    if trades:
                        if self._ui_loop:
                            self.emitter.emit_threadsafe(
                                self._ui_loop,
                                Signals.NEW_TRADE,
                                exchange=exchange_id,
                                trade_data=trades[0],
                            )
                        else:
                            self.emitter.emit(
                                Signals.NEW_TRADE,
                                exchange=exchange_id,
                                trade_data=trades[0],
                            )
                    if track_stats:
                        symbol, stats = self.agg.calc_trade_stats(exchange_id, trades)
                        if self._ui_loop:
                            self.emitter.emit_threadsafe(
                                self._ui_loop,
                                Signals.TRADE_STAT_UPDATE,
                                symbol=symbol,
                                stats=stats,
                            )
                        else:
                            self.emitter.emit(
                                Signals.TRADE_STAT_UPDATE,
                                symbol=symbol,
                                stats=stats,
                            )
                    if write_stats and write_trades:
                        await self.influx.write_trades(exchange_id, trades)
                        await self.influx.write_stats(exchange_id, stats, symbol)
                except asyncio.CancelledError:
                    logging.info(f"Trade list stream for {symbols} on {exchange_id} cancelled.")
                    break
                except Exception as e:
                    logging.error(e)
            logging.info(f"Trade list stream for {symbols} on {exchange_id} stopped.")

    async def watch_trades(
        self,
        symbol: str,
        exchange: str,
        stop_event: asyncio.Event,
        track_stats: bool = False,
        write_trades: bool = False,
        write_stats: bool = False,
        sink: Optional[Callable[[Dict[str, Any]], Awaitable[None]]] = None,
        queue: asyncio.Queue | None = None,
    ) -> None:
        if sink and queue:
            raise ValueError("Provide either a sink or a queue, not both.")

        exchange_object = self.exchange_list[exchange]
        logging.info(f"Starting trade stream for {symbol} on {exchange}")
        stop_event.clear()

        while not stop_event.is_set():
            try:
                trades_list = await exchange_object.watch_trades(symbol)
                if trades_list:
                    for trade_data in trades_list:
                        trade_event_dict = {"exchange": exchange, "trade_data": trade_data}

                        if sink:
                            await sink(trade_event_dict)
                        elif queue:
                            await queue.put(trade_event_dict)
                        elif self.emitter:
                            if self._ui_loop:
                                self.emitter.emit_threadsafe(
                                    self._ui_loop,
                                    Signals.NEW_TRADE,
                                    exchange=exchange,
                                    trade_data=trade_data,
                                )
                            else:
                                self.emitter.emit(
                                    Signals.NEW_TRADE,
                                    exchange=exchange,
                                    trade_data=trade_data,
                                )

                        if write_trades and self.influx and not (sink or queue):
                            await self.influx.write_trades(exchange, [trade_data])

                        if track_stats and self.emitter:
                            symbol_key, stats = self.agg.calc_trade_stats(exchange, [trade_data])
                            if self._ui_loop:
                                self.emitter.emit_threadsafe(
                                    self._ui_loop,
                                    Signals.TRADE_STAT_UPDATE,
                                    symbol=symbol_key,
                                    stats=stats,
                                )
                            else:
                                self.emitter.emit(
                                    Signals.TRADE_STAT_UPDATE,
                                    symbol=symbol_key,
                                    stats=stats,
                                )
                            if write_stats and self.influx and not (sink or queue):
                                await self.influx.write_stats(exchange, stats, symbol_key)
            except asyncio.CancelledError:
                logging.info(f"Trade stream for {symbol} on {exchange} cancelled.")
                break
            except ccxt.NetworkError as e:
                logging.warning(
                    f"NetworkError in watch_trades for {symbol} on {exchange}: {e}. Retrying after delay..."
                )
                await asyncio.sleep(
                    exchange_object.rateLimit / 1000 if exchange_object.rateLimit > 0 else 5
                )
            except ccxt.ExchangeError as e:
                logging.error(
                    f"ExchangeError in watch_trades for {symbol} on {exchange}: {e}. Might stop or retry depending on error."
                )
                await asyncio.sleep(5)
            except Exception as e:
                logging.error(
                    f"Unexpected error in watch_trades for {symbol} on {exchange}: {e}",
                    exc_info=True,
                )
                await asyncio.sleep(5)
        logging.info(f"Trade stream for {symbol} on {exchange} stopped.")

    async def watch_orderbooks(self, symbols: List[str], stop_event: asyncio.Event) -> None:
        for exchange_id in self.exchange_list.keys():
            exchange_object = self.exchange_list[exchange_id]
            logging.info(f"Starting orderbook stream for {symbols} on {exchange_id}")
            if exchange_object.has["watchOrderBookForSymbols"]:
                while not stop_event.is_set():
                    try:
                        orderbook = await exchange_object.watchOrderBookForSymbols(symbols)
                        if self._ui_loop:
                            self.emitter.emit_threadsafe(
                                self._ui_loop,
                                Signals.ORDER_BOOK_UPDATE,
                                exchange=exchange_id,
                                orderbook=orderbook,
                            )
                        else:
                            self.emitter.emit(
                                Signals.ORDER_BOOK_UPDATE,
                                exchange=exchange_id,
                                orderbook=orderbook,
                            )
                        await asyncio.sleep(0.3)
                    except asyncio.CancelledError:
                        logging.info(f"Orderbook list stream for {symbols} on {exchange_id} cancelled.")
                        break
                    except Exception as e:
                        logging.error(e)
                if not stop_event.is_set():
                    logging.info(f"Orderbook list stream stopping for {exchange_id} due to event clear.")
                    break
            logging.info(f"Orderbook list stream for {symbols} on {exchange_id} stopped.")

    async def watch_orderbook(
        self,
        exchange: str,
        symbol: str,
        stop_event: asyncio.Event,
        sink: Optional[Callable[[Dict[str, Any]], Awaitable[None]]] = None,
        queue: asyncio.Queue | None = None,
        cadence_ms: int = 500,
    ) -> None:
        if sink and queue:
            raise ValueError("Provide either a sink or a queue, not both.")

        exchange_object = self.exchange_list[exchange]
        logging.info(f"Starting orderbook stream for {symbol} on {exchange} with {cadence_ms}ms cadence.")
        stop_event.clear()

        last_emit_time = 0
        throttle_interval_seconds = cadence_ms / 1000.0
        latest_orderbook_raw = None

        while not stop_event.is_set():
            try:
                current_orderbook_data = await exchange_object.watch_order_book(symbol)
                if current_orderbook_data:
                    latest_orderbook_raw = current_orderbook_data
                current_time = asyncio.get_running_loop().time()
                if latest_orderbook_raw and (current_time - last_emit_time >= throttle_interval_seconds):
                    orderbook_event_dict = {"exchange": exchange, "orderbook": latest_orderbook_raw}

                    if sink:
                        await sink(orderbook_event_dict)
                    elif queue:
                        await queue.put(orderbook_event_dict)
                    elif self.emitter:
                        if self._ui_loop:
                            self.emitter.emit_threadsafe(
                                self._ui_loop,
                                Signals.ORDER_BOOK_UPDATE,
                                exchange=exchange,
                                orderbook=latest_orderbook_raw,
                            )
                        else:
                            self.emitter.emit(
                                Signals.ORDER_BOOK_UPDATE,
                                exchange=exchange,
                                orderbook=latest_orderbook_raw,
                            )
                    else:
                        logging.debug(
                            f"No sink, queue, or emitter configured for order book data for {symbol} on {exchange}."
                        )
                    last_emit_time = current_time
                    latest_orderbook_raw = None
            except asyncio.CancelledError:
                logging.info(f"Orderbook stream for {symbol} on {exchange} cancelled.")
                break
            except ccxt.NetworkError as e:
                logging.warning(
                    f"NetworkError in watch_orderbook for {symbol} on {exchange}: {e}. Retrying after delay..."
                )
                await asyncio.sleep(
                    exchange_object.rateLimit / 1000 if exchange_object.rateLimit > 0 else 5
                )
            except ccxt.ExchangeError as e:
                logging.error(
                    f"ExchangeError in watch_orderbook for {symbol} on {exchange}: {e}. Might stop or retry."
                )
                await asyncio.sleep(5)
            except Exception as e:
                logging.error(
                    f"Error in orderbook stream for {symbol} on {exchange}: {e}", exc_info=True
                )
                await asyncio.sleep(1)
        logging.info(f"Orderbook stream for {symbol} on {exchange} stopped.")

    async def watch_ticker(self, exchange_id: str, symbol: str, stop_event: asyncio.Event) -> None:
        if exchange_id not in self.exchange_list:
            logging.error(f"Exchange {exchange_id} not initialized in Streamer class.")
            return

        exchange = self.exchange_list[exchange_id]
        logging.info(f"Starting ticker watch for {symbol} on {exchange_id}")
        stop_event.clear()

        while not stop_event.is_set():
            try:
                ticker_data = await exchange.watch_ticker(symbol)
                if ticker_data:
                    if self._ui_loop:
                        self.emitter.emit_threadsafe(
                            self._ui_loop,
                            Signals.NEW_TICKER_DATA,
                            exchange=exchange_id,
                            symbol=symbol,
                            ticker_data_dict=ticker_data,
                        )
                    elif self.emitter:
                        self.emitter.emit(
                            Signals.NEW_TICKER_DATA,
                            exchange=exchange_id,
                            symbol=symbol,
                            ticker_data_dict=ticker_data,
                        )
                    else:
                        logging.debug(f"No emitter configured for ticker data for {symbol} on {exchange_id}.")
            except asyncio.CancelledError:
                logging.info(f"Ticker watch for {symbol} on {exchange_id} cancelled.")
                break
            except ccxt.NetworkError as e:
                await asyncio.sleep(
                    exchange.rateLimit / 1000 if hasattr(exchange, "rateLimit") and exchange.rateLimit > 0 else 5
                )
            except ccxt.ExchangeError as e:
                logging.error(f"ExchangeError in watch_ticker for {symbol} on {exchange_id}: {e}.")
                await asyncio.sleep(5)
            except Exception as e:
                logging.error(
                    f"Unexpected error in watch_ticker for {symbol} on {exchange_id}: {e}",
                    exc_info=True,
                )
                await asyncio.sleep(5)
        logging.info(f"Ticker watch for {symbol} on {exchange_id} stopped.")

