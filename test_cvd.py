#!/usr/bin/env python3
"""
Test script for CVD functionality
Run this to test trade streaming and CVD calculation
"""
import asyncio
import logging
import sys
from pathlib import Path

if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

# Add the project root to Python path
sys.path.append(str(Path(__file__).parent.parent))

from sentinel.alert_bot.fetcher.trade_streamer import TradeStreamer, CVDCalculator, TradeData
from datetime import datetime, timedelta

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

async def test_cvd_calculator():
    """Test the CVD calculator with mock data"""
    logger.info("Testing CVD Calculator...")
    
    cvd_calc = CVDCalculator(lookback_minutes=10)
    
    # Create some mock trades
    now = datetime.now()
    mock_trades = [
        TradeData(now - timedelta(minutes=8), 50000, 1.5, 'buy'),    # +1.5
        TradeData(now - timedelta(minutes=7), 50100, 0.8, 'sell'),   # -0.8
        TradeData(now - timedelta(minutes=6), 50200, 2.0, 'buy'),    # +2.0
        TradeData(now - timedelta(minutes=5), 50150, 1.0, 'sell'),   # -1.0
        TradeData(now - timedelta(minutes=4), 50300, 3.0, 'buy'),    # +3.0
        TradeData(now - timedelta(minutes=3), 50250, 0.5, 'buy'),    # +0.5
        TradeData(now - timedelta(minutes=2), 50200, 1.2, 'sell'),   # -1.2
        TradeData(now - timedelta(minutes=1), 50350, 2.5, 'buy'),    # +2.5
    ]
    
    # Expected CVD: 1.5 - 0.8 + 2.0 - 1.0 + 3.0 + 0.5 - 1.2 + 2.5 = 6.5
    
    for trade in mock_trades:
        cvd_calc.add_trade(trade)
        logger.info(f"Added trade: {trade}, CVD now: {cvd_calc.get_cvd():.2f}")
    
    final_cvd = cvd_calc.get_cvd()
    logger.info(f"Final CVD: {final_cvd:.2f} (expected: 6.5)")
    
    # Test CVD changes
    cvd_change_5m = cvd_calc.get_cvd_change(5)
    logger.info(f"CVD change over 5 minutes: {cvd_change_5m}")
    
    # Test buy/sell ratios
    ratio_data = cvd_calc.get_buy_sell_ratio(5)
    logger.info(f"Buy/Sell ratio (5m): {ratio_data}")
    
    return abs(final_cvd - 6.5) < 0.01  # Allow small floating point errors

async def test_trade_streaming():
    """Test actual trade streaming (requires internet connection)"""
    logger.info("Testing Trade Streaming...")
    
    streamer = TradeStreamer(exchange_id='coinbase', lookback_minutes=5)
    
    try:
        await streamer.initialize()
        
        # Test callback
        def cvd_callback(symbol, cvd_value, extra_data):
            logger.info(f"CVD Update: {symbol} = {cvd_value:.2f}")
            logger.info(f"Extra data: {extra_data}")
        
        streamer.register_callback(cvd_callback)
        streamer.track_symbol('BTC/USD')
        
        # Start streaming and let it run for 2 minutes
        logger.info("Starting trade streaming for 2 minutes...")
        await streamer.start()
        await asyncio.sleep(120)  # Let it run for 2 minutes
        
        # Check results
        cvd_data = streamer.get_cvd_data('BTC/USD')
        if cvd_data:
            logger.info(f"Final CVD data for BTC/USD: {cvd_data}")
            return True
        else:
            logger.warning("No CVD data collected")
            return False
            
    except Exception as e:
        logger.error(f"Error in trade streaming test: {e}")
        return False
    finally:
        await streamer.stop()

async def test_cvd_rule():
    """Test CVD rule evaluation with mock data"""
    logger.info("Testing CVD Rule...")
    
    from sentinel.alert_bot.rules.cvd import CVDRule
    from sentinel.alert_bot.state.manager import StateManager
    
    # Create a CVD rule
    config = {
        'type': 'change',
        'cvd_threshold': 5.0,
        'timeframe': 15,
        'cooldown': 300
    }
    
    rule = CVDRule('BTC/USD', config)
    state_manager = StateManager()
    
    # Mock CVD data showing a significant change
    mock_cvd_data = {
        'cvd': 150.5,
        'cvd_change_15m': 7.2,  # Above threshold
        'cvd_change_5m': 3.1,
        'buy_sell_ratio_15m': {
            'buy_ratio': 0.65,
            'sell_ratio': 0.35,
            'buy_volume': 1300,
            'sell_volume': 700
        }
    }
    
    extra_data = {'cvd_data': mock_cvd_data}
    
    # Evaluate rule
    result = rule.evaluate(50000, state_manager, extra_data)
    
    if result:
        logger.info(f"CVD Rule triggered: {result}")
        return True
    else:
        logger.warning("CVD Rule did not trigger (expected it to)")
        return False

async def main():
    """Run all tests"""
    logger.info("Starting CVD functionality tests...")
    
    # Test 1: CVD Calculator
    test1_passed = await test_cvd_calculator()
    logger.info(f"CVD Calculator test: {'PASSED' if test1_passed else 'FAILED'}")
    
    # Test 2: CVD Rule
    test2_passed = await test_cvd_rule()
    logger.info(f"CVD Rule test: {'PASSED' if test2_passed else 'FAILED'}")
    
    # Test 3: Trade Streaming (optional - requires network)
    try_streaming = input("Test live trade streaming? (requires internet) [y/N]: ").lower().startswith('y')
    test3_passed = True
    
    if try_streaming:
        test3_passed = await test_trade_streaming()
        logger.info(f"Trade Streaming test: {'PASSED' if test3_passed else 'FAILED'}")
    else:
        logger.info("Skipping trade streaming test")
    
    # Summary
    total_tests = 2 + (1 if try_streaming else 0)
    passed_tests = sum([test1_passed, test2_passed, test3_passed])
    
    logger.info(f"\n=== TEST SUMMARY ===")
    logger.info(f"Tests passed: {passed_tests}/{total_tests}")
    
    if passed_tests == total_tests:
        logger.info("🎉 All tests passed! CVD functionality is ready.")
    else:
        logger.warning("⚠️  Some tests failed. Check the logs above.")

if __name__ == "__main__":
    asyncio.run(main())