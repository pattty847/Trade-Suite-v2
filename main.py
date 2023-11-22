import asyncio
import logging
from pprint import pprint
import dotenv
import visualize

from analysis.market_analysis import calculate_exhaustion, scan_multiple_assets
from data_source import Data
from influx import InfluxDB

logging.basicConfig(level=logging.INFO)
dotenv.load_dotenv()

influx = InfluxDB()

async def main():
    async with Data(influx, exchanges=['coinbasepro', 'kucoin']) as data:
        symbols = ['BTC/USD', 'ETH/USD', 'DOGE/USD', 'SOL/USD']
        limit = 100
        params = {}
        
        
        # await data.stream_trades(symbols)
        # await data.stream_order_book(['BTC/USD'])
        
        candles = await data.fetch_candles(['coinbasepro'], ['BTC/USD', 'ETH/USD'], ['1m', '5m'])
        signals = scan_multiple_assets(candles)
        
        print(signals)
        
        
        # for exchange_name, candles in candles.items():
        #     for key, df in candles.items():
        #         symbol, timeframe = key.split('-')
        #         print(symbol, timeframe)
        #         print(df)
        #         calc = calculate_exhaustion(df)
        #         calc.to_csv('save.csv')

                # visualize.create_candlestick_chart(df)
    
if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("Program stopped by user.")