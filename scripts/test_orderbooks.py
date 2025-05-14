import asyncio
import json
import os
from ccxt.pro.coinbase import coinbase

async def test_orderbook_stream():
    # Initialize the exchange
    exchange = coinbase({
        # 'apiKey': 'YOUR_API_KEY',  # Replace with your actual API key
        # 'secret': 'YOUR_SECRET',   # Replace with your actual secret
    })

    # Define the symbol for Bitcoin
    symbol = 'BTC/USD'

    try:
        # Watch the order book for the specified symbol
        orderbook = await exchange.watch_order_book(symbol, parse=False)

        # Define the output file path
        output_file_path = 'orderbook_stream.json'

        # Save the order book data to a JSON file
        with open(output_file_path, 'w', encoding='utf-8') as f:
            json.dump(orderbook, f, ensure_ascii=False, indent=4)

        print(f"Order book data saved to {output_file_path}")

    except Exception as e:
        print(f"An error occurred: {e}")

    finally:
        # Ensure the exchange is closed properly
        await exchange.close()

# Run the test
if __name__ == "__main__":
    asyncio.run(test_orderbook_stream())
