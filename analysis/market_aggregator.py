import asyncio
from collections import defaultdict
from datetime import datetime
from typing import Dict, List
from influxdb_client import Point, WritePrecision
from influxdb_client.client.write_api import SYNCHRONOUS
import pandas as pd
from tabulate import tabulate
from collections import defaultdict
from typing import List

class MarketAggregator:
    
    def __init__(self):
        self.trade_stats = defaultdict(lambda: defaultdict(lambda: defaultdict(float)))
        self.order_size_categories = ['0-10k', '10k-100k', '100k-1m', '1m-10m', '10m-100m']


    def calc_trade_stats(self, exchange: str, trades: List[str]) -> None:
        try:
            for trade in trades:
                symbol = trade['symbol']
                # Check if necessary fields are in the trade data
                if not all(key in trade for key in ("price", "amount", "side")):
                    print(f"Trade data is missing necessary fields: {trade}")
                    return

                # Convert amount to float once and store the result
                try:
                    amount = float(trade["amount"]) # base currency
                except ValueError:
                    print(f"Amount is not a number: {trade['amount']}")
                    return

                # Check if side is either "buy" or "sell"
                if trade["side"] not in ("buy", "sell"):
                    print(f"Invalid trade side: {trade['side']}")
                    return

                order_cost = float(trade["price"]) * amount # quote currency
                order_size_category = self.get_order_size_category_(order_cost)

                # Total volume for an exchange and symbol pair
                self.trade_stats[(exchange, symbol)]['volume']['total'] += amount
                
                # Total volume in USD for an exchange and symbol pair
                self.trade_stats[(exchange, symbol)]['volume']['total_usd'] += order_cost

                # CVD for an exchange and symbol pair
                self.trade_stats[(exchange, symbol)]['CVD']['total'] += amount if trade["side"] == "buy" else -amount

                # CVD and Volume for an order size separated into categories based on size for an exchange and symbol pair
                self.trade_stats[(exchange, symbol)]['CVD'][order_size_category] += amount if trade["side"] == "buy" else -amount
                self.trade_stats[(exchange, symbol)]['volume'][order_size_category] += amount

        except Exception as e:
            print(f"Error processing trade data: {e}")

    def get_order_size_category_(self, order_cost):
        if order_cost < 1e4:
            return '0-10k'
        elif order_cost < 1e5:
            return '10k-100k'
        elif order_cost < 1e6:
            return '100k-1m'
        elif order_cost < 1e7:
            return '1m-10m'
        elif order_cost < 1e8:
            return '10m-100m'

    def report_statistics(self):
        header = ['Exchange/Symbol', 'USD Vol', 'Base Vol', 'Delta', '0-10k', '0-10kΔ', '10k-100k', '10k-100kΔ', '100k-1m', '100k-1mΔ', '1m-10m', '1m-10mΔ', '10m-100m', '10m-100mΔ']

        rows = []
        for (exchange, symbol), values in self.trade_stats.items():
            volume = values['volume']['total']
            cvd = values['CVD']['total']
            row = [
                f"{exchange}: {symbol}",
                f"{values['volume']['total_usd']:.2f}",
                f"{volume:.4f}",
                f"{cvd:.4f}",
                f"{values['volume']['0-10k']:.4f}",
                f"{values['CVD']['0-10k']:.4f}",
                f"{values['volume']['10k-100k']:.4f}",
                f"{values['CVD']['10k-100k']:.4f}",
                f"{values['volume']['100k-1m']:.4f}",
                f"{values['CVD']['100k-1m']:.4f}",
                f"{values['volume']['1m-10m']:.4f}",
                f"{values['CVD']['1m-10m']:.4f}",
                f"{values['volume']['10m-100m']:.4f}",
                f"{values['CVD']['10m-100m']:.4f}",
            ]
            rows.append(row)

        print(tabulate(rows, headers=header, tablefmt='grid'))