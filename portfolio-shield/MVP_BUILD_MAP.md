# MVP Build Map

This document maps the upgraded hedge advisory flow onto the current codebase.

## Files

- `main.py`
  - Parses the richer form.
  - Fetches portfolio analytics.
  - Calls the advisory engine.
  - Persists each recommendation.

- `hedge.py`
  - Builds hedge candidates.
  - Compares single-name and index strategies.
  - Produces the retail-facing recommendation payload.

- `options.py`
  - Filters option chains using liquidity and spread checks.
  - Selects the contract used by the candidate builder.

- `scenarios.py`
  - Builds directional scenario rows using shocked intrinsic values.

- `storage.py`
  - Stores generated recommendations in SQLite.

- `templates/index.html`
  - Adds objective, experience, horizon, and budget inputs.

- `templates/results.html`
  - Shows one chosen recommendation, scenarios, alternatives, and review triggers.

## Next Suggested Steps

1. Add a recommendation history page backed by `portfolio_shield.db`.
2. Add richer portfolio-level candidate generation, including mixed hedges.
3. Add stricter liquidity controls, earnings checks, and event-aware warnings.
4. Replace prototype market data before showing this to real users.
5. Add tests around candidate scoring and scenario generation.
