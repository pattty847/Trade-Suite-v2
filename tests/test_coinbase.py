import asyncio
import ccxt.pro as ccxtpro
import logging

# Set up logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

async def test_coinbase_public_data():
    try:
        # Initialize Coinbase without credentials
        logger.info("Initializing Coinbase without credentials...")
        exchange = ccxtpro.coinbase({})
        
        # Load markets
        logger.info("Loading markets...")
        await exchange.load_markets()
        
        # Try to fetch candles
        logger.info("Fetching candles for BTC/USD...")
        candles = await exchange.fetch_ohlcv('BTC/USD', '1m', limit=5)
        logger.info(f"Candles: {candles}")
        
        # Try to fetch recent trades
        logger.info("Fetching recent trades for BTC/USD...")
        trades = await exchange.fetch_trades('BTC/USD', limit=5)
        logger.info(f"Recent trades: {trades}")
        
        # Try to fetch orderbook
        logger.info("Fetching orderbook for BTC/USD...")
        orderbook = await exchange.fetch_order_book('BTC/USD')
        logger.info(f"Orderbook bids (first 3): {orderbook['bids'][:3]}")
        logger.info(f"Orderbook asks (first 3): {orderbook['asks'][:3]}")
        
        # Close the exchange
        await exchange.close()
        logger.info("Exchange closed successfully.")
        
    except Exception as e:
        logger.error(f"Error: {e}")
        if 'exchange' in locals() and hasattr(exchange, 'close'):
            await exchange.close()

if __name__ == "__main__":
    asyncio.run(test_coinbase_public_data()) 