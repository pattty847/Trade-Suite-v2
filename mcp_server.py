import asyncio
import logging
from typing import List, Dict, Any
from contextlib import asynccontextmanager # Added for lifespan manager

import pandas as pd
import uvicorn
from fastapi import FastAPI, HTTPException, Depends, Request
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

# --- Lifespan Event Handler ---
@asynccontextmanager
async def lifespan_manager(app_instance: FastAPI):
    # Code to run on startup
    logger.info("Lifespan: Startup - Initializing Data service...")
    dummy_influx = DummyInfluxDB()
    dummy_emitter = DummySignalEmitter()
    
    data_service = Data(influx=dummy_influx, emitter=dummy_emitter, exchanges=["coinbase"], force_public=True)
    await data_service.load_exchanges()
    app_instance.state.data_service = data_service # Store on app.state
    logger.info("Lifespan: Startup - Data service initialized and exchanges loaded.")
    
    yield  # Application is now live and serving requests
    
    # Code to run on shutdown
    logger.info("Lifespan: Shutdown - Closing Data service connections...")
    if hasattr(app_instance.state, 'data_service') and app_instance.state.data_service:
        await app_instance.state.data_service.close_all_exchanges()
        logger.info("Lifespan: Shutdown - Data service connections closed.")
    else:
        logger.info("Lifespan: Shutdown - No Data service found on app.state to close.")

# --- FastAPI Application ---
app = FastAPI(
    title="Trade Suite MCP Server",
    description="Server to interact with Trade Suite data functionalities for AI agents.",
    version="0.1.0",
    lifespan=lifespan_manager # Use the new lifespan manager
)

# --- Dependency Injection for Data Class ---
async def get_data_service(request: Request) -> Data:
    # Retrieve the shared Data instance from app.state
    # This ensures all requests use the same Data instance.
    if not hasattr(request.app.state, 'data_service') or not request.app.state.data_service:
        # This should ideally not happen if startup event ran correctly
        logger.error("Data service not found in app.state during request. This indicates an issue with application startup or lifespan manager.")
        raise HTTPException(status_code=500, detail="Data service is not available.")
    return request.app.state.data_service

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
                        
                        # Convert DataFrame to list of CandleData, handling potential NaN for string fields
                        candle_data_list = []
                        for row in df.to_dict(orient='records'):
                            # Clean potentially NaN string fields by converting them to None
                            if pd.isna(row.get('exchange')):
                                row['exchange'] = None
                            if pd.isna(row.get('symbol')):
                                row['symbol'] = None
                            if pd.isna(row.get('timeframe')):
                                row['timeframe'] = None
                            candle_data_list.append(CandleData(**row))
                        formatted_data[exchange][key] = candle_data_list
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
    import sys
    import asyncio

    if sys.platform.startswith('win'):
        # On Windows, ensure the correct event loop policy is set
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    # You would typically run this with: uvicorn mcp_server:app --reload
    # The host and port can be configured as needed.
    uvicorn.run(app, host="0.0.0.0", port=8000, log_level="info") 