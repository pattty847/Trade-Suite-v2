import asyncio
import logging
import dotenv
import pandas_ta as ta

from src.gui.viewport import Viewport
from pprint import pprint
from src.analysis.market_analysis import (
    calculate_exhaustion,
    scan_multiple_assets,
    wavetrend_with_signals,
)
from src.data.data_source import Data
from src.data.influx import InfluxDB

logging.basicConfig(level=logging.INFO)
dotenv.load_dotenv()

influx = InfluxDB()


async def main():
    async with Data(influx, exchanges=["coinbasepro"]) as data:
        symbols = ["BTC/USD"]

        # await data.stream_trades(symbols)
        # await data.stream_order_book(['BTC/USD'])

        candles = await data.fetch_candles(["coinbasepro"], ["BTC/USD"], ["1m"])
        # print(candles)
        # signals = scan_multiple_assets(candles)
        # print(signals)

        # How to loop through candles dictionary
        for exchange_name, candles in candles.items():
            for key, ohlcv_df in candles.items():
                symbol, timeframe = key.split("-")

                print(ohlcv_df)
                print(
                    ta.atr(
                        ohlcv_df["high"], ohlcv_df["low"], ohlcv_df["close"], 14
                    ).tail(10)
                )
                # df1 = calculate_exhaustion(df)
                # wt = wavetrend_with_signals(df)
                # print(calc)

                # visualize.create_candlestick_chart(df1)


async def watch_tick_data(symbols):
    async with Data(influx, exchanges=["coinbasepro"]) as data:
        await data.stream_trades(symbols)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    with Viewport() as viewport:
        viewport.run()

    # try:
    #     asyncio.run(main())
    # except KeyboardInterrupt:
    #     print("Program stopped by user.")
