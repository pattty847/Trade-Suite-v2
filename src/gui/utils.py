def str_timeframe_to_minutes(timeframe_str):
    # Extracts the numerical value and unit from the timeframe string
    numeric_part = int(timeframe_str[:-1])
    unit = timeframe_str[-1]

    if unit == 'm':
        return numeric_part * 60
    elif unit == 'h':
        return numeric_part * 60 * 60
    elif unit == 'd':
        return numeric_part * 60 * 60 * 24
    else:
        raise ValueError("Invalid timeframe format")