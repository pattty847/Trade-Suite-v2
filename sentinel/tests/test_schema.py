import unittest
from sentinel import schema
from sentinel import config # For accessing constants like RAW_BOOK_TOP_N for tests

class TestSchemaBuilders(unittest.TestCase):

    def test_build_trade_lp_example(self):
        exchange = "coinbase"
        symbol = "BTC/USD" # CCXT format
        safe_symbol_expected = "BTC-USD"
        side = "buy"
        size = 0.1
        price = 50000.0
        trade_id = "trd123"
        timestamp_ns = 1678886400123456789

        lp = schema.build_trade_lp(exchange, symbol, side, size, price, trade_id, timestamp_ns)
        
        expected_tags = f"trades,exchange={exchange},symbol={safe_symbol_expected},side={side}"
        expected_fields = f"trade_id=\"{trade_id}\",price={float(price)},size={float(size)}"
        expected_timestamp = str(timestamp_ns)

        self.assertTrue(lp.startswith(expected_tags))
        self.assertIn(expected_fields, lp)
        self.assertTrue(lp.endswith(expected_timestamp))
        self.assertEqual(lp.count(' '), 2) # Tags, Fields, Timestamp

    def test_build_book_lp_binned_example(self):
        exchange = "testex"
        symbol = "ETH/USD"
        safe_symbol_expected = "ETH-USD"
        # Bids sorted high to low, Asks sorted low to high
        bids = [(2998.0, 0.5), (2997.0, 1.0)] 
        asks = [(3002.0, 0.3), (3003.0, 0.8)]
        timestamp_ns = 1678886500987654321
        sequence = 12345

        # Expected mid_price = (2998.0 + 3002.0) / 2.0 = 3000.0
        # With BIN_BPS = 5 (0.05%), one bin width is 3000 * 0.0005 = 1.5 USD
        # Max bins per side = 5

        lp_lines = schema.build_book_lp(exchange, symbol, bids, asks, timestamp_ns, sequence)

        # Expected number of lines: (MAX_BINS_PER_SIDE * 2) + 1 (for mid_bin)
        expected_line_count = config.ORDER_BOOK_MAX_BINS_PER_SIDE * 2 + 1
        self.assertEqual(len(lp_lines), expected_line_count)

        found_specific_bid_bin = False
        found_specific_ask_bin = False
        found_mid_bin = False

        for lp in lp_lines:
            self.assertIn(f"order_book,exchange={exchange},symbol={safe_symbol_expected}", lp)
            self.assertIn(f"sequence={sequence}i", lp) # Check sequence field
            self.assertTrue(lp.endswith(str(timestamp_ns)))

            # Example check for a bid at 2998.0: (2998 - 3000) / 3000 * 10000 / 5 = -0.66 / 5 = -1.33 -> round = -1
            if f"side=bid,bps_offset_idx=-1" in lp:
                self.assertIn(f"total_qty=0.5", lp) # Approx, need to sum if multiple fall in same bin
                found_specific_bid_bin = True
            # Example check for an ask at 3002.0: (3002 - 3000) / 3000 * 10000 / 5 = 0.66 / 5 = 1.33 -> round = 1
            if f"side=ask,bps_offset_idx=1" in lp:
                self.assertIn(f"total_qty=0.3", lp)
                found_specific_ask_bin = True
            if f"side=mid_bin,bps_offset_idx=0" in lp:
                # qty might be 0 or sum of items very close to mid depending on exact rounding and data
                found_mid_bin = True
        
        self.assertTrue(found_specific_bid_bin, "Specific bid bin not found or incorrect.")
        self.assertTrue(found_specific_ask_bin, "Specific ask bin not found or incorrect.")
        self.assertTrue(found_mid_bin, "Mid bin not found.")

    def test_build_book_lp_binned_empty_input(self):
        lp_lines = schema.build_book_lp("test", "SYM", [], [], 123)
        self.assertEqual(len(lp_lines), 0)
        lp_lines = schema.build_book_lp("test", "SYM", [(1,1)], [], 123)
        self.assertEqual(len(lp_lines), 0)

    def test_build_raw_book_lp_example(self):
        exchange = "rawex"
        symbol = "ADA/USDT"
        safe_symbol_expected = "ADA-USDT"
        bids = [(1.00, 100.0), (0.99, 50.0)] * (config.RAW_BOOK_TOP_N // 2) # Ensure enough data
        asks = [(1.01, 80.0), (1.02, 60.0)] * (config.RAW_BOOK_TOP_N // 2)
        timestamp_ns = 1678886600000000000
        sequence = 54321

        lp_lines = schema.build_raw_book_lp(exchange, symbol, bids, asks, timestamp_ns, top_n=config.RAW_BOOK_TOP_N, sequence=sequence)
        
        expected_line_count = config.RAW_BOOK_TOP_N * 2 # N bids + N asks
        self.assertEqual(len(lp_lines), expected_line_count)

        for i in range(config.RAW_BOOK_TOP_N):
            bid_lp = lp_lines[i]
            ask_lp = lp_lines[i + config.RAW_BOOK_TOP_N]

            self.assertTrue(bid_lp.startswith(f"raw_order_book,exchange={exchange},symbol={safe_symbol_expected},side=bid,level={i}"))
            self.assertIn(f"price={float(bids[i][0])},amount={bids[i][1]:.8f}", bid_lp)
            self.assertIn(f"sequence={sequence}i", bid_lp)
            self.assertTrue(bid_lp.endswith(str(timestamp_ns)))

            self.assertTrue(ask_lp.startswith(f"raw_order_book,exchange={exchange},symbol={safe_symbol_expected},side=ask,level={i}"))
            self.assertIn(f"price={float(asks[i][0])},amount={asks[i][1]:.8f}", ask_lp)
            self.assertIn(f"sequence={sequence}i", ask_lp)
            self.assertTrue(ask_lp.endswith(str(timestamp_ns)))

    def test_build_raw_book_lp_less_data_than_top_n(self):
        bids = [(1.0, 10.0)]
        asks = [(1.1, 11.0)]
        lp_lines = schema.build_raw_book_lp("test", "SYM", bids, asks, 123, top_n=5)
        self.assertEqual(len(lp_lines), 2) # 1 bid + 1 ask
        self.assertIn("level=0", lp_lines[0])
        self.assertIn("level=0", lp_lines[1])

if __name__ == '__main__':
    unittest.main() 