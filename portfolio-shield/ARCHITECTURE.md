# Portfolio Shield — Architecture & Technical Documentation

## Overview

Portfolio Shield is a web application that recommends delta-hedging strategies using protective put options. Users enter their stock holdings, select a protection level, and receive actionable options trades along with full portfolio analytics — all powered by live market data.

**Stack:** Python 3.13 · FastAPI · Jinja2 · yfinance · SVG charts · No database

---

## How It Works (End-to-End Flow)

```
User enters positions        GET /api/quote/{ticker}        POST /analyze
  (ticker, shares,     -->   auto-fills live price    -->   server-side
   avg cost)                  via JS fetch                  processing
        |                                                       |
        |                                         +-------------+-------------+
        |                                         |             |             |
        v                                    fetch_quote   select_put   get_history
   index.html                                (quotes.py)  (options.py)  (history.py)
                                                  |             |             |
                                                  v             v             v
                                             live price    best put     1y prices
                                                  |        option       + beta
                                                  |             |             |
                                                  +------+------+------+------+
                                                         |
                                                         v
                                                  calculate_hedge
                                                    (hedge.py)
                                                         |
                                                         v
                                                  results.html
                                              (Overview + Hedge tabs)
```

### Step 1: User Input (index.html)

The form collects one or more positions, each with:

| Field | Name | Required | Notes |
|-------|------|----------|-------|
| Ticker | `ticker` | Yes | Auto-uppercased, validated via `/api/quote` |
| Shares | `shares` | Yes | Positive integer |
| Avg Cost | `avg_cost` | No | Defaults to live price if omitted |

When the ticker input loses focus, JavaScript calls `GET /api/quote/{ticker}` and displays the live price with a green/red day-change badge. The user selects one of three protection levels (Light 25%, Moderate 50%, Full 100%) and submits.

### Step 2: Form Processing (main.py → POST /analyze)

The `/analyze` route:

1. **Parses form data** — extracts parallel arrays of `ticker[]`, `shares[]`, `avg_cost[]`
2. **Fetches live prices** — calls `fetch_quote()` for each ticker
3. **Calculates hedge** — calls `calculate_portfolio_hedge()` (unchanged from v1)
4. **Calculates portfolio analytics** — calls three functions from `history.py`:
   - `get_performance_summary()` — P&L, weights, best/worst
   - `get_portfolio_history()` — 1-year daily portfolio values
   - `get_portfolio_beta()` — beta vs SPY
5. **Pre-computes SVG geometry** — calls `_build_svg_data()` (trig functions unavailable in Jinja2)
6. **Renders results.html** — passes all data to the template

Each analytics call is wrapped in try/except so failures never break the hedge results.

### Step 3: Results Display (results.html)

The results page has two tabs:

**Overview Tab:**
- Summary bar (cost basis, current value, P&L, beta badge)
- Side-by-side pie charts (initial vs live allocation weights)
- 1-year portfolio evolution SVG line chart
- Positions table with P&L, beta, weight per ticker
- Best/worst performer badges
- Beta interpretation text

**Hedge Strategy Tab:**
- Protection summary banner
- Hedge metrics (portfolio value, hedge cost, net protected)
- Options-to-buy table (contracts, strike, expiry, cost, breakeven)
- CSS-only cost breakdown bar chart
- Hedge position details (IV, delta, DTE)
- Step-by-step next-steps guide

---

## File-by-File Reference

### main.py — FastAPI App & Routes

**Routes:**

| Method | Path | Purpose |
|--------|------|---------|
| GET | `/` | Renders the portfolio input form |
| GET | `/api/quote/{ticker}` | Returns JSON quote (price, change, change_pct) |
| POST | `/analyze` | Processes form, returns full results page |

**SVG Helpers (in main.py):**

- `_build_pie_slices(weights, key)` — Computes SVG arc `<path>` data for pie chart slices using `math.cos`/`math.sin`. Returns list of dicts with `path`, `color`, `ticker`, `pct`, label coordinates.
- `_build_chart_points(history)` — Converts daily portfolio values into SVG polyline coordinates. Computes cost-basis line position, area-fill polygon, hover points, axis labels.
- `_build_svg_data(performance, history)` — Orchestrator that builds all SVG data for the template.

**Color Palette:** `["#c9a84c", "#2dd4bf", "#f87171", "#818cf8", "#fb923c", "#a78bfa", "#34d399", "#f472b6"]`

---

### quotes.py — Price Fetching & Caching

**Cache System:**

```python
_cache: dict[str, dict] = {}  # key -> {"value": ..., "ts": unix_timestamp}

def get_cached(key, ttl, fetch_fn):
    # Returns cached value if age < ttl seconds
    # Otherwise calls fetch_fn(), stores result, returns it
```

This is the shared cache used by all modules. Cache tiers:

| Data Type | TTL | Cache Key Pattern |
|-----------|-----|-------------------|
| Quotes | 60s | `quote:AAPL` |
| Options chains | 300s (5 min) | `chain:AAPL` |
| Historical data | 1800s (30 min) | `history:AAPL\|MSFT\|NVDA` |
| Beta history | 1800s (30 min) | `beta_hist:AAPL\|MSFT\|NVDA\|SPY:1y` |

**fetch_quote(ticker):**

Uses `yf.Ticker(ticker).fast_info` to get:
- `last_price` — current market price
- `previous_close` — for calculating day change

Returns: `{ticker, price, change, change_pct, last_updated}`

Raises `ValueError` for unknown tickers.

---

### options.py — Options Chain & Put Selection

**Protection Level Parameters:**

| Level | Hedge % | OTM Offset | Meaning |
|-------|---------|------------|---------|
| Light | 25% | 10% OTM | Cheap disaster protection |
| Moderate | 50% | 5% OTM | Balanced cost vs coverage |
| Full | 100% | ATM (0%) | Maximum protection |

**select_put(ticker, current_price, hedge_level) Algorithm:**

1. Fetch all put option expiries from yfinance
2. Filter to 21–90 days to expiry (DTE)
3. For each expiry, filter for open interest > 100 (liquidity)
4. Find the strike closest to `current_price * (1 - otm_offset)`
5. Compute mid price = (bid + ask) / 2
6. Score each candidate: `abs(dte - 45) + (strike_distance / price) * 100`
7. Pick the lowest-scored candidate
8. If nothing found, fall back to Black-Scholes estimate

**Black-Scholes Fallback:**

When no liquid options exist, the app:
- Estimates IV from 3 months of realized volatility (`_estimate_iv`)
- Prices a synthetic put via `bs_put_price(S, K, T, r, sigma)`
- Computes delta via `bs_put_delta(S, K, T, r, sigma)`
- Flags the result with `is_fallback: True` (shown as a warning badge in the UI)

---

### hedge.py — Delta Hedge Math

**Single Position Formula:**

```
portfolio_delta = shares * hedge_pct
contracts       = round(portfolio_delta / (100 * |put_delta|))
cost            = contracts * mid_price * 100
breakeven       = strike - (cost / (contracts * 100))
cost_pct        = cost / (shares * price) * 100
```

**calculate_portfolio_hedge(positions, hedge_level):**

Iterates over all positions, calls `calculate_hedge()` for each, then aggregates:

| Output Field | Calculation |
|-------------|-------------|
| `total_value` | Sum of all position values |
| `total_cost` | Sum of all hedge costs |
| `total_cost_pct` | total_cost / total_value * 100 |
| `net_protected` | total_value - total_cost |
| `protection_threshold` | Weighted average OTM percentage |
| `any_fallback` | True if any position used BS estimate |

---

### history.py — Portfolio Analytics

**Concurrent Fetching:**

All yfinance history calls run in parallel via `ThreadPoolExecutor`:
- Max 5 workers
- 10-second timeout per ticker
- Timed-out tickers are excluded with a warning

**get_portfolio_history(positions):**

1. Fetches 1-year daily close prices for all tickers concurrently
2. Builds a unified date index across all tickers
3. Forward-fills missing prices (for days when one ticker has data but another doesn't)
4. Calculates daily portfolio value: `sum(shares[i] * price[i][date])` for each date
5. Returns dates, values, cost_basis, min, max, current

**get_portfolio_beta(positions):**

1. Fetches 1-year daily prices for all tickers + SPY
2. For each ticker, aligns dates with SPY and computes daily returns
3. Calculates per-ticker beta: `cov(ticker_returns, spy_returns) / var(spy_returns)`
4. Computes portfolio beta: `sum(weight[i] * beta[i])`
5. Computes SPY correlation from portfolio-level returns vs SPY returns

**Beta Display Logic:**

| Beta Range | Label | Color |
|-----------|-------|-------|
| < 0.8 | Defensive | Teal (#2dd4bf) |
| 0.8 – 1.2 | Market-like | Gold (#c9a84c) |
| > 1.2 | Aggressive | Red (#f87171) |

**get_performance_summary(positions):**

For each position:
- `pnl = shares * (live_price - avg_cost)`
- `pnl_pct = (live_price - avg_cost) / avg_cost * 100`
- `weight = position_live_value / total_live_value * 100`
- `cost_weight = position_cost_value / total_cost_basis * 100`

Identifies best performer (highest pnl_pct) and worst performer (lowest pnl_pct).

---

## Frontend Architecture

### Styling

Both HTML files use embedded `<style>` blocks (no external CSS). Design tokens:

```css
--bg:   #0a0e1a   /* main background */
--bg2:  #111827   /* card background */
--bg3:  #1a2234   /* input/nested background */
--gold: #c9a84c   /* primary accent, headings */
--teal: #2dd4bf   /* positive values, gains */
--red:  #f87171   /* negative values, losses */
--text: #e2e8f0   /* primary text */
--text-dim: #94a3b8  /* secondary text */
--border: #2a3346    /* borders, dividers */
```

**Fonts:** DM Serif Display (headings), DM Mono (numbers/data), DM Sans (body text) — loaded via Google Fonts.

### SVG Charts (No Libraries)

**Pie Charts:** Pre-computed arc paths passed from Python. Each slice is an SVG `<path>` with `M 0 0 L ... A ... Z` syntax. Labels positioned at 65% radius using trig. Hover shows ticker + percentage via `<title>` elements.

**Evolution Chart:** 860x320 SVG viewBox with 70px left padding for Y-axis labels. The chart has:
- A dark `<rect>` plot background
- Horizontal grid lines at 5 Y-axis ticks
- A gold `<polyline>` for the portfolio value line
- Green `<polygon>` fill above cost basis (clipped)
- Red `<polygon>` fill below cost basis (clipped)
- A dashed cost-basis reference line
- Min, Max, and Current value annotations
- Invisible enlarged `<circle>` elements for hover tooltips

### Tab Switcher

Pure CSS + vanilla JS. Two `<div class="tab-content">` containers, toggled via:

```javascript
function switchTab(name, btn) {
    document.querySelectorAll('.tab-content').forEach(t => t.classList.remove('active'));
    document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
    document.getElementById('tab-' + name).classList.add('active');
    btn.classList.add('active');
}
```

### Dynamic Form Rows

The "Add another position" button clones a row template via `innerHTML`. Ticker blur events trigger live price fetches. Rows can be removed (minimum 1 row enforced).

---

## Data Flow Diagram

```
index.html
    |
    |  POST /analyze
    |  form: ticker[], shares[], avg_cost[], hedge_level
    |
    v
main.py (analyze route)
    |
    +-- fetch_quote(ticker) x N        [quotes.py, 60s cache]
    |       uses yf.Ticker.fast_info
    |
    +-- calculate_portfolio_hedge()     [hedge.py]
    |       |
    |       +-- select_put() x N        [options.py, 5min cache]
    |       |       uses yf.Ticker.option_chain
    |       |       fallback: Black-Scholes
    |       |
    |       +-- hedge math (contracts, cost, breakeven)
    |
    +-- get_performance_summary()       [history.py]
    |       pure math on positions data
    |
    +-- get_portfolio_history()         [history.py, 30min cache]
    |       concurrent yf.Ticker.history(period="1y")
    |       forward-fill, daily aggregation
    |
    +-- get_portfolio_beta()            [history.py, 30min cache]
    |       concurrent fetch (tickers + SPY)
    |       covariance / variance calculation
    |
    +-- _build_svg_data()               [main.py]
    |       pie slices (cos/sin arc paths)
    |       chart polyline coordinates
    |
    v
results.html
    Tab 1: Overview (pies, chart, P&L table, beta)
    Tab 2: Hedge Strategy (options, costs, next steps)
```

---

## Error Handling Strategy

| Error | Where | Behavior |
|-------|-------|----------|
| Invalid ticker | `/api/quote` | Returns 400 JSON error; form shows "Not found" |
| yfinance timeout | `/analyze` | Returns error page or excludes ticker with warning |
| No liquid options | `select_put()` | Falls back to Black-Scholes; flagged with warning badge |
| History fetch fails | `/analyze` | Chart section hidden; hedge results still shown |
| Beta calc fails | `/analyze` | Beta shows "N/A"; everything else works |
| Invalid shares | `/analyze` | Per-ticker error message; valid tickers still processed |

The design principle: **analytics failures never break hedge results.** Each analytics call is independent and wrapped in try/except.

---

## Caching Architecture

```
_cache (Python dict in quotes.py)
    |
    +-- "quote:AAPL"        TTL=60s     live stock price
    +-- "quote:MSFT"        TTL=60s
    +-- "chain:AAPL"        TTL=300s    full put options chain
    +-- "chain:MSFT"        TTL=300s
    +-- "history:AAPL|MSFT" TTL=1800s   1y daily close prices
    +-- "beta_hist:..."     TTL=1800s   1y prices for beta calc
```

All data lives in a single process-level dict. No Redis, no database. Cache is wiped on server restart. The `get_cached(key, ttl, fetch_fn)` function handles all tiers uniformly.

---

## Dependencies

| Package | Version | Purpose |
|---------|---------|---------|
| fastapi | 0.135+ | Web framework, routing |
| uvicorn | 0.41+ | ASGI server |
| yfinance | 1.2+ | Stock prices, options chains, history |
| jinja2 | 3.1+ | HTML templating |
| python-multipart | 0.0.22+ | Form data parsing |
| scipy | 1.17+ | `norm.cdf` for Black-Scholes |
| pandas | 2.2.3 | Required by yfinance (pinned for Windows compatibility) |
| numpy | 2.4+ | Array math for beta/correlation |

---

## Running the Application

```bash
cd portfolio-shield
pip install -r requirements.txt
python main.py
# → http://127.0.0.1:8000
```

Or via uvicorn directly:

```bash
uvicorn main:app --host 127.0.0.1 --port 8000 --reload
```
