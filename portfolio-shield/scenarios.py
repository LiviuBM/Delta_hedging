"""
scenarios.py - Downside and upside scenario snapshots for hedge recommendations.
"""

SCENARIO_SHOCKS = (-0.20, -0.10, -0.05, 0.05)


def build_scenarios(
    positions: list[dict],
    recommendation: dict,
    portfolio_beta: float | None = None,
) -> list[dict]:
    """Build simple scenario rows using shocked intrinsic values."""
    del portfolio_beta
    base_value = recommendation.get("total_value", 0.0)
    total_cost = recommendation.get("total_cost", 0.0)
    contracts = recommendation.get("contracts", [])

    rows = []
    for shock in SCENARIO_SHOCKS:
        scenario_prices = {
            pos["ticker"]: max(pos["price"] * (1.0 + shock), 0.01)
            for pos in positions
        }
        unhedged_value = round(
            sum(pos["shares"] * scenario_prices[pos["ticker"]] for pos in positions),
            2,
        )

        option_intrinsic = 0.0
        for leg in contracts:
            underlying = leg["underlying"]
            shocked_price = scenario_prices.get(
                underlying,
                max(leg.get("underlying_price", 0.0) * (1.0 + shock), 0.01),
            )
            option_intrinsic += max(leg["strike"] - shocked_price, 0.0) * leg["contracts"] * 100

        hedged_value = round(unhedged_value + option_intrinsic - total_cost, 2)
        rows.append(
            {
                "label": f"{shock * 100:+.0f}%",
                "portfolio_move_pct": round(shock * 100, 1),
                "unhedged_value": unhedged_value,
                "hedged_value": hedged_value,
                "hedge_lift": round(hedged_value - (unhedged_value - total_cost), 2),
                "net_change_unhedged": round(unhedged_value - base_value, 2),
                "net_change_hedged": round(hedged_value - base_value, 2),
            }
        )

    return rows
