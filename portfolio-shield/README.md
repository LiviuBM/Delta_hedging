# Portfolio Shield

Portfolio Shield is a retail-facing hedge advisory app for long stock portfolios. It analyzes positions, compares hedge approaches, and recommends option contracts to review based on protection target, budget, and horizon.

## Current Structure

- `portfolio-shield/` - active advisory app
- `portfolio-shield-legacy/` - preserved copy of the original prototype

## What The Active App Does

1. Accepts portfolio positions and advisory settings.
2. Fetches quotes, history, and option chains.
3. Compares single-name put hedges with an index hedge when possible.
4. Returns a recommended hedge, scenario table, review triggers, and suitability notes.
5. Stores each recommendation in a local SQLite file for traceability.

## Beginner Guide

A full beginner-friendly explanation is available in the repo root at [BEGINNER_GUIDE.md](../BEGINNER_GUIDE.md).

## Run

```bash
cd portfolio-shield
pip install -r requirements.txt
python main.py
```

Then open [http://127.0.0.1:8000](http://127.0.0.1:8000).

## Important Note

This is still an advisory prototype. It does not place trades, manage orders, or guarantee protection.



