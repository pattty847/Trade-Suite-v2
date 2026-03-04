import asyncio

from trade_suite.core.data.data_source import Data
import asyncio, os

async def smoke():
    ds = Data(influx=None, emitter=None, exchanges=['coinbase'], force_public=True)
    await ds.load_exchanges()
    stop = asyncio.Event()
    async def dummy(event): pass
    t1 = asyncio.create_task(ds.watch_orderbook('coinbase','BTC/USD', stop, sink=dummy, cadence_ms=200))
    await asyncio.sleep(3)
    stop.set(); await t1
    
asyncio.run(smoke())
