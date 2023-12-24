import pandas as pd
import asyncio
import logging
import dotenv

from lightweight_charts import Chart
from src.data.influx import InfluxDB

logging.basicConfig(level=logging.INFO)
dotenv.load_dotenv()

infl = InfluxDB()

if __name__ == '__main__':
    
    chart = Chart()
    results = infl.query_candles('coinbasepro', 'ETH/USD', '1h')
    # Columns: time | open | high | low | close | volume 
    # Convert the time column to string format
    results['_time'] = results['_time'].astype(str)
    results.rename(columns={'_time': 'date'}, inplace=True)
    print(results)
    
    chart.set(results)
    
    chart.show(block=True)