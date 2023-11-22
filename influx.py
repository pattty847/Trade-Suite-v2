import json
import os
from typing import Dict, List
from influxdb_client import InfluxDBClient, Point, WritePrecision
from influxdb_client.client.write_api import ASYNCHRONOUS
import pandas as pd
import logging

class InfluxDB:
    def __init__(self, is_local: bool = True) -> None:
        # Create a config.json file and store your INFLUX token as a key value pair
        self.client = self.get_influxdb_client(is_local)
        self.write_api = self.client.write_api(write_options=ASYNCHRONOUS)
        self.query_api = self.client.query_api()
        self.delete_api = self.client.delete_api()
        
    def get_influxdb_client(self, is_local):
        return InfluxDBClient(
            url="http://localhost:8086" if is_local else "https://us-east-1-1.aws.cloud2.influxdata.com",
            token=os.getenv('INFLUXDB_TOKEN_LOCAL') if is_local else os.getenv('INFLUXDB'),
            org="pepe"
        )
        
    async def write_trades(self, exchange, trades: List[Dict]):
        points = []
        
        for trade in trades:
            point = Point("trade") \
                    .tag("exchange", exchange) \
                    .tag("symbol", trade["symbol"]) \
                    .tag("side", trade["side"]) \
                    .field("price", trade["price"]) \
                    .field("amount", trade["amount"]) \
                    .field("cost", trade.get("cost", 0)) \
                    .time(trade["timestamp"], WritePrecision.MS)
                    
            # Optionally handle fees if present
            if "fee" in trade and "cost" in trade["fee"]:
                point.field("fee_cost", trade["fee"]["cost"])
            
            points.append(point)
            
        self.write_api.write(bucket="trades", org='pepe', record=points)

    async def write_order_book(self, order_book: Dict):
        symbol = order_book["symbol"]
        timestamp = order_book["timestamp"]
        
        for bid in order_book["bids"]:
            point = Point("order_book") \
                    .tag("symbol", symbol) \
                    .tag("type", "bid") \
                    .field("price", bid[0]) \
                    .field("amount", bid[1]) \
                    .time(timestamp, WritePrecision.MS)
            self.write_api.write(bucket="orderbook", org='pepe', record=point)

        for ask in order_book["asks"]:
            point = Point("order_book") \
                    .tag("symbol", symbol) \
                    .tag("type", "ask") \
                    .field("price", ask[0]) \
                    .field("amount", ask[1]) \
                    .time(timestamp, WritePrecision.MS)
            self.write_api.write(bucket="your_bucket_name", record=point)
            
    async def write_candlesticks(self, candlestick_data: Dict):
        batch_size = 10000  # example size, adjust as needed
        points = []

        for exchange, symbols in candlestick_data.items():
            for symbol_interval, dataframe in symbols.items():
                symbol, interval = symbol_interval.split('-')
                for timestamp, row in dataframe.iterrows():
                    point = Point("candlestick") \
                            .tag("exchange", exchange) \
                            .tag("symbol", symbol) \
                            .tag("interval", interval) \
                            .field("open", row['open']) \
                            .field("high", row['high']) \
                            .field("low", row['low']) \
                            .field("close", row['close']) \
                            .field("volume", row['volume']) \
                            .time(pd.Timestamp(timestamp).to_pydatetime(), WritePrecision.MS)

                    points.append(point)
                    if len(points) >= batch_size:
                        self.write_api.write(bucket="candles", org='pepe', record=points)
                        points = []  # Reset points after writing

            # Write any remaining points after processing each exchange
            if points:
                self.write_api.write(bucket="candles", org='pepe', record=points)
                points = []  # Reset for the next exchange

            # Log the completion of writing for an exchange
            logging.info(f"Completed writing candlesticks for {exchange}")