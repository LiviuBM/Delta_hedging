"""
main.py - FastAPI app, routes, and startup.
"""

import logging
import math
import time
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates

from hedge import build_delta_advice
from history import get_performance_summary, get_portfolio_beta, get_portfolio_history
from quotes import fetch_quote
from storage import init_storage, save_recommendation

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

app = FastAPI(title="Portfolio Shield", version="2.0.0")
templates = Jinja2Templates(directory="templates")


@app.on_event("startup")
async def startup_event():
    init_storage()


@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})


@app.get("/api/quote/{ticker}")
async def api_quote(ticker: str):
    try:
        quote = fetch_quote(ticker)
        return JSONResponse(quote)
    except ValueError as exc:
        return JSONResponse({"error": str(exc)}, status_code=400)
    except RuntimeError as exc:
        logger.error("Quote API service error for %s: %s", ticker, exc)
        return JSONResponse({"error": str(exc)}, status_code=503)
    except Exception as exc:
        logger.error("Quote API unexpected error for %s: %s", ticker, exc)
        return JSONResponse({"error": "Unexpected quote error."}, status_code=500)


@app.post("/analyze", response_class=HTMLResponse)
async def analyze(request: Request):
    form = await request.form()

    tickers = form.getlist("ticker")
    shares_list = form.getlist("shares")
    avg_cost_list = form.getlist("avg_cost")
    hedge_level = form.get("hedge_level", "moderate")
    objective = form.get("objective", "reduce_downside")
    experience = form.get("experience", "beginner")
    horizon_days = _safe_int(form.get("horizon_days"), default=45, minimum=21, maximum=90)
    max_budget = _safe_float(form.get("max_budget"), default=0.0, minimum=0.0)

    if hedge_level not in ("light", "moderate", "full"):
        hedge_level = "moderate"
    if objective not in ("reduce_downside", "protect_gains", "crash_hedge", "partial_delta"):
        objective = "reduce_downside"
    if experience not in ("beginner", "intermediate", "advanced"):
        experience = "beginner"

    positions = []
    errors = []

    for idx, ticker in enumerate(tickers):
        ticker = ticker.strip().upper()
        if not ticker:
            continue

        shares_str = shares_list[idx] if idx < len(shares_list) else ""
        avg_cost_str = avg_cost_list[idx] if idx < len(avg_cost_list) else ""

        try:
            shares = int(shares_str)
            if shares <= 0:
                raise ValueError
        except (ValueError, TypeError):
            errors.append(f"Invalid share count for {ticker}")
            continue

        avg_cost = None
        if avg_cost_str and avg_cost_str.strip():
            try:
                avg_cost = float(avg_cost_str)
                if avg_cost <= 0:
                    avg_cost = None
            except (ValueError, TypeError):
                avg_cost = None

        try:
            quote = fetch_quote(ticker)
            positions.append(
                {
                    "ticker": ticker,
                    "shares": shares,
                    "price": quote["price"],
                    "avg_cost": avg_cost if avg_cost else quote["price"],
                }
            )
        except ValueError:
            errors.append(f"Unknown ticker: {ticker}")
        except RuntimeError:
            errors.append(f"Market data unavailable for {ticker}. Please retry.")
        except Exception:
            errors.append(f"Could not fetch data for {ticker}.")

    if errors and not positions:
        return templates.TemplateResponse("index.html", {"request": request, "errors": errors})

    if not positions:
        return templates.TemplateResponse(
            "index.html",
            {"request": request, "errors": ["Please enter at least one valid position."]},
        )

    performance = get_performance_summary(positions)

    portfolio_history = {"dates": [], "values": [], "cost_basis": 0, "warnings": []}
    try:
        portfolio_history = get_portfolio_history(positions)
    except Exception as exc:
        logger.error("History fetch failed: %s", exc)
        portfolio_history["warnings"] = [str(exc)]

    portfolio_beta = {"portfolio_beta": None, "position_betas": {}, "spy_correlation": None, "warnings": []}
    try:
        portfolio_beta = get_portfolio_beta(positions)
    except Exception as exc:
        logger.error("Beta calc failed: %s", exc)
        portfolio_beta["warnings"] = [str(exc)]

    profile = {
        "objective": objective,
        "experience": experience,
        "horizon_days": horizon_days,
        "max_budget": max_budget,
    }

    try:
        recommendation = build_delta_advice(
            positions,
            hedge_level,
            profile,
            portfolio_beta=portfolio_beta.get("portfolio_beta"),
        )
        recommendation["timestamp"] = time.strftime("%H:%M ET")
        recommendation["errors"] = errors
    except Exception as exc:
        logger.error("Advisory calculation failed: %s", exc)
        return templates.TemplateResponse(
            "index.html",
            {"request": request, "errors": [f"Calculation error: {exc}"]},
        )

    svg_data = _build_svg_data(performance, portfolio_history)

    payload = {
        "profile": profile,
        "positions": positions,
        "performance": performance,
        "portfolio_beta": portfolio_beta,
        "recommendation": recommendation,
    }
    recommendation_id = save_recommendation(payload)

    return templates.TemplateResponse(
        "results.html",
        {
            "request": request,
            "profile": profile,
            "performance": performance,
            "portfolio_history": portfolio_history,
            "portfolio_beta": portfolio_beta,
            "recommendation": recommendation,
            "recommendation_id": recommendation_id,
            "svg": svg_data,
        },
    )


PALETTE = ["#d3a44a", "#45c4b0", "#ef7d57", "#7b8cff", "#f0b35b", "#f87171", "#4fd1c5", "#f6ad55"]


def _build_pie_slices(weights: list[dict], key: str) -> list[dict]:
    slices = []
    cumulative = 0.0
    for idx, position in enumerate(weights):
        pct = position[key] / 100.0
        if pct <= 0:
            continue
        start = cumulative * 2 * math.pi
        end = (cumulative + pct) * 2 * math.pi
        large = 1 if pct > 0.5 else 0

        start_x, start_y = math.cos(start), math.sin(start)
        end_x, end_y = math.cos(end), math.sin(end)
        mid = (cumulative + pct / 2) * 2 * math.pi
        label_x, label_y = 0.65 * math.cos(mid), 0.65 * math.sin(mid)

        slices.append(
            {
                "path": f"M 0 0 L {start_x:.4f} {start_y:.4f} A 1 1 0 {large} 1 {end_x:.4f} {end_y:.4f} Z",
                "color": PALETTE[idx % len(PALETTE)],
                "ticker": position["ticker"],
                "pct": position[key],
                "label_x": f"{label_x:.4f}",
                "label_y": f"{label_y:.4f}",
                "show_label": pct > 0.06,
            }
        )
        cumulative += pct
    return slices


def _build_chart_points(history: dict) -> dict:
    dates = history.get("dates", [])
    values = history.get("values", [])
    if len(values) < 5:
        return {
            "points": "",
            "hover_points": [],
            "x_labels": [],
            "y_labels": [],
            "cb_y": 0,
            "last_x": 0,
            "last_y": 0,
            "min_x": 0,
            "min_y_pos": 0,
            "max_x": 0,
            "has_data": False,
        }

    chart_w, chart_h = 860, 320
    pad_l, pad_r, pad_t, pad_b = 70, 20, 30, 50
    plot_w = chart_w - pad_l - pad_r
    plot_h = chart_h - pad_t - pad_b

    value_min = history["min_value"]
    value_max = history["max_value"]
    value_range = value_max - value_min if value_max != value_min else 1
    cost_basis = history["cost_basis"]
    count = len(values)

    points = []
    for idx, value in enumerate(values):
        x_pos = pad_l + (idx / (count - 1)) * plot_w
        y_pos = pad_t + plot_h - ((value - value_min) / value_range * plot_h)
        points.append(f"{x_pos:.1f},{y_pos:.1f}")
    points_str = " ".join(points)

    cb_y = pad_t + plot_h - ((cost_basis - value_min) / value_range * plot_h)
    cb_in_range = value_min <= cost_basis <= value_max
    last_x = pad_l + plot_w
    last_y = pad_t + plot_h - ((values[-1] - value_min) / value_range * plot_h)

    min_idx = values.index(value_min)
    max_idx = values.index(value_max)
    min_x = pad_l + (min_idx / (count - 1)) * plot_w
    max_x = pad_l + (max_idx / (count - 1)) * plot_w

    hover_points = []
    for idx, value in enumerate(values):
        if idx % 3 == 0 or idx == count - 1:
            x_pos = pad_l + (idx / (count - 1)) * plot_w
            y_pos = pad_t + plot_h - ((value - value_min) / value_range * plot_h)
            hover_points.append({"x": f"{x_pos:.1f}", "y": f"{y_pos:.1f}", "date": dates[idx], "value": f"{value:,.0f}"})

    x_labels = []
    step = max(count // 6, 1)
    for idx in range(0, count, step):
        x_pos = pad_l + (idx / (count - 1)) * plot_w
        x_labels.append({"x": f"{x_pos:.1f}", "label": dates[idx][5:]})

    y_labels = []
    for idx in range(5):
        label_value = value_min + (value_range * idx / 4)
        y_pos = pad_t + plot_h - (plot_h * idx / 4)
        y_labels.append({"y": f"{y_pos:.1f}", "label": f"${label_value:,.0f}"})

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
        "ch_w": chart_w,
        "ch_h": chart_h,
    }


def _build_svg_data(performance: dict, history: dict) -> dict:
    return {
        "pie_initial": _build_pie_slices(performance["positions"], "cost_weight"),
        "pie_live": _build_pie_slices(performance["positions"], "weight"),
        "chart": _build_chart_points(history),
        "palette": PALETTE,
    }


def _safe_int(value, default: int, minimum: int, maximum: int) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return default
    return max(minimum, min(parsed, maximum))


def _safe_float(value, default: float, minimum: float) -> float:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return default
    return max(minimum, parsed)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("main:app", host="127.0.0.1", port=8000, reload=True)
