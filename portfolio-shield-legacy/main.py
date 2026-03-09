"""
main.py — FastAPI app, routes, startup.
"""

import logging
import math
import time
from fastapi import FastAPI, Request, Form
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates

from quotes import fetch_quote
from hedge import calculate_portfolio_hedge
from history import get_portfolio_history, get_portfolio_beta, get_performance_summary

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# App
# ---------------------------------------------------------------------------
app = FastAPI(title="Portfolio Shield", version="1.0.0")
templates = Jinja2Templates(directory="templates")


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})


@app.get("/api/quote/{ticker}")
async def api_quote(ticker: str):
    """JSON endpoint: live quote for a single ticker."""
    try:
        quote = fetch_quote(ticker)
        return JSONResponse(quote)
    except ValueError as e:
        return JSONResponse({"error": str(e)}, status_code=400)
    except Exception as e:
        logger.error("Quote API error for %s: %s", ticker, e)
        return JSONResponse(
            {"error": f"Could not fetch data for '{ticker}'. Please try again."},
            status_code=503,
        )


@app.post("/analyze", response_class=HTMLResponse)
async def analyze(request: Request):
    """Process portfolio form and return hedge strategy results."""
    form = await request.form()

    # Parse positions from form
    tickers = form.getlist("ticker")
    shares_list = form.getlist("shares")
    avg_cost_list = form.getlist("avg_cost")
    hedge_level = form.get("hedge_level", "moderate")

    if hedge_level not in ("light", "moderate", "full"):
        hedge_level = "moderate"

    positions = []
    errors = []

    for i, ticker in enumerate(tickers):
        ticker = ticker.strip().upper()
        if not ticker:
            continue

        shares_str = shares_list[i] if i < len(shares_list) else ""
        avg_cost_str = avg_cost_list[i] if i < len(avg_cost_list) else ""

        try:
            shares = int(shares_str)
            if shares <= 0:
                raise ValueError("Shares must be positive")
        except (ValueError, TypeError):
            errors.append(f"Invalid share count for {ticker}")
            continue

        # Parse avg_cost (optional — defaults to live price later)
        avg_cost = None
        if avg_cost_str and avg_cost_str.strip():
            try:
                avg_cost = float(avg_cost_str)
                if avg_cost <= 0:
                    avg_cost = None
            except (ValueError, TypeError):
                avg_cost = None

        # Fetch live price
        try:
            quote = fetch_quote(ticker)
            positions.append({
                "ticker": ticker,
                "shares": shares,
                "price": quote["price"],
                "avg_cost": avg_cost if avg_cost else quote["price"],
            })
        except ValueError:
            errors.append(f"Unknown ticker: {ticker}")
        except Exception:
            errors.append(f"Could not fetch data for {ticker}. Service may be unavailable.")

    if errors and not positions:
        return templates.TemplateResponse("index.html", {
            "request": request,
            "errors": errors,
        })

    if not positions:
        return templates.TemplateResponse("index.html", {
            "request": request,
            "errors": ["Please enter at least one valid position."],
        })

    # Calculate hedge
    try:
        result = calculate_portfolio_hedge(positions, hedge_level)
        result["timestamp"] = time.strftime("%H:%M ET")
        result["errors"] = errors  # pass through any partial errors
    except Exception as e:
        logger.error("Hedge calculation failed: %s", e)
        return templates.TemplateResponse("index.html", {
            "request": request,
            "errors": [f"Calculation error: {e}"],
        })

    # Portfolio analysis (non-blocking — failures don't break hedge results)
    performance = get_performance_summary(positions)

    portfolio_history = {"dates": [], "values": [], "cost_basis": 0, "warnings": []}
    try:
        portfolio_history = get_portfolio_history(positions)
    except Exception as e:
        logger.error("History fetch failed: %s", e)
        portfolio_history["warnings"] = [str(e)]

    portfolio_beta = {"portfolio_beta": None, "position_betas": {}, "spy_correlation": None, "warnings": []}
    try:
        portfolio_beta = get_portfolio_beta(positions)
    except Exception as e:
        logger.error("Beta calc failed: %s", e)
        portfolio_beta["warnings"] = [str(e)]

    # Pre-compute SVG data (trig not available in Jinja2)
    svg_data = _build_svg_data(performance, portfolio_history)

    return templates.TemplateResponse("results.html", {
        "request": request,
        "result": result,
        "performance": performance,
        "portfolio_history": portfolio_history,
        "portfolio_beta": portfolio_beta,
        "svg": svg_data,
    })


# ---------------------------------------------------------------------------
# SVG pre-computation helpers
# ---------------------------------------------------------------------------
PALETTE = ["#c9a84c", "#2dd4bf", "#f87171", "#818cf8", "#fb923c", "#a78bfa", "#34d399", "#f472b6"]


def _build_pie_slices(weights: list[dict], key: str) -> list[dict]:
    """Build SVG arc path data for pie chart slices.

    Each entry: {path, color, ticker, pct, label_x, label_y, show_label}
    """
    slices = []
    cum = 0.0
    for i, pos in enumerate(weights):
        pct = pos[key] / 100.0
        if pct <= 0:
            continue
        start = cum * 2 * math.pi
        end = (cum + pct) * 2 * math.pi
        large = 1 if pct > 0.5 else 0

        sx, sy = math.cos(start), math.sin(start)
        ex, ey = math.cos(end), math.sin(end)

        mid = (cum + pct / 2) * 2 * math.pi
        lx, ly = 0.65 * math.cos(mid), 0.65 * math.sin(mid)

        path = f"M 0 0 L {sx:.4f} {sy:.4f} A 1 1 0 {large} 1 {ex:.4f} {ey:.4f} Z"
        slices.append({
            "path": path,
            "color": PALETTE[i % len(PALETTE)],
            "ticker": pos["ticker"],
            "pct": pos[key],
            "label_x": f"{lx:.4f}",
            "label_y": f"{ly:.4f}",
            "show_label": pct > 0.06,
        })
        cum += pct
    return slices


def _build_chart_points(history: dict) -> dict:
    """Pre-compute SVG line chart coordinates."""
    dates = history.get("dates", [])
    values = history.get("values", [])
    if len(values) < 5:
        return {"points": "", "hover_points": [], "x_labels": [], "y_labels": [],
                "cb_y": 0, "last_x": 0, "last_y": 0, "min_x": 0, "min_y_pos": 0,
                "max_x": 0, "has_data": False}

    ch_w, ch_h = 860, 320
    pad_l, pad_r, pad_t, pad_b = 70, 20, 30, 50
    plot_w = ch_w - pad_l - pad_r
    plot_h = ch_h - pad_t - pad_b

    v_min = history["min_value"]
    v_max = history["max_value"]
    v_range = v_max - v_min if v_max != v_min else 1
    cb = history["cost_basis"]
    n = len(values)

    # Build polyline points
    pts = []
    for i, v in enumerate(values):
        x = pad_l + (i / (n - 1)) * plot_w
        y = pad_t + plot_h - ((v - v_min) / v_range * plot_h)
        pts.append(f"{x:.1f},{y:.1f}")
    points_str = " ".join(pts)

    # Cost basis Y position
    cb_y = pad_t + plot_h - ((cb - v_min) / v_range * plot_h)
    cb_in_range = v_min <= cb <= v_max

    # Last point (current)
    last_x = pad_l + plot_w
    last_y = pad_t + plot_h - ((values[-1] - v_min) / v_range * plot_h)

    # Min/Max positions
    min_idx = values.index(v_min)
    max_idx = values.index(v_max)
    min_x = pad_l + (min_idx / (n - 1)) * plot_w
    max_x = pad_l + (max_idx / (n - 1)) * plot_w

    # Hover points (every 3rd + last)
    hover_points = []
    for i, v in enumerate(values):
        if i % 3 == 0 or i == n - 1:
            hx = pad_l + (i / (n - 1)) * plot_w
            hy = pad_t + plot_h - ((v - v_min) / v_range * plot_h)
            hover_points.append({"x": f"{hx:.1f}", "y": f"{hy:.1f}",
                                 "date": dates[i], "value": f"{v:,.0f}"})

    # X-axis labels (~6 labels)
    step = max(n // 6, 1)
    x_labels = []
    for i in range(0, n, step):
        lx = pad_l + (i / (n - 1)) * plot_w
        x_labels.append({"x": f"{lx:.1f}", "label": dates[i][5:]})

    # Y-axis labels (5 ticks)
    y_labels = []
    for i in range(5):
        yv = v_min + (v_range * i / 4)
        yy = pad_t + plot_h - (plot_h * i / 4)
        y_labels.append({"y": f"{yy:.1f}", "label": f"${yv:,.0f}"})

    # Area polygon (for green/red fill — closes to cost basis line)
    close_left = f"{pad_l:.1f},{cb_y:.1f}"
    close_right = f"{pad_l + plot_w:.1f},{cb_y:.1f}"
    area_points = points_str + f" {close_right} {close_left}"

    return {
        "has_data": True,
        "points": points_str,
        "area_points": area_points,
        "hover_points": hover_points,
        "x_labels": x_labels,
        "y_labels": y_labels,
        "cb_y": f"{cb_y:.1f}",
        "cb_in_range": cb_in_range,
        "last_x": f"{last_x:.1f}",
        "last_y": f"{last_y:.1f}",
        "min_x": f"{min_x:.1f}",
        "min_y_pos": f"{(pad_t + plot_h - 5):.1f}",
        "max_x": f"{max_x:.1f}",
        "max_y_pos": f"{(pad_t + 12):.1f}",
        "plot_x": pad_l,
        "plot_y": pad_t,
        "plot_w": plot_w,
        "plot_h": plot_h,
        "ch_w": ch_w,
        "ch_h": ch_h,
    }


def _build_svg_data(performance: dict, history: dict) -> dict:
    """Build all pre-computed SVG data for templates."""
    return {
        "pie_initial": _build_pie_slices(performance["positions"], "cost_weight"),
        "pie_live": _build_pie_slices(performance["positions"], "weight"),
        "chart": _build_chart_points(history),
        "palette": PALETTE,
    }


# ---------------------------------------------------------------------------
# Startup
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    import uvicorn

    uvicorn.run("main:app", host="127.0.0.1", port=8000, reload=True)
