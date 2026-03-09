# Delta Hedging

This repository contains a retail-focused portfolio protection project built around delta-based hedge advisory workflows.

## Repo Layout

- `portfolio-shield/`
  - Active FastAPI app.
  - Recommends protective option hedges for a stock portfolio.
  - Compares single-name hedges with an index hedge when appropriate.
  - Includes scenario analysis, review triggers, and lightweight SQLite persistence.

- `portfolio-shield-legacy/`
  - Preserved copy of the original prototype.
  - Kept for reference while the newer advisory flow evolves.

## Active App Highlights

The current app in `portfolio-shield/`:

1. Accepts stock positions plus advisory settings such as objective, horizon, budget, and user experience level.
2. Fetches quotes, options chains, and supporting portfolio analytics.
3. Builds a hedge recommendation using delta-based sizing logic.
4. Shows recommended contracts, scenarios, alternatives considered, and review triggers.
5. Stores generated recommendations locally for traceability.

## Beginner Guide

For a full beginner-friendly explanation of what the app does, how delta-based hedging is applied, and how the recommendation engine compares strategies, read [BEGINNER_GUIDE.md](./BEGINNER_GUIDE.md).

## Running The App

```bash
cd portfolio-shield
pip install -r requirements.txt
python main.py
```

Open `http://127.0.0.1:8000`.

## Notes

- This is an advisory app, not a trading platform.
- It is still an MVP/prototype and should not be treated as guaranteed protection.
- Market-data quality and hedge realism should be improved further before real user rollout.
