"""
quotes.py — yfinance price fetching with 60-second in-memory cache.
"""

import time
import logging
import yfinance as yf

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Generic TTL cache
# ---------------------------------------------------------------------------
_cache: dict[str, dict] = {}


def get_cached(key: str, ttl: int, fetch_fn):
    """Return cached value if fresh, otherwise call fetch_fn and store."""
    now = time.time()
    entry = _cache.get(key)
    if entry and now - entry["ts"] < ttl:
        return entry["value"]
    value = fetch_fn()
    _cache[key] = {"value": value, "ts": now}
    return value


# ---------------------------------------------------------------------------
# Quote fetching
# ---------------------------------------------------------------------------
QUOTE_TTL = 60  # seconds


def fetch_quote(ticker: str) -> dict:
    """Fetch a live quote for *ticker* via yfinance.

    Returns dict with: ticker, price, change, change_pct, last_updated
    Raises ValueError for invalid / unknown tickers.
    """

    def _fetch():
        tk = yf.Ticker(ticker.upper())
        info = tk.fast_info
        price = getattr(info, "last_price", None)
        prev = getattr(info, "previous_close", None)

        if price is None:
            raise ValueError(f"No price data for ticker '{ticker}'")

        change = round(price - prev, 2) if prev else 0.0
        change_pct = round((change / prev) * 100, 2) if prev else 0.0

        return {
            "ticker": ticker.upper(),
            "price": round(price, 2),
            "change": change,
            "change_pct": change_pct,
            "last_updated": time.strftime("%H:%M ET"),
        }

    try:
        return get_cached(f"quote:{ticker.upper()}", QUOTE_TTL, _fetch)
    except Exception as e:
        logger.error("Quote fetch failed for %s: %s", ticker, e)
        raise ValueError(f"Could not fetch quote for '{ticker}': {e}")


# ---------------------------------------------------------------------------
# Standalone test
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    import json, sys

    tickers = sys.argv[1:] or ["AAPL", "MSFT", "TSLA"]
    for t in tickers:
        try:
            q = fetch_quote(t)
            print(json.dumps(q, indent=2))
        except ValueError as exc:
            print(f"ERROR: {exc}")
