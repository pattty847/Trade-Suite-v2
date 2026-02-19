#!/usr/bin/env python3
"""
Utility script to generate an example configuration file for the Crypto Price Alert Bot.
"""
import logging
import yaml
from pathlib import Path

# Set up logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def create_example_config():
    """Create an example configuration file"""
    example_config = {
        'BTC/USD': {
            'price_levels': [
                {'price': 50000, 'condition': 'above', 'cooldown': 3600},
                {'price': 45000, 'condition': 'below', 'cooldown': 3600}
            ],
            'percentage_changes': [
                {'percentage': 5, 'timeframe': 10, 'cooldown': 1800}  # 10 minutes
            ],
            'volatility': [
                {'threshold': 2, 'timeframe': 5, 'cooldown': 3600}  # 5 minutes
            ]
        },
        'ETH/USD': {
            'price_levels': [
                {'price': 3000, 'condition': 'above', 'cooldown': 3600},
                {'price': 2500, 'condition': 'below', 'cooldown': 3600}
            ],
            'percentage_changes': [
                {'percentage': 7, 'timeframe': 15, 'cooldown': 1800}
            ],
            'volatility': [
                {'threshold': 3, 'timeframe': 5, 'cooldown': 3600}
            ]
        },
        'PEPE/USD': {  # Example for high precision
            'price_levels': [
                {'price': 0.00001700, 'condition': 'above', 'cooldown': 3600},
                {'price': 0.00001200, 'condition': 'below', 'cooldown': 3600}
            ]
        }
    }
    
    # Ensure config directory exists
    config_dir = Path(__file__).parent
    config_path = config_dir / 'alerts_config.yaml'
    
    # Write the config file
    with open(config_path, 'w') as f:
        yaml.dump(example_config, f, default_flow_style=False)
    
    logger.info(f"Created example configuration file at {config_path}")
    return config_path

if __name__ == "__main__":
    config_path = create_example_config()
    print(f"Example configuration created at: {config_path}")
    print("You can now run the alert bot with:")
    print(f"  python -m sentinel.alert_bot.main --config {config_path}") 