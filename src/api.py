"""FastAPI server for the stock screener — refactored with domain-specific routers."""

import json
import logging
import math
import os
from datetime import date
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

# Load .env file for API_KEY
load_dotenv()

from .routes import scan, portfolio, backtest, optimize, ml, trading, analysis, risk, thesis, rebalance
from .pipeline import DATA_DIR

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger(__name__)

app = FastAPI(title="Stock Picker", version="5.0.0")

# Include all domain routers
app.include_router(scan.router)
app.include_router(portfolio.router)
app.include_router(backtest.router)
app.include_router(optimize.router)
app.include_router(ml.router)
app.include_router(trading.router)
app.include_router(analysis.router)
app.include_router(risk.router)
app.include_router(thesis.router)
app.include_router(rebalance.router)


# --- Core endpoints (kept in main api.py) ---


@app.get("/health")
def health():
    """Health check endpoint."""
    return {"status": "ok"}


@app.get("/strategies")
def strategies_list():
    """List all available strategies with descriptions."""
    from .strategies import list_strategies

    return {"strategies": list_strategies()}


# --- Watchlist endpoints ---

WATCHLIST_FILE = DATA_DIR / "watchlist.json"


def _load_watchlist() -> dict:
    if WATCHLIST_FILE.exists():
        with open(WATCHLIST_FILE) as f:
            return json.load(f)
    return {"tickers": {}}


def _save_watchlist(data: dict):
    with open(WATCHLIST_FILE, "w") as f:
        json.dump(data, f, indent=2)


def _get_current_price(ticker: str):
    cache_path = DATA_DIR / "stock_data_cache.json"
    if not cache_path.exists():
        return None
    with open(cache_path) as f:
        cache = json.load(f)
    entry = cache.get(ticker)
    if not entry:
        return None
    closes = entry.get("history", {}).get("Close", [])
    for val in reversed(closes):
        if val is not None and not math.isnan(val):
            return val
    return None


@app.get("/watchlist")
async def get_watchlist():
    """Get watchlist with current prices and performance."""
    data = _load_watchlist()
    enriched = {}
    for ticker, meta in data["tickers"].items():
        current_price = _get_current_price(ticker)
        price_at_add = meta.get("price_at_add")
        change_pct = None
        if current_price is not None and price_at_add and price_at_add != 0:
            change_pct = round(
                (current_price - price_at_add) / price_at_add * 100, 2
            )
        enriched[ticker] = {
            "added": meta.get("added"),
            "price_at_add": price_at_add,
            "current_price": current_price,
            "change_pct": change_pct,
        }
    return {"tickers": enriched}


@app.post("/watchlist/{ticker}")
async def add_to_watchlist(ticker: str):
    """Add ticker to watchlist."""
    ticker = ticker.upper()
    data = _load_watchlist()
    if ticker in data["tickers"]:
        return {"status": "already_exists", "ticker": ticker}
    price = _get_current_price(ticker)
    data["tickers"][ticker] = {
        "added": date.today().isoformat(),
        "price_at_add": price,
    }
    _save_watchlist(data)
    return {"status": "added", "ticker": ticker, "price_at_add": price}


@app.delete("/watchlist/{ticker}")
async def remove_from_watchlist(ticker: str):
    """Remove ticker from watchlist."""
    ticker = ticker.upper()
    data = _load_watchlist()
    if ticker not in data["tickers"]:
        return {"status": "not_found", "ticker": ticker}
    del data["tickers"][ticker]
    _save_watchlist(data)
    return {"status": "removed", "ticker": ticker}


# --- Cache health diagnostic ---


@app.get("/cache/health")
async def cache_health():
    """Read-only cache health diagnostic."""
    import asyncio

    from .cache_health import diagnose_cache

    return await asyncio.to_thread(diagnose_cache)


# --- Devil's Advocate endpoint ---


@app.get("/review/{ticker}")
async def devil_review(ticker: str):
    """Devil's Advocate review — find every reason NOT to buy this stock."""
    import asyncio

    from .devils_advocate import review

    return await asyncio.to_thread(review, ticker.upper())


# --- Static files mounting ---

_static_dist = Path(__file__).parent.parent / "static" / "dist"
_static_legacy = Path(__file__).parent.parent / "static"

if _static_dist.exists():
    app.mount(
        "/assets",
        StaticFiles(directory=str(_static_dist / "assets")),
        name="static-assets",
    )

    @app.get("/{full_path:path}")
    async def serve_spa(full_path: str):
        file_path = _static_dist / full_path
        if file_path.is_file():
            return FileResponse(file_path)
        return FileResponse(_static_dist / "index.html")
else:
    app.mount("/", StaticFiles(directory=str(_static_legacy), html=True), name="static")


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
