"""FastAPI server for the stock screener."""

import logging
import json
import os
import threading
import time
from pathlib import Path
from typing import Optional, List

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Query, Header, Depends
from fastapi.responses import JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles

# Load .env file for API_KEY
load_dotenv()

from .pipeline import run_scan, get_stock_detail, get_all_sectors, load_config, RESULTS_FILE, DATA_DIR
from .backtest import run_backtest, load_backtest_history, run_rolling_backtest, get_rolling_backtest_status, load_rolling_backtest_cache
from .earnings import get_earnings_info
from .portfolio import build_portfolio
from .alerts import check_alerts, get_alert_history, generate_morning_briefing
from .momentum import compute_momentum
from .strategies import list_strategies, get_strategy
# FMP removed — yfinance is sole data source. SEC EDGAR planned for future.
from .universe import get_sp500_tickers
from .accuracy import get_accuracy, take_snapshot
from .streak_tracker import get_all_streaks, get_streak
from .optimizer import run_optimization, get_optimization_status, load_optimization_results, apply_optimization
from .model_report import generate_factor_report, format_report_discord
from .auto_optimize import run_monthly_optimization, get_optimization_history

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger(__name__)


def verify_api_key(x_api_key: Optional[str] = Header(None)):
    """Check API key for mutating endpoints. If no API_KEY in .env, skip auth (backward compatible)."""
    required_key = os.getenv("API_KEY")
    if required_key is None:
        # No API key configured, skip auth
        return
    if x_api_key != required_key:
        raise HTTPException(status_code=401, detail="Invalid or missing API key")


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


_scan_status = {"running": False, "started_at": None, "finished_at": None, "error": None, "strategy": None}


def _run_scan_background(config, sector, min_cap, max_cap, exclude_tickers, strategy):
    """Run scan in background thread."""
    global _scan_status
    try:
        _scan_status["running"] = True
        _scan_status["started_at"] = time.strftime("%Y-%m-%dT%H:%M:%S")
        _scan_status["finished_at"] = None
        _scan_status["error"] = None
        _scan_status["strategy"] = strategy
        run_scan(
            config,
            sector=sector,
            min_cap=min_cap,
            max_cap=max_cap,
            exclude_tickers=exclude_tickers,
            strategy=strategy,
        )
        _scan_status["finished_at"] = time.strftime("%Y-%m-%dT%H:%M:%S")
    except Exception as e:
        _scan_status["error"] = str(e)
        logger.error("Background scan failed: %s", e, exc_info=True)
    finally:
        _scan_status["running"] = False


@app.get("/scan")
def scan(
    sector: Optional[str] = Query(None, description="Filter by sector (e.g. Technology)"),
    min_cap: Optional[float] = Query(None, description="Minimum market cap (e.g. 10e9)"),
    max_cap: Optional[float] = Query(None, description="Maximum market cap"),
    exclude: Optional[str] = Query(None, description="Comma-separated tickers to exclude"),
    strategy: str = Query("balanced", description="Strategy: conservative, balanced, aggressive"),
    sync: bool = Query(False, description="If true, block until scan completes and return results"),
    _: None = Depends(verify_api_key),
):
    """Run full scan. Default: async (returns immediately, poll /scan/status). Use sync=true to block."""
    config = load_config()
    exclude_list = [t.strip().upper() for t in exclude.split(",")] if exclude else None

    if sync:
        result = run_scan(
            config,
            sector=sector,
            min_cap=min_cap,
            max_cap=max_cap,
            exclude_tickers=exclude_list,
            strategy=strategy,
        )
        return result

    if _scan_status["running"]:
        return {"status": "already_running", "started_at": _scan_status["started_at"], "strategy": _scan_status["strategy"]}

    t = threading.Thread(
        target=_run_scan_background,
        args=(config, sector, min_cap, max_cap, exclude_list, strategy),
        daemon=True,
    )
    t.start()
    return {"status": "started", "strategy": strategy}


@app.get("/scan/status")
def scan_status():
    """Check if a scan is in progress."""
    return dict(_scan_status)


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
    """Detailed breakdown for one stock with earnings."""
    config = load_config()
    result = get_stock_detail(ticker, config)
    if not result:
        raise HTTPException(404, "No data for %s" % ticker.upper())

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


# FMP endpoints removed — data source deprecated


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


@app.get("/snapshots/verify")
def verify_snapshots():
    """Verify daily snapshot completeness and integrity."""
    try:
        from .snapshot_verify import run_verification, format_verification_report
        report = run_verification()
        report["formatted"] = format_verification_report(report)
        return report
    except Exception as e:
        raise HTTPException(500, "Verification failed: %s" % str(e))


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


@app.get("/optimize/monthly")
def optimize_monthly(
    strategy: str = Query("balanced", description="Strategy to optimize"),
    months_back: int = Query(6, ge=1, le=12),
):
    """Run monthly weight optimization."""
    try:
        result = run_monthly_optimization(strategy=strategy, months_back=months_back)
        return result
    except Exception as e:
        raise HTTPException(500, "Optimization failed: %s" % str(e))


@app.get("/optimize/history")
def optimize_history():
    """Return optimization changelog."""
    return {"history": get_optimization_history()}


## ML Model endpoints

from .ml_model import train_model as _ml_train, predict_scores as _ml_predict, get_model_metrics as _ml_metrics, compare_with_rules as _ml_compare


@app.get("/ml/train")
def ml_train(months_history: int = Query(12, ge=1, le=36)):
    """Train ML model."""
    try:
        return _ml_train(months_history=months_history)
    except Exception as e:
        logger.error("ML training failed", exc_info=True)
        raise HTTPException(500, f"ML training failed: {e}")


@app.get("/ml/predict")
def ml_predict(tickers: Optional[str] = Query(None, description="Comma-separated tickers")):
    """Get ML predictions for stocks."""
    try:
        ticker_list = [t.strip().upper() for t in tickers.split(",")] if tickers else None
        return {"predictions": _ml_predict(ticker_list)}
    except Exception as e:
        raise HTTPException(500, f"ML prediction failed: {e}")


@app.get("/ml/metrics")
def ml_metrics():
    """Get ML model metrics."""
    return _ml_metrics()


@app.get("/ml/compare")
def ml_compare():
    """Compare ML vs rule-based picks."""
    try:
        return _ml_compare()
    except Exception as e:
        raise HTTPException(500, f"ML comparison failed: {e}")


@app.get("/optimize/run")
def optimize_run(strategy: str = Query("balanced")):
    """Run weight optimization."""
    try:
        result = run_optimization(strategy=strategy)
        return result
    except Exception as e:
        raise HTTPException(500, "Optimization failed: %s" % str(e))


@app.get("/optimize/status")
def optimize_status():
    """Check optimization progress."""
    return get_optimization_status()


@app.get("/optimize/results")
def optimize_results():
    """Get cached optimization results."""
    results = load_optimization_results()
    if not results:
        raise HTTPException(404, "No optimization results. Run /optimize/run first.")
    return results


@app.get("/optimize/apply")
def optimize_apply(dry_run: bool = Query(True), _: None = Depends(verify_api_key)):
    """Apply optimization results to config."""
    try:
        return apply_optimization(dry_run=dry_run)
    except Exception as e:
        raise HTTPException(500, "Apply failed: %s" % str(e))


@app.get("/report/factors")
def report_factors(months: int = Query(3, ge=1, le=12), format: str = Query("json")):
    """Get factor attribution report."""
    try:
        report = generate_factor_report(months=months)
        if format == "discord":
            return {"text": format_report_discord(report)}
        return report
    except Exception as e:
        raise HTTPException(500, "Report failed: %s" % str(e))


# --- Rebalance endpoints ---

@app.get("/rebalance/status")
def rebalance_status(_: None = Depends(verify_api_key)):
    """Get current rebalance state and holdings."""
    from .rebalance import load_holdings, load_rebalance_state
    return {
        "holdings": load_holdings(),
        "state": load_rebalance_state(),
    }


@app.get("/rebalance/check")
def rebalance_check(_: None = Depends(verify_api_key)):
    """Run rebalance evaluation against latest scan results."""
    from .rebalance import (
        load_holdings, load_rebalance_state, save_rebalance_state,
        update_signal_streaks, evaluate_swaps, format_rebalance_report
    )
    
    scan_data = None
    if RESULTS_FILE.exists():
        scan_data = json.loads(RESULTS_FILE.read_text())
    if not scan_data:
        raise HTTPException(400, "No scan results. Run /scan first.")
    
    top = {s["ticker"]: s for s in scan_data.get("top", [])}
    holdings = load_holdings()
    state = load_rebalance_state()
    
    held_signals = {t: top[t] for t in holdings if t in top}
    candidate_signals = {t: s for t, s in top.items() if t not in holdings}
    
    state = update_signal_streaks(state, held_signals, candidate_signals)
    save_rebalance_state(state)
    
    suggestions = evaluate_swaps(holdings, state, held_signals, candidate_signals)
    report = format_rebalance_report(suggestions, holdings)
    
    return {
        "suggestions": suggestions,
        "report": report,
        "holdings_count": len(holdings),
    }


# --- Validation endpoints ---

@app.get("/validation/run")
def validation_run():
    """Run prediction validation (compare yesterday's predictions with today's reality)."""
    from .validation import validate_predictions, format_validation_report
    report = validate_predictions()
    return {
        "report": report,
        "formatted": format_validation_report(report),
    }


@app.get("/validation/summary")
def validation_summary(days: int = Query(7, ge=1, le=90)):
    """Get validation summary over recent days."""
    from .validation import get_validation_summary
    return get_validation_summary(days=days)


# --- Smart money endpoints ---

@app.get("/insider/{ticker}")
def insider_analysis(ticker: str):
    """Get analyst revision + insider trading analysis for a ticker."""
    import yfinance as yf
    from .insider import get_combined_smart_money_score
    try:
        t = yf.Ticker(ticker.upper())
        return get_combined_smart_money_score(t)
    except Exception as e:
        raise HTTPException(500, f"Analysis failed: {e}")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("src.api:app", host="0.0.0.0", port=8000, reload=True)
