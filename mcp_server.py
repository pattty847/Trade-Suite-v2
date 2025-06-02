import asyncio
import logging
from typing import List, Dict, Any

import pandas as pd
import uvicorn
from fastapi import FastAPI, HTTPException, Depends
from pydantic import BaseModel, Field

# Assuming data_source.py is in the trade_suite.data package and accessible
# Adjust the import path if your project structure is different
from trade_suite.data.data_source import Data
from trade_suite.gui.signals import SignalEmitter, Signals # Keep original imports
from trade_suite.data.influx import InfluxDB # Keep original imports

# --- Configuration ---
# For simplicity, we'll use basic logging. You might want to enhance this.
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# --- Dummy Implementations (Replace with your actual classes or mocks) ---
class DummyInfluxDB:
    async def write_candles(self, all_candles: Dict):
        logger.info(f"Dummy InfluxDB: 'Writing' {len(all_candles)} exchange(s) candle data.")
        # In a real scenario, this would write to InfluxDB
        pass

    async def write_trades(self, exchange_id: str, trades: list):
        logger.info(f"Dummy InfluxDB: 'Writing' {len(trades)} trades for {exchange_id}.")
        pass

    async def write_stats(self, exchange_id: str, stats: dict, symbol: str):
        logger.info(f"Dummy InfluxDB: 'Writing' stats for {exchange_id} - {symbol}.")
        pass

class DummySignalEmitter:
    def emit(self, signal_type, **kwargs):
        logger.info(f"Dummy Emitter: Emitting signal {signal_type} with data: {kwargs}")
        pass

    def emit_threadsafe(self, loop, signal_type, **kwargs):
        logger.info(f"Dummy Emitter (thread-safe): Emitting signal {signal_type} with data: {kwargs}")
        pass

# --- Pydantic Models for API ---
class FetchCandlesRequest(BaseModel):
    exchanges: List[str] = Field(..., example=["binance", "coinbasepro"])
    symbols: List[str] = Field(..., example=["BTC/USDT", "ETH/USD"])
    since: str = Field(..., example="2023-01-01T00:00:00Z") # ISO8601 format
    timeframes: List[str] = Field(..., example=["1h", "4h"])
    write_to_db: bool = False

class CandleData(BaseModel):
    dates: int
    opens: float
    highs: float
    lows: float
    closes: float
    volumes: float
    exchange: str | None = None # Optional metadata, if saved with it
    symbol: str | None = None
    timeframe: str | None = None

class FetchCandlesResponse(BaseModel):
    status: str = "success"
    # Structure: {exchange_name: {cache_key: [CandleData]}}
    data: Dict[str, Dict[str, List[CandleData]]] = Field(default_factory=dict)
    message: str | None = None

# --- FastAPI Application ---
app = FastAPI(
    title="Trade Suite MCP Server",
    description="Server to interact with Trade Suite data functionalities for AI agents.",
    version="0.1.0"
)

# --- Dependency Injection for Data Class ---
async def get_data_service():
    # In a real application, you might have more complex setup for InfluxDB and Emitter
    # For now, using dummy implementations.
    # Ensure these dummy classes have the methods your Data class expects.
    dummy_influx = DummyInfluxDB() 
    dummy_emitter = DummySignalEmitter()
    
    # Initialize Data with desired exchanges. 
    # For testing, ensure exchanges like 'binance' are valid and have public API access if force_public=True
    # Or, provide valid API keys if force_public=False and your CCXTInterface expects them.
    data_service = Data(influx=dummy_influx, emitter=dummy_emitter, exchanges=["binance"], force_public=True)
    # data_service.set_ui_loop(asyncio.get_event_loop()) # If your Data class requires a UI loop set
    return data_service

# --- API Endpoints ---
@app.post("/fetch_candles", response_model=FetchCandlesResponse)
async def fetch_candles_endpoint(request_data: FetchCandlesRequest, data_service: Data = Depends(get_data_service)):
    logger.info(f"Received /fetch_candles request: {request_data.model_dump()}")
    try:
        # Call the actual fetch_candles method
        raw_candle_data = await data_service.fetch_candles(
            exchanges=request_data.exchanges,
            symbols=request_data.symbols,
            since=request_data.since,
            timeframes=request_data.timeframes,
            write_to_db=request_data.write_to_db
        )

        # Convert pandas DataFrames to list of Pydantic models
        formatted_data: Dict[str, Dict[str, List[CandleData]]] = {}
        if raw_candle_data:
            for exchange, symbol_data in raw_candle_data.items():
                formatted_data[exchange] = {}
                for key, df in symbol_data.items():
                    if isinstance(df, pd.DataFrame) and not df.empty:
                        # Ensure 'dates' is int64 if it exists. Handle potential NaNs if converting floats.
                        if 'dates' in df.columns:
                            df['dates'] = pd.to_numeric(df['dates'], errors='coerce').fillna(0).astype('int64')
                        formatted_data[exchange][key] = [CandleData(**row) for row in df.to_dict(orient='records')]
                    else:
                        formatted_data[exchange][key] = [] # Empty list if no data or not a DataFrame
        
        return FetchCandlesResponse(data=formatted_data)
    
    except ValueError as ve:
        logger.error(f"ValueError in /fetch_candles: {ve}", exc_info=True)
        raise HTTPException(status_code=400, detail=str(ve))
    except Exception as e:
        logger.error(f"Error processing /fetch_candles: {e}", exc_info=True)
        # Return a more generic error to the client for unexpected issues
        raise HTTPException(status_code=500, detail=f"An unexpected error occurred: {type(e).__name__}")

@app.get("/")
async def root():
    return {"message": "Welcome to the Trade Suite MCP Server. Use /docs for API documentation."}

# --- Main entry point for running the server (e.g., with uvicorn) ---
if __name__ == "__main__":
    # You would typically run this with: uvicorn mcp_server:app --reload
    # The host and port can be configured as needed.
    uvicorn.run(app, host="0.0.0.0", port=8000, log_level="info") 