from datetime import datetime, timedelta
import os
import pandas as pd
import logging

from collections import deque
from typing import Dict, List

from influxdb_client import InfluxDBClient, Point, WritePrecision
from influxdb_client.client.write_api import ASYNCHRONOUS
from influxdb_client.client.query_api_async import QueryApiAsync


class InfluxDB:
    def __init__(self, is_local: bool = True) -> None:
        # Create a config.json file and store your INFLUX token as a key value pair
        self.client = self.get_influxdb_client(is_local)
        self.write_api = self.client.write_api(write_options=ASYNCHRONOUS)
        self.query_api = self.client.query_api()
        self.delete_api = self.client.delete_api()

        # Counter for trades
        self.tick_count = 0

        # List deque for a history of trades
        self.trade_history = deque(maxlen=1000)

    async def write_trades(self, exchange, trades: List[Dict]):
        points = []
        self.tick_count += 1
        for trade in trades:
            point = (
                Point("trade")
                .tag("exchange", exchange)
                .tag("symbol", trade["symbol"])
                .tag("side", trade["side"])
                .field("price", trade["price"])
                .field("amount", trade["amount"])
                .field("cost", trade.get("cost", 0))
                .time(trade["timestamp"], WritePrecision.MS)
            )

            # Optionally handle fees if present
            if "fee" in trade and "cost" in trade["fee"]:
                point.field("fee_cost", trade["fee"]["cost"])

            points.append(point)

        # Every 1000 ticks, logging.info to console the amount saved thus far
        if self.tick_count % 1000 == 0:
            logging.info(f"Wrote {self.tick_count} trades to the database total.")

        self.write_api.write(bucket="trades", org="pepe", record=points)

    async def write_stats(self, exchange, stats, symbol):
        point = Point("trade_stats").tag("exchange", exchange).tag("symbol", symbol)

        for category, metrics in stats.items():
            for metric, value in metrics.items():
                point = point.field(f"{category}_{metric}", value)

        self.write_api.write(bucket="trade_stats", org="pepe", record=point)

    async def write_ob_and_trades(self, exchange, trades, orderbook):
        points = []

        # Process trades and create data points
        # list[dict_keys(['id', 'order', 'info', 'timestamp', 'datetime', 'symbol', 'type', 'takerOrMaker', 'side', 'price', 'amount', 'fee', 'cost', 'fees'])]
        for trade in trades:
            self.trade_history.append(trade)
            trade_point = (
                Point("trade")
                .tag("trade_exchange", exchange)
                .tag("trade_symbol", trade["symbol"])
                .tag("trade_side", trade["side"])
                .field("trade_price", trade["price"])
                .field("trade_amount", trade["amount"])
                .field("trade_cost", trade.get("cost", 0))
                .time(trade["timestamp"], WritePrecision.MS)
            )

            # Optionally handle fees if present
            if "fee" in trade and "cost" in trade["fee"]:
                trade_point.field("fee_cost", trade["fee"]["cost"])
            points.append(trade_point)

        # Process order book and create data points
        # dict_keys(['bids', 'asks', 'timestamp', 'datetime', 'nonce', 'symbol'])
        best_bid = orderbook["bids"][0]  # [price, amount]
        best_bid_price = best_bid[0]
        best_bid_amount = best_bid[1]

        best_ask = orderbook["asks"][0]  # [price, amount]
        best_ask_price = best_ask[0]
        best_ask_amount = best_ask[1]

        # Calculate cumulative depth imbalance within a certain depth range (e.g., top 5 levels)
        bid_depth_range = sum(bid[1] for bid in orderbook["bids"][:10])
        ask_depth_range = sum(ask[1] for ask in orderbook["asks"][:10])
        cumulative_depth_imbalance = bid_depth_range - ask_depth_range

        # Calculate weighted imbalance
        weighted_bid = sum(bid[0] * bid[1] for bid in orderbook["bids"][:10])
        weighted_ask = sum(ask[0] * ask[1] for ask in orderbook["asks"][:10])
        weighted_imbalance = weighted_bid - weighted_ask

        # Calculate trade imbalance (assuming you have a trade history available)
        # This is a simplified example where `trade_history` is a list of recent trades
        # Each trade is a dict with 'side' ('buy' or 'sell') and 'amount'
        buy_volume = sum(
            trade["amount"] for trade in self.trade_history if trade["side"] == "buy"
        )
        sell_volume = sum(
            trade["amount"] for trade in self.trade_history if trade["side"] == "sell"
        )
        trade_imbalance = buy_volume - sell_volume

        order_book_point = (
            Point("order_book")
            .tag("exchange", exchange)
            .tag("symbol", orderbook["symbol"])
            .field("best_bid_price", best_bid_price)
            .field("best_bid_amount", best_bid_amount)
            .field("best_ask_price", best_ask_price)
            .field("best_ask_amount", best_ask_amount)
            .field("price_spread", best_ask_price - best_bid_price)
            .field("amount_spread", best_ask_amount - best_bid_amount)
            .field("cumulative_depth_imbalance", cumulative_depth_imbalance)
            .field("weighted_imbalance", weighted_imbalance)
            .field("trade_imbalance", trade_imbalance)
            .time(orderbook["timestamp"], WritePrecision.MS)
        )

        points.append(order_book_point)

        # Write points to InfluxDB asynchronously
        # logging.info(f'Writing {len(points)} points to DB for {symbol}.')
        self.write_api.write(bucket="market_data", org="pepe", record=points)

    async def write_candles(self, all_candles: Dict[str, Dict[str, pd.DataFrame]]):
        points = []
        for exchange, symbol_data in all_candles.items():
            for symbol_timeframe, df in symbol_data.items():
                symbol, timeframe = symbol_timeframe.split("-")
                for _, row in df.iterrows():
                    point = (
                        Point("candle")
                        .tag("exchange", exchange)
                        .tag("symbol", symbol)
                        .tag("timeframe", timeframe)
                        .field("opens", row["opens"])
                        .field("highs", row["highs"])
                        .field("lows", row["lows"])
                        .field("closes", row["closes"])
                        .field("volumes", row["volumes"])
                        .time(row.name, WritePrecision.MS)
                    )  # row.name is the timestamp index

                    points.append(point)

        logging.info(f"Writing {len(points)} candle points to DB.")
        self.write_api.write(bucket="candles", org="pepe", record=points)

    # TODO: Make this and the whole class truly async
    def query_candles(self, exchange: str, symbol: str, timeframe: str):
        """
        Queries InfluxDB for candle data for a given exchange, symbol, and timeframe.

        Args:
            exchange: The exchange to query for.
            symbol: The trading symbol to query for.
            timeframe: The timeframe to query for.

        Returns:
            A pandas DataFrame containing the candle data.
        """
        # Define the time range for the query. This example uses 5 years ago until now.
        start_time = datetime.utcnow() - timedelta(days=5 * 365)
        end_time = datetime.utcnow()

        # Construct the Flux query
        flux_query = f"""
        from(bucket: "candles")
        |> range(start: {start_time.isoformat()}Z, stop: {end_time.isoformat()}Z)
        |> filter(fn: (r) => 
            r._measurement == "candle" and 
            r.exchange == "{exchange}" and 
            r.symbol == "{symbol}" and 
            r.timeframe == "{timeframe}")
        |> pivot(rowKey:["_time"], columnKey: ["_field"], valueColumn: "_value")
        |> keep(columns: ["_time", "open", "high", "low", "close"])
        """

        # Execute the query and return the result as a pandas DataFrame
        result = self.query_api.query_data_frame(flux_query)
        return result

    async def write_candlesticks_batch(self, candlestick_data: Dict):
        batch_size = 10000  # example size, adjust as needed
        points = []

        for exchange, symbols in candlestick_data.items():
            for symbol_interval, dataframe in symbols.items():
                symbol, interval = symbol_interval.split("-")
                for timestamp, row in dataframe.iterrows():
                    point = (
                        Point("candlestick")
                        .tag("exchange", exchange)
                        .tag("symbol", symbol)
                        .tag("interval", interval)
                        .field("open", row["open"])
                        .field("high", row["high"])
                        .field("low", row["low"])
                        .field("close", row["close"])
                        .field("volume", row["volume"])
                        .time(
                            pd.Timestamp(timestamp).to_pydatetime(), WritePrecision.MS
                        )
                    )

                    points.append(point)
                    if len(points) >= batch_size:
                        self.write_api.write(
                            bucket="candles", org="pepe", record=points
                        )
                        points = []  # Reset points after writing

            # Write any remaining points after processing each exchange
            if points:
                self.write_api.write(bucket="candles", org="pepe", record=points)
                points = []  # Reset for the next exchange

            # Log the completion of writing for an exchange
            logging.info(f"Completed writing candlesticks for {exchange}")

    async def write_order_book(self, exchange, orderbook):
        points = []

        # Process order book and create data points
        # dict_keys(['bids', 'asks', 'timestamp', 'datetime', 'nonce', 'symbol'])
        best_bid = orderbook["bids"][0]  # [price, amount]
        best_bid_price = best_bid[0]
        best_bid_amount = best_bid[1]

        best_ask = orderbook["asks"][0]  # [price, amount]
        best_ask_price = best_ask[0]
        best_ask_amount = best_ask[1]

        # Calculate cumulative depth imbalance within a certain depth range (e.g., top 5 levels)
        bid_depth_range = sum(bid[1] for bid in orderbook["bids"][:10])
        ask_depth_range = sum(ask[1] for ask in orderbook["asks"][:10])
        cumulative_depth_imbalance = bid_depth_range - ask_depth_range

        # Calculate weighted imbalance
        weighted_bid = sum(bid[0] * bid[1] for bid in orderbook["bids"][:10])
        weighted_ask = sum(ask[0] * ask[1] for ask in orderbook["asks"][:10])
        weighted_imbalance = weighted_bid - weighted_ask

        order_book_point = (
            Point("order_book")
            .tag("exchange", exchange)
            .tag("symbol", orderbook["symbol"])
            .field("best_bid_price", best_bid_price)
            .field("best_bid_amount", best_bid_amount)
            .field("best_ask_price", best_ask_price)
            .field("best_ask_amount", best_ask_amount)
            .field("price_spread", best_ask_price - best_bid_price)
            .field("amount_spread", best_ask_amount - best_bid_amount)
            .field("bid_depth_range", bid_depth_range)
            .field("ask_depth_range", ask_depth_range)
            .field("cumulative_depth_imbalance", cumulative_depth_imbalance)
            .field("weighted_imbalance", weighted_imbalance)
            .time(orderbook["timestamp"], WritePrecision.MS)
        )

        points.append(order_book_point)
        self.write_api.write(bucket="orderbook", org="pepe", record=points)

    def get_influxdb_client(self, is_local):
        return InfluxDBClient(
            url=(
                "http://localhost:8086"
                if is_local
                else "https://us-east-1-1.aws.cloud2.influxdata.com"
            ),
            token=(
                os.getenv("INFLUXDB_TOKEN_LOCAL") if is_local else os.getenv("INFLUXDB")
            ),
            org="pepe",
        )