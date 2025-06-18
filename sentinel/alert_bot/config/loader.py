#!/usr/bin/env python3
from typing import List, Dict, Optional, Literal, Any, Union, ClassVar
from datetime import timedelta
from pathlib import Path
import logging
import yaml
from pydantic import BaseModel, Field, field_validator, model_validator

logger = logging.getLogger(__name__)

class PriceLevelRule(BaseModel):
    """Rule that triggers when price crosses above/below a specified level"""
    price: float
    condition: Literal['above', 'below']
    cooldown: int = Field(default=300, description="Seconds before this alert can trigger again")
    
    @field_validator('price')
    @classmethod
    def price_must_be_positive(cls, v):
        if v <= 0:
            raise ValueError('Price must be positive')
        return v
    
    @field_validator('cooldown')
    @classmethod
    def cooldown_must_be_positive(cls, v):
        if v < 0:
            raise ValueError('Cooldown must be non-negative')
        return v

class PercentageChangeRule(BaseModel):
    """Rule that triggers when price changes by X% within specified timeframe"""
    type: Literal['percentage_change'] = 'percentage_change'
    percentage: float
    lookback_duration_str: str = Field(description="The total lookback period (e.g., '60m', '4h', '1d')")
    candle_timeframe: str = Field(description="The timeframe of the candles this rule applies to (e.g., '5m', '1h')")
    price_point_to_use: Literal['open', 'high', 'low', 'close'] = Field(default='close', description="Which candle price point to use")
    cooldown: int = Field(default=1800, description="Seconds before this alert can trigger again")
    
    @field_validator('percentage')
    @classmethod
    def percentage_must_be_positive(cls, v):
        if v <= 0:
            raise ValueError('Percentage must be positive')
        return v

class VolatilityRule(BaseModel):
    """Rule that triggers when price volatility exceeds threshold within timeframe"""
    type: Literal['volatility'] = 'volatility'
    threshold: float
    timeframe_duration_str: str = Field(description="Timeframe for volatility calculation (e.g., '30m')")
    candle_timeframe: str = Field(description="Candle timeframe for data source (e.g., '1m')")
    cooldown: int = Field(default=3600, description="Seconds before this alert can trigger again")
    
    @field_validator('threshold')
    @classmethod
    def threshold_must_be_positive(cls, v):
        if v <= 0:
            raise ValueError('Threshold must be positive')
        return v

class CVDRule(BaseModel):
    """Rule that triggers based on Cumulative Volume Delta conditions"""
    type: Literal['cvd_change', 'cvd_ratio', 'cvd_level']
    timeframe_duration_str: str = Field(description="Lookback duration for CVD calculation (e.g., '15m', '1h')")
    cooldown: int = Field(default=1800, description="Seconds before this alert can trigger again")
    
    # For 'cvd_change' type alerts
    cvd_threshold: Optional[float] = Field(default=None, description="Absolute CVD change threshold")
    cvd_percentage_threshold: Optional[float] = Field(default=None, description="CVD percentage change threshold")
    
    # For 'cvd_ratio' type alerts
    buy_ratio_threshold: Optional[float] = Field(default=None, description="Buy volume ratio threshold (0.0-1.0)")
    sell_ratio_threshold: Optional[float] = Field(default=None, description="Sell volume ratio threshold (0.0-1.0)")
    
    # For 'cvd_level' type alerts
    cvd_level: Optional[float] = Field(default=None, description="CVD level to watch for")
    level_condition: Literal['above', 'below'] = Field(default='above', description="Trigger when CVD goes above or below level")
    
    @field_validator('buy_ratio_threshold', 'sell_ratio_threshold')
    @classmethod
    def ratio_must_be_valid(cls, v):
        if v is not None and (v < 0 or v > 1):
            raise ValueError('Ratio thresholds must be between 0.0 and 1.0')
        return v
    
    @model_validator(mode='after')
    def validate_type_requirements(self) -> 'CVDRule':
        if self.type == 'cvd_change':
            if self.cvd_threshold is None and self.cvd_percentage_threshold is None:
                raise ValueError('cvd_change type requires cvd_threshold or cvd_percentage_threshold')
        elif self.type == 'cvd_ratio':
            if self.buy_ratio_threshold is None and self.sell_ratio_threshold is None:
                raise ValueError('cvd_ratio type requires buy_ratio_threshold or sell_ratio_threshold')
        elif self.type == 'cvd_level':
            if self.cvd_level is None:
                raise ValueError('cvd_level type requires cvd_level')
        return self

class PriceLevelConfigRule(BaseModel):
    """Pydantic model for price_level rules as expected by manager.py"""
    type: Literal['price_level'] = 'price_level'
    target_price: float
    condition: Literal['above', 'below']
    cooldown: int = Field(default=300, description="Seconds before alert can trigger again")
    enabled: bool = True

AnyRule = Union[PriceLevelConfigRule, PercentageChangeRule, VolatilityRule, CVDRule]

class SymbolAlertConfig(BaseModel):
    """Configuration for a single trading symbol, aligning with manager.py expectations."""
    exchange: str = Field(description="Exchange ID (e.g., coinbase, binance)")
    symbol: str = Field(description="Trading symbol (e.g., BTC/USDT)")
    rules: List[AnyRule] = Field(default_factory=list, description="List of all rules for this symbol")
    price_precision: int = Field(default=2, description="Default price precision for formatting alerts")
    volume_precision: int = Field(default=3, description="Default volume precision for formatting alerts (e.g. CVD values)")

    @model_validator(mode='before')
    @classmethod
    def consolidate_rules(cls, data: Any) -> Any:
        if isinstance(data, dict):
            pass
        return data

class ActiveAlertsConfig(BaseModel):
    symbols: Dict[str, SymbolAlertConfig]

class NotifierConfig(BaseModel):
    id: str
    type: Literal['console', 'email']
    enabled: bool = True
    config: Dict[str, Any] = Field(default_factory=dict, description="Notifier-specific settings (e.g., email to, smtp_host)")

class NotificationSettings(BaseModel):
    notifiers: List[NotifierConfig] = Field(default_factory=list)

class GlobalAlertConfig(BaseModel):
    """ The main configuration model that manager.py loads. """
    alerts: ActiveAlertsConfig
    notification_settings: NotificationSettings = Field(default_factory=NotificationSettings)

def load_alerts_from_yaml(config_path: Union[str, Path]) -> GlobalAlertConfig:
    config_path = Path(config_path)
    if not config_path.exists():
        logger.error(f"Configuration file not found: {config_path}")
        raise FileNotFoundError(f"Config file not found: {config_path}")

    try:
        with open(config_path, 'r') as f:
            raw_config_data = yaml.safe_load(f)
        
        if not isinstance(raw_config_data, dict):
            raise ValueError(f"Config root must be a dictionary, got {type(raw_config_data)}")

        parsed_config = GlobalAlertConfig(**raw_config_data)
        
        num_symbols = 0
        if parsed_config.alerts and parsed_config.alerts.symbols:
            num_symbols = len(parsed_config.alerts.symbols)
        
        logger.info(f"Successfully loaded GlobalAlertConfig with {num_symbols} symbols and {len(parsed_config.notification_settings.notifiers)} notifiers.")
        return parsed_config
        
    except Exception as e:
        logger.exception(f"Error loading or parsing GlobalAlertConfig from {config_path}: {e}")
        raise

def create_example_global_config_file(output_file_path: Path):
    """Creates an example global alert configuration YAML file at the specified path."""
    example_config_content = {
        "alerts": {
            "symbols": {
                "BTC/USD": {
                    "exchange": "coinbase",
                    "symbol": "BTC/USD",
                    "price_precision": 2,
                    "volume_precision": 3,
                    "rules": [
                        {
                            "type": "price_level",
                            "target_price": 50000,
                            "condition": "below",
                            "cooldown": 300,
                            "enabled": True
                        },
                        {
                            "type": "percentage_change",
                            "percentage": 5,
                            "lookback_duration_str": "1h",
                            "candle_timeframe": "5m",
                            "price_point_to_use": "close",
                            "cooldown": 1800,
                            "enabled": True
                        },
                        {
                            "type": "cvd_change",
                            "timeframe_duration_str": "30m",
                            "cvd_threshold": 100000,
                            "cooldown": 1800,
                            "enabled": True
                        }
                    ]
                }
            }
        },
        "notification_settings": {
            "notifiers": [
                {
                    "id": "console_1",
                    "type": "console",
                    "enabled": True,
                    "config": {}
                },
                {
                    "id": "email_1",
                    "type": "email",
                    "enabled": False, # Example: disabled email notifier
                    "config": {
                        "email_to": ["alerts@example.com"],
                        "smtp_host": "smtp.example.com",
                        "smtp_port": 587,
                        "smtp_user": "user@example.com",
                        "smtp_password_env_var": "SMTP_PASSWORD", # IMPORTANT: Store actual password in env var
                        "email_from": "bot@example.com"
                    }
                }
            ]
        }
    }
    try:
        with open(output_file_path, 'w') as f:
            yaml.dump(example_config_content, f, indent=2, sort_keys=False)
        logger.info(f"Successfully created example global config: {output_file_path}")
    except Exception as e:
        logger.exception(f"Error writing example global config to {output_file_path}: {e}")
        raise # Re-raise the exception so the caller knows

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(name)s - %(message)s')
    
    # Define the default path for the example config when loader.py is run directly
    default_example_path = Path(__file__).parent / "example_global_alerts_config.yaml"
    
    try:
        create_example_global_config_file(default_example_path)
        # Test loading the new example config
        loaded_global_config = load_alerts_from_yaml(default_example_path)
        logger.info(f"Successfully loaded example config after creation: {loaded_global_config.model_dump_json(indent=2)}")
    except Exception as e:
        # Error already logged by create_example_global_config_file or load_alerts_from_yaml
        pass # Avoid duplicate logging, error is already detailed 