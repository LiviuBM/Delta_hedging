"""
hedge.py — Delta hedge calculation engine.
"""

import logging
from options import select_put, HEDGE_PCTS

logger = logging.getLogger(__name__)


def calculate_hedge(
    ticker: str,
    shares: int,
    price: float,
    hedge_level: str,
) -> dict:
    """Calculate hedge strategy for a single position.

    Returns dict with: ticker, shares, price, position_value, contracts,
    strike, expiry, cost, breakeven, cost_pct, iv, delta, is_fallback
    """
    hedge_pct = HEDGE_PCTS[hedge_level]

    # Select best put option
    put = select_put(ticker, price, hedge_level)

    put_delta = abs(put["delta"])
    if put_delta < 0.001:
        put_delta = 0.001  # avoid division by zero

    # Core hedge math
    portfolio_delta = shares * hedge_pct
    contracts = max(1, round(portfolio_delta / (100 * put_delta)))
    cost = round(contracts * put["mid_price"] * 100, 2)
    position_value = round(shares * price, 2)

    if contracts > 0:
        breakeven = round(put["strike"] - (cost / (contracts * 100)), 2)
    else:
        breakeven = put["strike"]

    cost_pct = round((cost / position_value) * 100, 2) if position_value > 0 else 0.0

    return {
        "ticker": ticker.upper(),
        "shares": shares,
        "price": price,
        "position_value": position_value,
        "contracts": contracts,
        "strike": put["strike"],
        "expiry": put["expiry"],
        "dte": put["dte"],
        "mid_price": put["mid_price"],
        "cost": cost,
        "breakeven": breakeven,
        "cost_pct": cost_pct,
        "iv": put["iv"],
        "delta": put["delta"],
        "open_interest": put["open_interest"],
        "is_fallback": put["is_fallback"],
    }


def calculate_portfolio_hedge(
    positions: list[dict],
    hedge_level: str,
) -> dict:
    """Calculate hedge for an entire portfolio.

    positions: list of {"ticker": str, "shares": int, "price": float}
    hedge_level: "light" | "moderate" | "full"

    Returns dict with per-position results and portfolio summary.
    """
    results = []
    total_value = 0.0
    total_cost = 0.0
    any_fallback = False

    for pos in positions:
        try:
            hedge = calculate_hedge(
                ticker=pos["ticker"],
                shares=pos["shares"],
                price=pos["price"],
                hedge_level=hedge_level,
            )
            results.append(hedge)
            total_value += hedge["position_value"]
            total_cost += hedge["cost"]
            if hedge["is_fallback"]:
                any_fallback = True
        except Exception as e:
            logger.error("Hedge calc failed for %s: %s", pos["ticker"], e)
            results.append({
                "ticker": pos["ticker"].upper(),
                "shares": pos["shares"],
                "price": pos["price"],
                "position_value": round(pos["shares"] * pos["price"], 2),
                "error": str(e),
            })

    total_cost_pct = round((total_cost / total_value) * 100, 2) if total_value > 0 else 0.0
    net_protected = round(total_value - total_cost, 2)
    hedge_pct = HEDGE_PCTS[hedge_level]

    # Weighted average protection threshold
    if results and not all("error" in r for r in results):
        valid = [r for r in results if "error" not in r]
        if valid:
            weighted_otm = sum(
                (1 - r["strike"] / r["price"]) * r["position_value"]
                for r in valid
            ) / sum(r["position_value"] for r in valid)
            protection_threshold = round(weighted_otm * 100, 1)
        else:
            protection_threshold = 0.0
    else:
        protection_threshold = 0.0

    return {
        "positions": results,
        "hedge_level": hedge_level,
        "hedge_pct": hedge_pct,
        "total_value": round(total_value, 2),
        "total_cost": round(total_cost, 2),
        "total_cost_pct": total_cost_pct,
        "net_protected": net_protected,
        "protection_threshold": protection_threshold,
        "any_fallback": any_fallback,
    }


# ---------------------------------------------------------------------------
# Standalone test
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    import json

    test_positions = [
        {"ticker": "AAPL", "shares": 100, "price": 0},  # price=0 means fetch live
        {"ticker": "MSFT", "shares": 50, "price": 0},
    ]

    # Fill in live prices
    from quotes import fetch_quote

    for p in test_positions:
        if p["price"] == 0:
            q = fetch_quote(p["ticker"])
            p["price"] = q["price"]
            print(f"{p['ticker']}: ${q['price']}")

    for level in ("light", "moderate", "full"):
        print(f"\n{'='*60}")
        print(f"  HEDGE LEVEL: {level.upper()}")
        print(f"{'='*60}")
        result = calculate_portfolio_hedge(test_positions, level)
        print(json.dumps(result, indent=2))
