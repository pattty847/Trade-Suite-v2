from datetime import datetime, timedelta


def timeframe_to_seconds(timeframe_str):
    # Extracts the numerical value and unit from the timeframe string
    numeric_part = int(timeframe_str[:-1])
    unit = timeframe_str[-1]

    if unit == "m":
        return numeric_part * 60
    elif unit == "h":
        return numeric_part * 60 * 60
    elif unit == "d":
        return numeric_part * 60 * 60 * 24
    else:
        raise ValueError("Invalid timeframe format")


def calculate_since(exchange, timeframe_str, num_candles):
    # Convert the timeframe string to timedelta
    timeframe_duration_in_seconds = exchange.parse_timeframe(timeframe_str)
    timeframe_duration = timedelta(seconds=timeframe_duration_in_seconds)

    # Calculate the total duration
    total_duration = timeframe_duration * num_candles

    # Current time
    now = datetime.utcnow()

    # Calculate the 'since' time
    since_time = now - total_duration

    # Convert 'since' time to Unix timestamp in milliseconds
    since_iso8601 = since_time.isoformat() + "Z"
    return since_iso8601
