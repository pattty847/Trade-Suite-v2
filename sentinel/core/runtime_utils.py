from __future__ import annotations

from datetime import datetime, timedelta
import logging


def timeframe_to_seconds(timeframe_str: str) -> int:
    numeric_part = int(timeframe_str[:-1])
    unit = timeframe_str[-1]

    if unit == "m":
        return numeric_part * 60
    if unit == "h":
        return numeric_part * 60 * 60
    if unit == "d":
        return numeric_part * 60 * 60 * 24
    raise ValueError(f"Invalid timeframe format: {timeframe_str}")


def calculate_since(exchange, timeframe_str: str, num_candles: int) -> str:
    timeframe_duration_in_seconds = exchange.parse_timeframe(timeframe_str)
    timeframe_duration = timedelta(seconds=timeframe_duration_in_seconds)
    total_duration = timeframe_duration * num_candles
    since_time = datetime.utcnow() - total_duration
    return since_time.isoformat() + "Z"


def create_timed_popup(message: str, time: int, label: str = "Notice", additional_ui_callback=None) -> None:
    """Non-GUI fallback used by non-DPG runtimes."""
    logging.warning("%s: %s (for %ss)", label, message, time)
