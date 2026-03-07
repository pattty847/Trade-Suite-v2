import ccxt.async_support as ccxt
import logging
from typing import List


async def get_top_x_symbols_by_volume(
    exchange: ccxt.Exchange,
    quote_currency: str = "USD",
    count: int = 200,
    volume_field: str = "volume_24h",
) -> List[str]:
    """Return the most active symbols for the requested quote currency."""
    try:
        logging.info("Fetching markets from %s", exchange.id)
        markets = await exchange.fetch_markets()
    except Exception as exc:
        logging.error("Error fetching markets from %s: %s", exchange.id, exc)
        return []

    valid_markets = []
    for market in markets:
        if market.get("quote", "").upper() != quote_currency.upper() or not market.get("active", True):
            continue

        volume = None
        if market.get("info") and market["info"].get(volume_field):
            try:
                volume = float(market["info"][volume_field])
            except (TypeError, ValueError):
                logging.warning(
                    "Could not parse volume field %r=%r for %s on %s",
                    volume_field,
                    market["info"][volume_field],
                    market.get("symbol"),
                    exchange.id,
                )
        elif market.get("quoteVolume") is not None:
            try:
                volume = float(market["quoteVolume"])
            except (TypeError, ValueError):
                logging.warning(
                    "Could not parse quoteVolume=%r for %s on %s",
                    market["quoteVolume"],
                    market.get("symbol"),
                    exchange.id,
                )
        elif market.get("baseVolume") is not None and market.get("last") is not None:
            try:
                volume = float(market["baseVolume"]) * float(market["last"])
            except (TypeError, ValueError):
                logging.warning(
                    "Could not estimate volume from baseVolume=%r and last=%r for %s on %s",
                    market["baseVolume"],
                    market["last"],
                    market.get("symbol"),
                    exchange.id,
                )

        if volume is not None and volume > 0:
            valid_markets.append({"symbol": market["symbol"], "effectiveVolume": volume})

    if not valid_markets:
        logging.warning(
            "No markets found on %s for quote currency %s with valid volume data.",
            exchange.id,
            quote_currency,
        )
        return []

    valid_markets.sort(key=lambda item: item["effectiveVolume"], reverse=True)
    return [market["symbol"] for market in valid_markets[:count]]
