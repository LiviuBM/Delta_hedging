"""
hedge.py - Portfolio-level hedge recommendation engine.
"""

import logging
from datetime import date, timedelta

from options import HEDGE_PCTS, select_put
from quotes import fetch_quote
from scenarios import build_scenarios

logger = logging.getLogger(__name__)

OBJECTIVE_LABELS = {
    "reduce_downside": "Reduce 1-3 month downside",
    "protect_gains": "Protect recent gains",
    "crash_hedge": "Crash hedge only",
    "partial_delta": "Partial delta hedge",
}

EXPERIENCE_WARNINGS = {
    "beginner": "This recommendation uses listed put options. Use limit orders only and review the OCC disclosure document before trading.",
    "intermediate": "Monitor the hedge after large moves or if the underlying mix changes materially.",
    "advanced": "Greeks and event risk can move quickly; treat the output as a review list, not a standing order ticket.",
}


def calculate_hedge(
    ticker: str,
    shares: int,
    price: float,
    hedge_level: str,
    target_dte: int = 45,
) -> dict:
    """Calculate hedge details for a single position."""
    hedge_pct = HEDGE_PCTS[hedge_level]
    put = select_put(ticker, price, hedge_level, target_dte=target_dte)

    put_delta = abs(put["delta"])
    if put_delta < 0.001:
        put_delta = 0.001

    portfolio_delta = shares * hedge_pct
    contracts = max(1, round(portfolio_delta / (100 * put_delta)))
    cost = round(contracts * put["mid_price"] * 100, 2)
    position_value = round(shares * price, 2)
    coverage_notional = round(contracts * 100 * put_delta * price, 2)
    breakeven = round(put["strike"] - put["mid_price"], 2)
    cost_pct = round((cost / position_value) * 100, 2) if position_value > 0 else 0.0

    return {
        "ticker": ticker.upper(),
        "underlying": ticker.upper(),
        "strategy_scope": "single",
        "shares": shares,
        "price": round(price, 2),
        "underlying_price": round(price, 2),
        "position_value": position_value,
        "contracts": contracts,
        "strike": put["strike"],
        "expiry": put["expiry"],
        "dte": put["dte"],
        "mid_price": put["mid_price"],
        "bid": put["bid"],
        "ask": put["ask"],
        "spread_pct": put["spread_pct"],
        "cost": cost,
        "breakeven": breakeven,
        "cost_pct": cost_pct,
        "iv": put["iv"],
        "delta": put["delta"],
        "open_interest": put["open_interest"],
        "volume": put["volume"],
        "coverage_notional": coverage_notional,
        "is_fallback": put["is_fallback"],
    }


def calculate_portfolio_hedge(
    positions: list[dict],
    hedge_level: str,
    target_dte: int = 45,
) -> dict:
    """Build a single-name protective-put candidate for the full portfolio."""
    legs = []
    total_value = 0.0
    total_cost = 0.0
    total_coverage = 0.0
    any_fallback = False
    errors = []

    for pos in positions:
        try:
            leg = calculate_hedge(
                ticker=pos["ticker"],
                shares=pos["shares"],
                price=pos["price"],
                hedge_level=hedge_level,
                target_dte=target_dte,
            )
            legs.append(leg)
            total_value += leg["position_value"]
            total_cost += leg["cost"]
            total_coverage += leg["coverage_notional"]
            any_fallback = any_fallback or leg["is_fallback"]
        except Exception as exc:
            logger.error("Hedge calc failed for %s: %s", pos["ticker"], exc)
            errors.append(f"{pos['ticker']}: {exc}")

    total_cost_pct = round((total_cost / total_value) * 100, 2) if total_value > 0 else 0.0
    delta_coverage_pct = round((total_coverage / total_value) * 100, 1) if total_value > 0 else 0.0
    average_spread = round(sum(leg["spread_pct"] for leg in legs) / len(legs), 2) if legs else 0.0

    return {
        "strategy": "single_name",
        "strategy_label": "Single-name protective puts",
        "strategy_scope": "single",
        "positions": legs,
        "contracts": [
            {
                "underlying": leg["underlying"],
                "underlying_price": leg["underlying_price"],
                "strategy_scope": "single",
                "contracts": leg["contracts"],
                "strike": leg["strike"],
                "expiry": leg["expiry"],
                "cost": leg["cost"],
                "delta": leg["delta"],
                "dte": leg["dte"],
                "open_interest": leg["open_interest"],
                "spread_pct": leg["spread_pct"],
                "iv": leg["iv"],
                "ticker": leg["ticker"],
            }
            for leg in legs
        ],
        "total_value": round(total_value, 2),
        "total_cost": round(total_cost, 2),
        "total_cost_pct": total_cost_pct,
        "coverage_notional": round(total_coverage, 2),
        "market_delta_coverage_pct": delta_coverage_pct,
        "average_spread_pct": average_spread,
        "net_protected": round(total_value - total_cost, 2),
        "protection_threshold": _weighted_threshold(legs),
        "any_fallback": any_fallback,
        "errors": errors,
    }


def calculate_index_hedge(
    positions: list[dict],
    hedge_level: str,
    portfolio_beta: float | None,
    target_dte: int = 45,
    index_ticker: str = "SPY",
) -> dict:
    """Build an index-put hedge candidate based on beta-adjusted market exposure."""
    total_value = round(sum(pos["shares"] * pos["price"] for pos in positions), 2)
    if total_value <= 0:
        raise ValueError("Portfolio value must be positive")

    beta = portfolio_beta if portfolio_beta and portfolio_beta > 0 else 1.0
    hedge_pct = HEDGE_PCTS[hedge_level]
    quote = fetch_quote(index_ticker)
    price = quote["price"]
    put = select_put(index_ticker, price, hedge_level, target_dte=target_dte)

    delta = abs(put["delta"])
    if delta < 0.001:
        delta = 0.001

    market_exposure = total_value * beta
    target_market_exposure = market_exposure * hedge_pct
    contracts = max(1, round(target_market_exposure / (100 * price * delta)))
    total_cost = round(contracts * put["mid_price"] * 100, 2)
    coverage_notional = round(contracts * 100 * delta * price, 2)
    total_cost_pct = round((total_cost / total_value) * 100, 2)
    market_delta_coverage_pct = round((coverage_notional / market_exposure) * 100, 1) if market_exposure > 0 else 0.0

    contract = {
        "ticker": index_ticker,
        "underlying": index_ticker,
        "underlying_price": price,
        "strategy_scope": "index",
        "contracts": contracts,
        "strike": put["strike"],
        "expiry": put["expiry"],
        "cost": total_cost,
        "mid_price": put["mid_price"],
        "delta": put["delta"],
        "dte": put["dte"],
        "open_interest": put["open_interest"],
        "volume": put["volume"],
        "spread_pct": put["spread_pct"],
        "iv": put["iv"],
        "coverage_notional": coverage_notional,
        "is_fallback": put["is_fallback"],
    }

    return {
        "strategy": "index_put",
        "strategy_label": f"{index_ticker} index hedge",
        "strategy_scope": "index",
        "positions": [],
        "contracts": [contract],
        "total_value": total_value,
        "total_cost": total_cost,
        "total_cost_pct": total_cost_pct,
        "coverage_notional": coverage_notional,
        "market_exposure": round(market_exposure, 2),
        "market_delta_coverage_pct": market_delta_coverage_pct,
        "average_spread_pct": put["spread_pct"],
        "net_protected": round(total_value - total_cost, 2),
        "protection_threshold": round((1 - put["strike"] / price) * 100, 1),
        "any_fallback": put["is_fallback"],
        "errors": [],
    }


def build_delta_advice(
    positions: list[dict],
    hedge_level: str,
    profile: dict,
    portfolio_beta: float | None = None,
) -> dict:
    """Compare hedge candidates and return one retail-facing recommendation."""
    target_dte = max(21, min(int(profile.get("horizon_days", 45) or 45), 90))
    budget = float(profile.get("max_budget", 0) or 0)
    objective = profile.get("objective", "reduce_downside")
    experience = profile.get("experience", "beginner")
    target_pct = HEDGE_PCTS[hedge_level] * 100

    candidates = [calculate_portfolio_hedge(positions, hedge_level, target_dte=target_dte)]
    if len(positions) > 1:
        try:
            candidates.append(
                calculate_index_hedge(
                    positions,
                    hedge_level,
                    portfolio_beta=portfolio_beta,
                    target_dte=target_dte,
                )
            )
        except Exception as exc:
            logger.warning("Index hedge unavailable: %s", exc)

    scored = []
    for candidate in candidates:
        score = _score_candidate(candidate, objective, budget, experience, target_pct)
        candidate["score"] = score
        candidate["rationale"] = _build_rationale(candidate, objective, budget)
        scored.append(candidate)

    recommendation = min(scored, key=lambda item: item["score"])
    review_date = date.today() + timedelta(days=min(14, target_dte // 2))
    recommendation["objective_label"] = OBJECTIVE_LABELS.get(objective, OBJECTIVE_LABELS["reduce_downside"])
    recommendation["experience_warning"] = EXPERIENCE_WARNINGS.get(experience, EXPERIENCE_WARNINGS["beginner"])
    recommendation["review_date"] = review_date.isoformat()
    recommendation["review_window_days"] = min(14, target_dte // 2)
    recommendation["rebalance_triggers"] = [
        "Re-check if the portfolio moves by 5% or more.",
        "Review if 14 days pass without a refresh.",
        "Roll or replace if time to expiry falls below 21 days.",
    ]
    recommendation["suitability_notes"] = _build_suitability_notes(recommendation, experience, budget)
    recommendation["scenarios"] = build_scenarios(positions, recommendation, portfolio_beta)
    recommendation["alternatives"] = [
        {
            "strategy": candidate["strategy_label"],
            "cost_pct": candidate["total_cost_pct"],
            "coverage_pct": candidate["market_delta_coverage_pct"],
            "score": round(candidate["score"], 1),
        }
        for candidate in sorted(scored, key=lambda item: item["score"])
        if candidate["strategy"] != recommendation["strategy"]
    ]
    recommendation["target_dte"] = target_dte
    recommendation["target_delta_reduction_pct"] = round(target_pct, 0)
    recommendation["residual_delta_pct"] = round(max(0.0, 100.0 - recommendation["market_delta_coverage_pct"]), 1)
    return recommendation


def _weighted_threshold(legs: list[dict]) -> float:
    if not legs:
        return 0.0
    total_value = sum(leg["position_value"] for leg in legs)
    if total_value <= 0:
        return 0.0
    weighted_otm = sum((1 - leg["strike"] / leg["price"]) * leg["position_value"] for leg in legs) / total_value
    return round(weighted_otm * 100, 1)


def _score_candidate(candidate: dict, objective: str, budget: float, experience: str, target_pct: float) -> float:
    score = candidate["total_cost_pct"] * 4
    score += abs(candidate["market_delta_coverage_pct"] - target_pct) * 0.7
    score += candidate.get("average_spread_pct", 0.0) * 0.6

    if budget and candidate["total_cost"] > budget:
        score += 35 + (candidate["total_cost"] - budget) / max(budget, 1) * 20

    if candidate.get("any_fallback"):
        score += 20

    if objective == "crash_hedge":
        if candidate["strategy"] == "index_put":
            score -= 8
        score += candidate["total_cost_pct"] * 2
    elif objective == "protect_gains":
        if candidate["strategy"] == "single_name":
            score -= 6
        score -= candidate["market_delta_coverage_pct"] * 0.08
    elif objective == "partial_delta":
        score += candidate["total_cost_pct"] * 4
    else:
        score -= candidate["market_delta_coverage_pct"] * 0.04

    if experience == "beginner" and candidate["average_spread_pct"] > 12:
        score += 8

    return round(score, 3)


def _build_rationale(candidate: dict, objective: str, budget: float) -> str:
    base = []
    if candidate["strategy"] == "index_put":
        base.append("This uses one liquid market hedge instead of several single-stock contracts")
    else:
        base.append("This keeps the hedge tied directly to each stock in the portfolio")

    base.append(
        f"Estimated market delta coverage is about {candidate['market_delta_coverage_pct']:.0f}%"
    )
    base.append(f"estimated premium cost is {candidate['total_cost_pct']:.2f}% of portfolio value")

    if budget:
        if candidate["total_cost"] <= budget:
            base.append("and it stays within the budget you entered")
        else:
            base.append("but it exceeds the current budget cap")

    if objective == "crash_hedge":
        base.append("which fits a lower-cost drawdown hedge objective")
    elif objective == "protect_gains":
        base.append("which fits a tighter protection objective")
    else:
        base.append("which balances cost, coverage, and liquidity for a first-pass hedge")

    return ". ".join(base) + "."


def _build_suitability_notes(candidate: dict, experience: str, budget: float) -> list[str]:
    notes = []
    if candidate["average_spread_pct"] > 10:
        notes.append("Some selected options have wider bid-ask spreads than ideal. Use limit orders and verify liquidity before acting.")
    if candidate.get("any_fallback"):
        notes.append("At least one contract used fallback pricing because a liquid chain was not found. Treat those estimates with extra caution.")
    if budget and candidate["total_cost"] > budget:
        notes.append("The recommendation is above the budget entered, so the user should either widen strikes, lower target coverage, or shorten the hedge horizon.")
    if experience == "beginner":
        notes.append("This output is best used as an advisory checklist. A beginner should avoid near-expiry options and confirm brokerage approval before trading.")
    return notes
