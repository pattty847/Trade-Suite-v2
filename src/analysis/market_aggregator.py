import asyncio
from collections import defaultdict
from datetime import datetime
from typing import List
from influxdb_client import Point, WritePrecision
import pandas as pd
from tabulate import tabulate
from collections import defaultdict
from typing import List

from src.data.influx import InfluxDB
from src.gui.signals import SignalEmitter


class MarketAggregator:
    def __init__(self, influx: InfluxDB, emitter: SignalEmitter):
        self.emitter = emitter
        """
        self.trade_stats = {
            ('exchange1', 'symbol1'): {
                'category1': {
                    'metric1': 0.0,
                    'metric2': 0.0,
                    ...
                },
                'category2': {
                    'metric1': 0.0,
                    'metric2': 0.0,
                    ...
                },
                ...
            },
            ('exchange2', 'symbol2'): {
                ...
            },
            ...
        }
        """
        self.trade_stats = defaultdict(lambda: defaultdict(lambda: defaultdict(float)))
        self.order_size_categories = [
            "0-10k",
            "10k-100k",
            "100k-1m",
            "1m-10m",
            "10m-100m",
        ]
        self.influx = influx

    def calc_trade_stats(self, exchange: str, trades: List[str]) -> None:
        # This function will be passed a particular exchange and tick data (containing the symbol, and other relevant information)
        try:
            for trade in trades:
                symbol = trade["symbol"]
                # Check if necessary fields are in the trade data
                if not all(key in trade for key in ("price", "amount", "side")):
                    print(f"Trade data is missing necessary fields: {trade}")
                    return

                # Convert amount to float once and store the result
                try:
                    amount = float(trade["amount"])  # base currency
                except ValueError:
                    print(f"Amount is not a number: {trade['amount']}")
                    return

                # Check if side is either "buy" or "sell"
                if trade["side"] not in ("buy", "sell"):
                    print(f"Invalid trade side: {trade['side']}")
                    return

                order_cost = float(trade["price"]) * amount  # quote currency
                order_size_category = self.get_order_size_category_(order_cost)

                # Total volume for an exchange and symbol pair
                self.trade_stats[(exchange, symbol)]["volume"]["total_base"] += amount

                # Total volume in USD for an exchange and symbol pair
                self.trade_stats[(exchange, symbol)]["volume"][
                    "total_usd"
                ] += order_cost

                # CVD for an exchange and symbol pair
                self.trade_stats[(exchange, symbol)]["CVD"]["total_base"] += (
                    amount if trade["side"] == "buy" else -amount
                )
                self.trade_stats[(exchange, symbol)]["CVD"]["total_usd"] += (
                    amount * trade["price"]
                    if trade["side"] == "buy"
                    else -amount * trade["price"]
                )

                # CVD and Volume for an order size separated into categories based on size, for an exchange and symbol pair
                self.trade_stats[(exchange, symbol)]["CVD"][order_size_category] += (
                    amount if trade["side"] == "buy" else -amount
                )
                self.trade_stats[(exchange, symbol)]["volume"][
                    order_size_category
                ] += amount

                return symbol, self.trade_stats[(exchange, symbol)]

        except Exception as e:
            print(f"Error processing trade data: {e}")

    def get_order_size_category_(self, order_cost):
        if order_cost < 1e4:
            return "0-10k"
        elif order_cost < 1e5:
            return "10k-100k"
        elif order_cost < 1e6:
            return "100k-1m"
        elif order_cost < 1e7:
            return "1m-10m"
        elif order_cost < 1e8:
            return "10m-100m"

    def report_statistics(self):
        header = [
            "Exchange/Symbol",
            "USD Vol",
            "Base Vol",
            "Delta USD",
            "Delta BASE",
            "0-10k",
            "0-10kΔ",
            "10k-100k",
            "10k-100kΔ",
            "100k-1m",
            "100k-1mΔ",
            "1m-10m",
            "1m-10mΔ",
            "10m-100m",
            "10m-100mΔ",
        ]

        rows = []
        for (exchange, symbol), values in self.trade_stats.items():
            row = [
                f"{exchange}: {symbol}",
                f"{values['volume']['total_usd']:.2f}",  # Volume for USD
                f"{values['volume']['total_base']:.4f}",  # Volume for BASE
                f"{values['CVD']['total_usd']:.4f}",  # CVD for BASE
                f"{values['CVD']['total_base']:.4f}",
            ]  # CVD for USD

            for category in self.order_size_categories:
                row.append(f"{values['volume'][category]:.4f}")  # Volume for category
                row.append(f"{values['CVD'][category]:.4f}")  # Delta for category

            rows.append(row)

        print(tabulate(rows, headers=header, tablefmt="grid"))
        # print(self.trade_stats)
