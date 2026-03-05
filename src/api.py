"""FastAPI server for the stock screener."""

import logging
import json
import os
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import Optional, List

import pandas as pd
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
from .universe import get_sp500_tickers, get_universe_tickers
from .accuracy import get_accuracy, take_snapshot
from .streak_tracker import get_all_streaks, get_streak
from .optimizer import run_optimization, get_optimization_status, load_optimization_results, apply_optimization
from .model_report import generate_factor_report, format_report_discord
from .auto_optimize import run_monthly_optimization, get_optimization_history
from .sec_edgar import get_sec_financials
from .dcf_valuation import run_dcf, get_dcf_summary
from .comps_analysis import run_comps
from .thesis_tracker import record_thesis, get_thesis, check_all_theses, close_thesis
from .earnings_analysis import analyze_earnings

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
                "top": result.get("top", result.get("stocks", []))[:20],
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
    top = data.get("top", data.get("stocks", []))
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
        ranked = data.get("top", data.get("stocks", []))
    else:
        config = load_config()
        config["top_n"] = 50
        data = run_scan(config)
        ranked = data.get("top", data.get("stocks", []))

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
    
    top = {s["ticker"]: s for s in scan_data.get("top", scan_data.get("stocks", []))}
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


@app.get("/portfolio/check")
def portfolio_check():
    """Comprehensive post-market check: validation, holdings, rebalance, snapshots.
    
    Consolidates all post-market logic into a single defensive endpoint.
    Each section is wrapped in try/except so one failure doesn't kill the whole check.
    """
    from pathlib import Path
    import yfinance as yf
    from .validation import validate_predictions, format_validation_report
    from .snapshot_verify import run_verification, format_verification_report
    from .rebalance import (
        load_holdings, load_rebalance_state, save_rebalance_state,
        update_signal_streaks, evaluate_swaps, format_rebalance_report
    )
    
    response = {}
    
    # --- Validation Section ---
    try:
        validation_report = validate_predictions()
        response["validation"] = {
            "report": format_validation_report(validation_report),
            "raw": validation_report,
        }
    except Exception as e:
        logger.error("Validation check failed", exc_info=True)
        response["validation"] = {
            "error": f"Validation failed: {e}",
            "report": "⚠️ Validation check failed — see error field"
        }
    
    # --- Load scan results with defensive key access ---
    scan_data = None
    if RESULTS_FILE.exists():
        try:
            scan_data = json.loads(RESULTS_FILE.read_text())
        except Exception as e:
            logger.error("Failed to load scan results", exc_info=True)
            response["scan_data_error"] = f"Failed to load scan results: {e}"
    
    # Defensive key access: check both 'top' and 'stocks' keys
    top_stocks = []
    if scan_data:
        top_stocks = scan_data.get('top', scan_data.get('stocks', []))
    
    sanity_warnings = scan_data.get("sanity_warnings", []) if scan_data else []
    
    # --- Holdings Section ---
    holdings_list = []
    holdings_dict = {}
    try:
        # Load holdings from trades.md
        trades_file = Path.home() / "clawd" / "memory" / "trades.md"
        holdings_dict = {}
        
        if trades_file.exists():
            content = trades_file.read_text()
            # Parse markdown table for "Active Positions (Stock Picker)"
            in_picker_section = False
            for line in content.split("\n"):
                line = line.strip()
                if "Active Positions (Stock Picker)" in line:
                    in_picker_section = True
                    continue
                elif line.startswith("## ") and in_picker_section:
                    # End of section
                    break
                
                if in_picker_section and line.startswith("- **"):
                    # Parse: - **EQT** 12.255 shares @ $57.12 — bought 2/17
                    try:
                        parts = line.split("**")
                        if len(parts) >= 3:
                            ticker = parts[1].strip()
                            rest = parts[2].strip()
                            # Extract shares and price
                            if " shares @ $" in rest or " shares @ ~$" in rest:
                                shares_part = rest.split(" shares")[0].strip()
                                price_part = rest.split("@ ")[1].split(" ")[0].replace("$", "").replace("~", "")
                                try:
                                    shares = float(shares_part)
                                    entry_price = float(price_part)
                                    holdings_dict[ticker] = {
                                        "shares": shares,
                                        "entry_price": entry_price,
                                    }
                                except ValueError:
                                    pass
                    except Exception:
                        pass
        
        # Enrich with current prices and scores
        if holdings_dict:
            tickers = list(holdings_dict.keys())
            # Batch fetch prices
            prices = {}
            try:
                data = yf.download(tickers, period="2d", progress=False, threads=True)
                if data is not None and not data.empty:
                    close = data["Close"]
                    if isinstance(close, pd.Series):
                        if len(close) >= 1:
                            prices[tickers[0]] = float(close.iloc[-1])
                    else:
                        for ticker in tickers:
                            if ticker in close.columns:
                                val = close[ticker].iloc[-1]
                                if pd.notna(val):
                                    prices[ticker] = float(val)
                    
                    # Get today's change
                    if len(data) >= 2:
                        prev_close = data["Close"].iloc[-2] if isinstance(data["Close"], pd.Series) else data["Close"].iloc[-2]
                        curr_close = data["Close"].iloc[-1] if isinstance(data["Close"], pd.Series) else data["Close"].iloc[-1]
                        for ticker in tickers:
                            if ticker in holdings_dict:
                                if isinstance(prev_close, pd.Series):
                                    prev = prev_close
                                    curr = curr_close
                                else:
                                    prev = prev_close[ticker] if ticker in prev_close else None
                                    curr = curr_close[ticker] if ticker in curr_close else None
                                
                                if prev is not None and curr is not None and pd.notna(prev) and pd.notna(curr):
                                    holdings_dict[ticker]["today_change_pct"] = round(((float(curr) - float(prev)) / float(prev)) * 100, 2)
            except Exception as e:
                logger.warning("Failed to fetch prices: %s", e)
            
            # Build holdings list with scores from scan (check all_scores too)
            top_dict = {s.get("ticker"): s for s in top_stocks}
            all_scores_dict = {}
            if scan_data and scan_data.get("all_scores"):
                all_scores_dict = {s.get("ticker"): s for s in scan_data.get("all_scores", [])}
            
            for ticker, h in holdings_dict.items():
                entry_price = h.get("entry_price", 0)
                current_price = prices.get(ticker, entry_price)
                total_return_pct = ((current_price - entry_price) / entry_price * 100) if entry_price > 0 else 0
                
                # Try top list first, then all_scores
                score_data = top_dict.get(ticker, all_scores_dict.get(ticker, {}))
                
                # Handle both 'composite_score' (from top) and 'composite' (from all_scores)
                score = score_data.get("composite_score", score_data.get("composite", 0))
                signal = score_data.get("entry_signal", score_data.get("signal", "N/A"))
                
                holdings_list.append({
                    "ticker": ticker,
                    "entry_price": round(entry_price, 2),
                    "current_price": round(current_price, 2),
                    "today_change_pct": h.get("today_change_pct", 0),
                    "total_return_pct": round(total_return_pct, 2),
                    "score": score,
                    "signal": signal,
                })
        
        response["holdings"] = holdings_list
    except Exception as e:
        logger.error("Holdings check failed", exc_info=True)
        response["holdings"] = []
        response["holdings_error"] = f"Holdings check failed: {e}"
    
    # --- Rebalance Section ---
    try:
        if scan_data and top_stocks:
            top_dict = {s.get("ticker"): s for s in top_stocks}
            holdings = {h["ticker"]: {"shares": holdings_dict.get(h["ticker"], {}).get("shares", 0), 
                                      "entry_price": h["entry_price"], 
                                      "entry_date": "2026-02-17"} 
                       for h in holdings_list}
            state = load_rebalance_state()
            
            held_signals = {t: top_dict.get(t, {}) for t in holdings}
            candidate_signals = {t: s for t, s in top_dict.items() if t not in holdings}
            
            state = update_signal_streaks(state, held_signals, candidate_signals)
            save_rebalance_state(state)
            
            suggestions = evaluate_swaps(holdings, state, held_signals, candidate_signals)
            report = format_rebalance_report(suggestions, holdings)
            
            response["rebalance"] = {
                "report": report,
                "suggestions": suggestions,
            }
        else:
            response["rebalance"] = {
                "report": "⚠️ No scan data available for rebalance check",
                "suggestions": [],
            }
    except Exception as e:
        logger.error("Rebalance check failed", exc_info=True)
        response["rebalance"] = {
            "error": f"Rebalance check failed: {e}",
            "report": "⚠️ Rebalance check failed — see error field",
            "suggestions": [],
        }
    
    # --- Snapshots Section ---
    try:
        snapshot_report = run_verification()
        response["snapshots"] = {
            "report": format_verification_report(snapshot_report),
            "status": snapshot_report.get("status", "unknown").lower(),
            "details": snapshot_report,
        }
    except Exception as e:
        logger.error("Snapshot verification failed", exc_info=True)
        response["snapshots"] = {
            "error": f"Snapshot verification failed: {e}",
            "report": "⚠️ Snapshot verification failed — see error field",
            "status": "error",
        }
    
    # --- Portfolio Summary ---
    try:
        if holdings_list:
            returns = [h["total_return_pct"] for h in holdings_list]
            avg_return = sum(returns) / len(returns)
            best = max(holdings_list, key=lambda x: x["total_return_pct"])
            worst = min(holdings_list, key=lambda x: x["total_return_pct"])
            
            response["portfolio_summary"] = {
                "avg_return": round(avg_return, 2),
                "best": f"{best['ticker']} {best['total_return_pct']:+.2f}%",
                "worst": f"{worst['ticker']} {worst['total_return_pct']:+.2f}%",
                "holdings_count": len(holdings_list),
            }
        else:
            response["portfolio_summary"] = {
                "avg_return": 0,
                "best": "N/A",
                "worst": "N/A",
                "holdings_count": 0,
            }
    except Exception as e:
        logger.error("Portfolio summary failed", exc_info=True)
        response["portfolio_summary"] = {
            "error": f"Portfolio summary failed: {e}",
        }
    
    response["sanity_warnings"] = sanity_warnings
    response["timestamp"] = datetime.now().isoformat()
    
    return response


# --- SEC EDGAR endpoints ---

@app.get("/sec/{ticker}")
def sec_data(ticker: str):
    """Get structured financial data from SEC EDGAR filings."""
    try:
        return get_sec_financials(ticker.upper())
    except Exception as e:
        raise HTTPException(500, f"SEC data fetch failed: {e}")


# --- DCF Valuation endpoints ---

@app.get("/dcf/{ticker}")
def dcf_full(ticker: str):
    """Full DCF valuation analysis."""
    try:
        return run_dcf(ticker.upper())
    except Exception as e:
        raise HTTPException(500, f"DCF analysis failed: {e}")


@app.get("/dcf/{ticker}/summary")
def dcf_summary(ticker: str):
    """Quick DCF summary: intrinsic value + margin of safety."""
    try:
        return get_dcf_summary(ticker.upper())
    except Exception as e:
        raise HTTPException(500, f"DCF summary failed: {e}")


# --- Comps Analysis endpoints ---

@app.get("/comps/{ticker}")
def comps(ticker: str, max_peers: int = Query(15, ge=3, le=30)):
    """Comparable company analysis vs sector peers."""
    try:
        return run_comps(ticker.upper(), max_peers=max_peers)
    except Exception as e:
        raise HTTPException(500, f"Comps analysis failed: {e}")


# --- Thesis Tracker endpoints ---

from pydantic import BaseModel

class ThesisCreate(BaseModel):
    thesis: str
    entry_price: Optional[float] = None
    target_price: Optional[float] = None
    stop_loss: Optional[float] = None
    conditions: Optional[List[str]] = None
    time_horizon: Optional[str] = None


@app.post("/thesis/{ticker}")
def create_thesis(ticker: str, body: ThesisCreate, _: None = Depends(verify_api_key)):
    """Record an investment thesis."""
    try:
        return record_thesis(
            ticker.upper(),
            thesis=body.thesis,
            entry_price=body.entry_price,
            target_price=body.target_price,
            stop_loss=body.stop_loss,
            conditions=body.conditions,
            time_horizon=body.time_horizon,
        )
    except Exception as e:
        raise HTTPException(500, f"Failed to record thesis: {e}")


@app.get("/thesis/check")
def thesis_check():
    """Check all active investment theses."""
    try:
        return {"results": check_all_theses()}
    except Exception as e:
        raise HTTPException(500, f"Thesis check failed: {e}")


@app.get("/thesis/{ticker}")
def thesis_get(ticker: str):
    """Get current thesis and status for a ticker."""
    result = get_thesis(ticker.upper())
    if not result:
        raise HTTPException(404, f"No thesis found for {ticker.upper()}")
    return result


# --- Earnings Analysis endpoint ---

@app.get("/earnings/{ticker}/analysis")
def earnings_deep_analysis(ticker: str):
    """Deep earnings analysis: trends, beat/miss history, quality score."""
    try:
        return analyze_earnings(ticker.upper())
    except Exception as e:
        raise HTTPException(500, f"Earnings analysis failed: {e}")


# ── Alpaca Paper Trading ─────────────────────────────────────────────
from .alpaca_trader import (
    get_account as alpaca_get_account,
    get_positions as alpaca_get_positions,
    get_orders as alpaca_get_orders,
    sync_with_holdings as alpaca_sync,
    get_performance as alpaca_performance,
)


@app.get("/alpaca/account")
def alpaca_account():
    """Paper trading account info."""
    try:
        return alpaca_get_account()
    except Exception as e:
        raise HTTPException(500, f"Alpaca error: {e}")


@app.get("/alpaca/positions")
def alpaca_positions():
    """Paper trading positions."""
    try:
        return alpaca_get_positions()
    except Exception as e:
        raise HTTPException(500, f"Alpaca error: {e}")


@app.get("/alpaca/orders")
def alpaca_orders(status: str = "all", limit: int = 50):
    """Paper trading orders."""
    try:
        return alpaca_get_orders(status, limit)
    except Exception as e:
        raise HTTPException(500, f"Alpaca error: {e}")


@app.post("/alpaca/sync")
def alpaca_sync_holdings(_=Depends(verify_api_key)):
    """Sync paper portfolio with holdings.json."""
    try:
        return alpaca_sync()
    except Exception as e:
        raise HTTPException(500, f"Alpaca sync error: {e}")


@app.get("/alpaca/performance")
def alpaca_perf():
    """Paper trading performance."""
    try:
        return alpaca_performance()
    except Exception as e:
        raise HTTPException(500, f"Alpaca error: {e}")


# === Economic Data (FRED) ===

@app.get("/economic/summary")
def economic_summary():
    """Get FRED economic data summary with composite score."""
    from .fred_data import get_economic_summary
    return get_economic_summary()


@app.get("/economic/data")
def economic_data(refresh: bool = Query(False)):
    """Get raw FRED economic data."""
    from .fred_data import fetch_fred_data
    return fetch_fred_data(force_refresh=refresh)


# === Risk Management ===

@app.get("/risk/summary")
def risk_summary():
    """Full portfolio risk summary: stop-losses, position limits, P&L."""
    from .risk_manager import get_portfolio_summary
    from .rebalance import load_holdings
    
    holdings = load_holdings()
    
    # Add NFLX as extra holding (non-picker)
    extra = {
        "NFLX": {"shares": 40, "entry_price": 80.51, "entry_date": "2025-01-01"},
    }
    
    return get_portfolio_summary(holdings, extra_holdings=extra)


@app.get("/risk/stop-losses")
def risk_stop_losses():
    """Check stop-loss status for all positions."""
    from .risk_manager import check_stop_losses
    from .rebalance import load_holdings
    
    holdings = load_holdings()
    # Include NFLX
    holdings["NFLX"] = {"shares": 40, "entry_price": 80.51, "entry_date": "2025-01-01"}
    
    return {"alerts": check_stop_losses(holdings)}


@app.get("/risk/positions")
def risk_positions():
    """Check position size limits."""
    from .risk_manager import check_position_limits
    from .rebalance import load_holdings
    
    holdings = load_holdings()
    extra = {
        "NFLX": {"shares": 40, "entry_price": 80.51, "entry_date": "2025-01-01"},
    }
    
    return {"positions": check_position_limits(holdings, extra_holdings=extra)}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("src.api:app", host="0.0.0.0", port=8000, reload=True)
