"""
options.py — Options chain fetching, filtering, selection, and Black-Scholes fallback.
"""

import time
import math
import logging
from datetime import datetime, timedelta

import yfinance as yf
from scipy.stats import norm

from quotes import get_cached

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Cache TTL
# ---------------------------------------------------------------------------
CHAIN_TTL = 300  # 5 minutes

# ---------------------------------------------------------------------------
# OTM offsets by protection level
# ---------------------------------------------------------------------------
OTM_OFFSETS = {
    "light": 0.10,     # 10% OTM
    "moderate": 0.05,   # 5% OTM
    "full": 0.00,       # ATM
}

HEDGE_PCTS = {
    "light": 0.25,
    "moderate": 0.50,
    "full": 1.00,
}

# ---------------------------------------------------------------------------
# Black-Scholes helpers (put pricing + delta)
# ---------------------------------------------------------------------------

def bs_put_price(S: float, K: float, T: float, r: float, sigma: float) -> float:
    """European put price via Black-Scholes."""
    if T <= 0 or sigma <= 0:
        return max(K - S, 0.0)
    d1 = (math.log(S / K) + (r + 0.5 * sigma**2) * T) / (sigma * math.sqrt(T))
    d2 = d1 - sigma * math.sqrt(T)
    return K * math.exp(-r * T) * norm.cdf(-d2) - S * norm.cdf(-d1)


def bs_put_delta(S: float, K: float, T: float, r: float, sigma: float) -> float:
    """Put delta via Black-Scholes (negative value)."""
    if T <= 0 or sigma <= 0:
        return -1.0 if S < K else 0.0
    d1 = (math.log(S / K) + (r + 0.5 * sigma**2) * T) / (sigma * math.sqrt(T))
    return norm.cdf(d1) - 1.0


# ---------------------------------------------------------------------------
# Chain fetching + selection
# ---------------------------------------------------------------------------

def fetch_chain(ticker: str) -> dict:
    """Fetch all put-options expiries from yfinance for *ticker*.

    Returns dict keyed by expiry date string -> DataFrame of puts.
    """

    def _fetch():
        tk = yf.Ticker(ticker.upper())
        expiries = tk.options  # tuple of date strings
        chains = {}
        for exp in expiries:
            try:
                chain = tk.option_chain(exp)
                chains[exp] = chain.puts
            except Exception as e:
                logger.warning("Could not fetch chain %s/%s: %s", ticker, exp, e)
        return chains

    return get_cached(f"chain:{ticker.upper()}", CHAIN_TTL, _fetch)


def select_put(
    ticker: str,
    current_price: float,
    hedge_level: str,
    risk_free_rate: float = 0.05,
) -> dict:
    """Select the best protective put for a position.

    Returns dict with: strike, expiry, mid_price, delta, iv, is_fallback
    """
    otm_offset = OTM_OFFSETS[hedge_level]
    target_strike = current_price * (1.0 - otm_offset)

    now = datetime.now()
    min_dte = 21
    max_dte = 90
    target_dte = 45

    chains = fetch_chain(ticker)

    best = None
    best_score = float("inf")

    for exp_str, puts in chains.items():
        exp_date = datetime.strptime(exp_str, "%Y-%m-%d")
        dte = (exp_date - now).days

        if dte < min_dte or dte > max_dte:
            continue

        # Filter for liquidity
        liquid = puts[puts["openInterest"] > 100].copy() if "openInterest" in puts.columns else puts.copy()
        if liquid.empty:
            continue

        # Find closest strike to target
        liquid = liquid.copy()
        liquid["strike_dist"] = (liquid["strike"] - target_strike).abs()
        closest = liquid.sort_values("strike_dist").iloc[0]

        # Compute mid price
        bid = closest.get("bid", 0) or 0
        ask = closest.get("ask", 0) or 0
        mid = (bid + ask) / 2.0

        if mid <= 0.01:
            continue

        # Score: prefer closest to 45 DTE, then closest strike
        dte_score = abs(dte - target_dte)
        strike_score = abs(closest["strike"] - target_strike) / current_price
        score = dte_score + strike_score * 100

        # Get IV from chain if available
        iv = closest.get("impliedVolatility", None)
        if iv is None or iv <= 0:
            iv = 0.30  # default fallback

        T = dte / 365.0
        delta = bs_put_delta(current_price, closest["strike"], T, risk_free_rate, iv)

        candidate = {
            "strike": round(float(closest["strike"]), 2),
            "expiry": exp_str,
            "dte": dte,
            "mid_price": round(mid, 2),
            "delta": round(delta, 4),
            "iv": round(iv, 4),
            "open_interest": int(closest.get("openInterest", 0)),
            "is_fallback": False,
        }

        if score < best_score:
            best_score = score
            best = candidate

    # Fallback to Black-Scholes if nothing found
    if best is None:
        logger.warning("No liquid options for %s — using Black-Scholes fallback", ticker)
        T = target_dte / 365.0
        iv = _estimate_iv(ticker)
        strike = round(target_strike, 2)
        mid = round(bs_put_price(current_price, strike, T, risk_free_rate, iv), 2)
        delta = round(bs_put_delta(current_price, strike, T, risk_free_rate, iv), 4)
        best = {
            "strike": strike,
            "expiry": (now + timedelta(days=target_dte)).strftime("%Y-%m-%d"),
            "dte": target_dte,
            "mid_price": mid,
            "delta": delta,
            "iv": round(iv, 4),
            "open_interest": 0,
            "is_fallback": True,
        }

    return best


def _estimate_iv(ticker: str) -> float:
    """Estimate IV from yfinance history (annualized 30-day realized vol)."""
    try:
        tk = yf.Ticker(ticker.upper())
        hist = tk.history(period="3mo")
        if hist.empty or len(hist) < 10:
            return 0.30
        returns = hist["Close"].pct_change().dropna()
        vol = float(returns.std() * math.sqrt(252))
        return max(vol, 0.10)
    except Exception:
        return 0.30


# ---------------------------------------------------------------------------
# Standalone test
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    import json, sys

    tickers = sys.argv[1:] or ["AAPL"]
    for t in tickers:
        print(f"\n=== {t} ===")
        for level in ("light", "moderate", "full"):
            from quotes import fetch_quote

            q = fetch_quote(t)
            result = select_put(t, q["price"], level)
            print(f"\n  {level.upper()}:")
            print(json.dumps(result, indent=4))
