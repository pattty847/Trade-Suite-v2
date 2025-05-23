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
    percentage: float
    timeframe: int = Field(description="Timeframe in minutes")
    cooldown: int = Field(default=1800, description="Seconds before this alert can trigger again")
    
    @field_validator('percentage')
    @classmethod
    def percentage_must_be_positive(cls, v):
        if v <= 0:
            raise ValueError('Percentage must be positive')
        return v
    
    @field_validator('timeframe')
    @classmethod
    def timeframe_must_be_positive(cls, v):
        if v <= 0:
            raise ValueError('Timeframe must be positive')
        return v

class VolatilityRule(BaseModel):
    """Rule that triggers when price volatility exceeds threshold within timeframe"""
    threshold: float
    timeframe: int = Field(description="Timeframe in minutes")
    cooldown: int = Field(default=3600, description="Seconds before this alert can trigger again")
    
    @field_validator('threshold')
    @classmethod
    def threshold_must_be_positive(cls, v):
        if v <= 0:
            raise ValueError('Threshold must be positive')
        return v
    
    @field_validator('timeframe')
    @classmethod
    def timeframe_must_be_positive(cls, v):
        if v <= 0:
            raise ValueError('Timeframe must be positive')
        return v

class SymbolConfig(BaseModel):
    """Configuration for a single trading symbol"""
    price_levels: List[PriceLevelRule] = Field(default_factory=list)
    percentage_changes: List[PercentageChangeRule] = Field(default_factory=list)
    volatility: List[VolatilityRule] = Field(default_factory=list)
    
    @model_validator(mode='after')
    def at_least_one_rule(self) -> 'SymbolConfig':
        """Ensure there's at least one rule defined"""
        has_rules = (
            len(self.price_levels) > 0 or
            len(self.percentage_changes) > 0 or
            len(self.volatility) > 0
        )
        if not has_rules:
            raise ValueError('At least one rule type must be defined for the symbol')
        return self

class AlertConfig(BaseModel):
    """Root configuration object with all symbols and their rules"""
    symbols: Dict[str, SymbolConfig]
    
    # Custom constructor to translate from the flat YAML format to our nested structure
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'AlertConfig':
        """Convert from flat dict of symbols to nested structure"""
        return cls(symbols={symbol: SymbolConfig(**config) for symbol, config in data.items()})

def load_config(config_path: Union[str, Path]) -> AlertConfig:
    """
    Load and validate the alert configuration from a YAML file
    
    Args:
        config_path: Path to the YAML configuration file
        
    Returns:
        Validated AlertConfig object
        
    Raises:
        FileNotFoundError: If config file doesn't exist
        ValidationError: If config doesn't match the expected schema
        Exception: Other parsing/loading errors
    """
    config_path = Path(config_path)
    
    if not config_path.exists():
        raise FileNotFoundError(f"Config file not found: {config_path}")
    
    try:
        with open(config_path, 'r') as f:
            raw_config = yaml.safe_load(f)
        
        if not isinstance(raw_config, dict):
            raise ValueError(f"Config must be a dictionary, got {type(raw_config)}")
        
        # Parse the config through our Pydantic model for validation
        config = AlertConfig.from_dict(raw_config)
        
        logger.info(f"Successfully loaded config with {len(config.symbols)} symbols")
        return config
        
    except Exception as e:
        logger.error(f"Failed to load config from {config_path}: {e}")
        raise

if __name__ == "__main__":
    # Example usage
    import sys
    logging.basicConfig(level=logging.INFO)
    
    if len(sys.argv) > 1:
        config_file = sys.argv[1]
    else:
        config_file = "alerts_config.yaml"
    
    try:
        config = load_config(config_file)
        print(f"Loaded config with {len(config.symbols)} symbols")
        for symbol, symbol_config in config.symbols.items():
            print(f"\n{symbol}:")
            if symbol_config.price_levels:
                print(f"  Price Levels: {len(symbol_config.price_levels)}")
            if symbol_config.percentage_changes:
                print(f"  Percentage Changes: {len(symbol_config.percentage_changes)}")
            if symbol_config.volatility:
                print(f"  Volatility Rules: {len(symbol_config.volatility)}")
    except Exception as e:
        print(f"Error: {e}")
        sys.exit(1) 