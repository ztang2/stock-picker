"""FastAPI server for the stock screener."""

import logging
import json
from pathlib import Path
from typing import Optional, List

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles

from .pipeline import run_scan, get_stock_detail, get_all_sectors, load_config, RESULTS_FILE, DATA_DIR
from .backtest import run_backtest, load_backtest_history, run_rolling_backtest, get_rolling_backtest_status, load_rolling_backtest_cache
from .sentiment import analyze_sentiment
from .earnings import get_earnings_info
from .portfolio import build_portfolio
from .alerts import check_alerts, get_alert_history, generate_morning_briefing
from .momentum import compute_momentum
from .strategies import list_strategies, get_strategy
from .fmp import fetch_all_fundamentals, get_fetch_status, get_cached_fundamentals
from .universe import get_sp500_tickers
from .accuracy import get_accuracy, take_snapshot
from .streak_tracker import get_all_streaks, get_streak

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")

app = FastAPI(title="Stock Picker", version="4.0.0")

_static_dir = Path(__file__).resolve().parent.parent / "static"
app.mount("/static", StaticFiles(directory=str(_static_dir), html=True), name="static")


@app.get("/")
def root_redirect():
    return RedirectResponse(url="/static/index.html")


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/strategies")
def strategies_list():
    """List all available strategies with descriptions."""
    return {"strategies": list_strategies()}


@app.get("/scan")
def scan(
    sector: Optional[str] = Query(None, description="Filter by sector (e.g. Technology)"),
    min_cap: Optional[float] = Query(None, description="Minimum market cap (e.g. 10e9)"),
    max_cap: Optional[float] = Query(None, description="Maximum market cap"),
    exclude: Optional[str] = Query(None, description="Comma-separated tickers to exclude"),
    strategy: str = Query("balanced", description="Strategy: conservative, balanced, aggressive"),
):
    """Run full scan with optional filters and strategy. Returns top ranked stocks."""
    config = load_config()
    exclude_list = [t.strip().upper() for t in exclude.split(",")] if exclude else None
    result = run_scan(
        config,
        sector=sector,
        min_cap=min_cap,
        max_cap=max_cap,
        exclude_tickers=exclude_list,
        strategy=strategy,
    )
    return result


@app.get("/scan/cached")
def scan_cached():
    """Return last scan results without re-running."""
    if RESULTS_FILE.exists():
        return json.loads(RESULTS_FILE.read_text())
    raise HTTPException(404, "No cached results. Run /scan first.")


@app.get("/compare")
def compare_strategies(
    strategies: str = Query("conservative,balanced,aggressive", description="Comma-separated strategy names"),
    sector: Optional[str] = Query(None),
    min_cap: Optional[float] = Query(None),
    max_cap: Optional[float] = Query(None),
):
    """Run same universe with different strategies, return side-by-side top 20s."""
    config = load_config()
    strat_names = [s.strip().lower() for s in strategies.split(",")]
    results = {}
    for name in strat_names:
        try:
            result = run_scan(
                config,
                sector=sector,
                min_cap=min_cap,
                max_cap=max_cap,
                strategy=name,
            )
            results[name] = {
                "strategy": get_strategy(name),
                "top": result.get("top", [])[:20],
                "stocks_analyzed": result.get("stocks_analyzed", 0),
                "stocks_after_filter": result.get("stocks_after_filter", 0),
            }
        except Exception as e:
            results[name] = {"error": str(e)}
    return {"comparison": results}


@app.get("/sectors")
def list_sectors():
    """List all sectors with stock counts."""
    config = load_config()
    sectors = get_all_sectors(config)
    if not sectors:
        raise HTTPException(404, "No cached data. Run /scan first to populate.")
    return {"sectors": sectors, "total": sum(sectors.values())}


@app.get("/top/{sector}")
def top_in_sector(sector: str, top_n: int = Query(10, ge=1, le=50)):
    """Top stocks in a specific sector."""
    config = load_config()
    config["top_n"] = top_n
    result = run_scan(config, sector=sector)
    return result


@app.get("/stock/{ticker}")
def stock_detail(ticker: str):
    """Detailed breakdown for one stock with sentiment and earnings."""
    config = load_config()
    result = get_stock_detail(ticker, config)
    if not result:
        raise HTTPException(404, "No data for %s" % ticker.upper())

    # Enrich with sentiment
    try:
        result["sentiment"] = analyze_sentiment(ticker.upper())
    except Exception:
        result["sentiment"] = None

    # Enrich with earnings
    try:
        result["earnings"] = get_earnings_info(ticker.upper())
    except Exception:
        result["earnings"] = None

    return result


@app.get("/alerts")
def get_alerts(limit: int = Query(50, ge=1, le=200)):
    """Get current and historical alerts."""
    try:
        current = check_alerts()
    except Exception:
        current = []
    history = get_alert_history(limit)
    return {"current": current, "history": history}


@app.get("/briefing")
def morning_briefing(top_n: int = Query(20, ge=5, le=50)):
    """Get morning briefing with streak indicators."""
    try:
        briefing = generate_morning_briefing(top_n=top_n)
        return {"briefing": briefing}
    except Exception as e:
        raise HTTPException(500, "Briefing generation failed: %s" % str(e))


@app.get("/signals")
def get_signals(strategy: str = Query("balanced", description="Strategy to use")):
    """Get stocks with STRONG_BUY or BUY entry signals."""
    if not RESULTS_FILE.exists():
        raise HTTPException(404, "No scan results. Run /scan first.")
    data = json.loads(RESULTS_FILE.read_text())
    top = data.get("top", [])
    signals = [s for s in top if s.get("entry_signal") in ("STRONG_BUY", "BUY")]
    return {"signals": signals, "count": len(signals)}


@app.get("/backtest")
def backtest(
    months_back: int = Query(6, ge=1, le=24, description="How many months back to test"),
    top_n: int = Query(20, ge=5, le=50),
):
    """Run a backtest from N months ago."""
    try:
        result = run_backtest(months_back=months_back, top_n=top_n)
        return result
    except Exception as e:
        raise HTTPException(500, "Backtest failed: %s" % str(e))


@app.get("/backtest/rolling")
def rolling_backtest(
    years: int = Query(5, ge=1, le=10, description="Years of rolling backtest"),
    force: bool = Query(False, description="Force re-run ignoring cache"),
):
    """Run rolling monthly backtest across all strategies."""
    try:
        if force:
            cache_file = DATA_DIR / "rolling_backtest.json"
            if cache_file.exists():
                cache_file.unlink()
        result = run_rolling_backtest(years=years)
        return result
    except Exception as e:
        raise HTTPException(500, "Rolling backtest failed: %s" % str(e))


@app.get("/backtest/rolling/status")
def rolling_backtest_status():
    """Check if rolling backtest is in progress."""
    return get_rolling_backtest_status()


@app.get("/backtest/history")
def backtest_history():
    """Return all past backtest results."""
    return {"results": load_backtest_history()}


@app.get("/portfolio")
def portfolio(
    stocks: int = Query(10, ge=3, le=30, description="Number of stocks in portfolio"),
):
    """Build a diversified portfolio from top scored stocks."""
    if RESULTS_FILE.exists():
        data = json.loads(RESULTS_FILE.read_text())
        ranked = data.get("top", [])
    else:
        config = load_config()
        config["top_n"] = 50
        data = run_scan(config)
        ranked = data.get("top", [])

    if not ranked:
        raise HTTPException(404, "No scan results. Run /scan first.")

    # Enrich with risk data for portfolio builder
    config = load_config()
    enriched = []
    for s in ranked:
        detail = get_stock_detail(s["ticker"], config)
        if detail:
            detail["composite_score"] = s.get("composite_score")
            enriched.append(detail)
        else:
            enriched.append(s)

    result = build_portfolio(enriched, target_size=stocks)
    return result


@app.get("/fmp/status")
def fmp_status():
    """Show FMP data fetch progress."""
    return get_fetch_status()


@app.get("/fmp/fetch")
def fmp_fetch(limit: int = Query(50, ge=1, le=200)):
    """Trigger fetching FMP data for up to N tickers."""
    tickers = get_sp500_tickers(cache_hours=168)
    result = fetch_all_fundamentals(tickers, limit=limit)
    return result


@app.get("/fmp/stock/{ticker}")
def fmp_stock(ticker: str):
    """Show cached FMP data for one ticker."""
    data = get_cached_fundamentals(ticker.upper())
    if not data:
        raise HTTPException(404, "No FMP data cached for %s" % ticker.upper())
    return data


@app.get("/accuracy")
def accuracy():
    """Get historical signal accuracy analysis."""
    try:
        return get_accuracy()
    except Exception as e:
        raise HTTPException(500, "Accuracy analysis failed: %s" % str(e))


@app.get("/accuracy/snapshot")
def accuracy_snapshot(strategy: str = Query("balanced")):
    """Take a snapshot of current signals for accuracy tracking."""
    try:
        return take_snapshot(strategy=strategy)
    except Exception as e:
        raise HTTPException(500, "Snapshot failed: %s" % str(e))


@app.get("/streaks")
def all_streaks():
    """Get all current streak data."""
    try:
        return {"streaks": get_all_streaks()}
    except Exception as e:
        raise HTTPException(500, "Failed to get streaks: %s" % str(e))


@app.get("/streaks/{ticker}")
def ticker_streak(ticker: str):
    """Get streak info for a specific ticker."""
    try:
        days, first_seen, last_seen = get_streak(ticker.upper())
        return {
            "ticker": ticker.upper(),
            "consecutive_days": days,
            "first_seen": first_seen,
            "last_seen": last_seen,
        }
    except Exception as e:
        raise HTTPException(500, "Failed to get streak: %s" % str(e))


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("src.api:app", host="0.0.0.0", port=8000, reload=True)
