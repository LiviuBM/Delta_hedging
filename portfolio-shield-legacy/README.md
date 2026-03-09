# Portfolio Shield

Delta-hedging calculator that recommends protective put options using live market data.

## Quick Start

```bash
cd portfolio-shield
pip install -r requirements.txt
python main.py
```

Open http://127.0.0.1:8000 in your browser.

## How It Works

1. Enter your stock positions (tickers + share counts)
2. Choose a protection level: Light (25%), Moderate (50%), or Full (100%)
3. Click "Calculate Hedge" — the app fetches live prices and options chains via yfinance
4. View recommended put options to buy, total cost, breakeven prices, and next steps

## Architecture

| File | Purpose |
|------|---------|
| `main.py` | FastAPI routes and app startup |
| `quotes.py` | Live price fetching with 60s TTL cache |
| `options.py` | Options chain filtering, selection, Black-Scholes fallback |
| `hedge.py` | Delta hedge calculation engine |
| `templates/index.html` | Portfolio input form |
| `templates/results.html` | Strategy results display |

## API

- `GET /` — Portfolio input form
- `POST /analyze` — Calculate hedge (form submission)
- `GET /api/quote/{ticker}` — JSON quote for a single ticker
