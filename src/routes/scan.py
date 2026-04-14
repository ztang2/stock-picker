"""Scan routing — stock screening and signal endpoints."""

import json
import logging
import threading
import time
from pathlib import Path
from typing import Optional

import pandas as pd
from fastapi import APIRouter, Depends, HTTPException, Query

from ..pipeline import run_scan, get_stock_detail, get_all_sectors
from ..earnings import get_earnings_info
from ..strategies import get_strategy, list_strategies
from ..alerts import check_alerts, get_alert_history, generate_morning_briefing
from ..accuracy import get_accuracy, take_snapshot
from ..streak_tracker import get_all_streaks, get_streak
from ..snapshot_verify import run_verification, format_verification_report
from .deps import verify_api_key, load_config, RESULTS_FILE, DATA_DIR, logger

router = APIRouter(tags=["scan"])

# Global scan status tracking
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


@router.get("/scan")
def scan(
    sector: Optional[str] = Query(None, description="Filter by sector (e.g. Technology)"),
    min_cap: Optional[float] = Query(None, description="Minimum market cap (e.g. 10e9)"),
    max_cap: Optional[float] = Query(None, description="Maximum market cap"),
    exclude: Optional[str] = Query(None, description="Comma-separated tickers to exclude"),
    strategy: str = Query("balanced", description="Strategy: conservative, balanced, aggressive"),
    sync: bool = Query(False, description="If true, block until scan completes and return results"),
    force: bool = Query(False, description="Force scan even if recent scan exists"),
    _: None = Depends(verify_api_key),
):
    """Run full scan. Default: async (returns immediately, poll /scan/status). Use sync=true to block.
    Scans are rate-limited to once per hour unless force=true."""
    # Rate limit: don't re-scan within 1 hour unless forced
    if not force:
        try:
            scan_file = DATA_DIR / "scan_results.json"
            if scan_file.exists():
                scan_age = time.time() - scan_file.stat().st_mtime
                if scan_age < 3600:  # 1 hour
                    cached = json.loads(scan_file.read_text())
                    cached["_note"] = f"Cached scan from {int(scan_age)}s ago. Use force=true to re-scan."
                    return cached
        except Exception:
            pass
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


@router.get("/scan/status")
def scan_status():
    """Check if a scan is in progress."""
    return dict(_scan_status)


@router.get("/scan/cached")
def scan_cached():
    """Return last scan results without re-running."""
    from ..scan_results_service import ScanResultsService
    data = ScanResultsService.get_latest()
    if data:
        return data
    raise HTTPException(404, "No cached results. Run /scan first.")


@router.get("/compare")
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


@router.get("/sectors")
def list_sectors():
    """List all sectors with stock counts."""
    config = load_config()
    sectors = get_all_sectors(config)
    if not sectors:
        raise HTTPException(404, "No cached data. Run /scan first to populate.")
    return {"sectors": sectors, "total": sum(sectors.values())}


@router.get("/top/{sector}")
def top_in_sector(sector: str, top_n: int = Query(10, ge=1, le=50)):
    """Top stocks in a specific sector."""
    config = load_config()
    config["top_n"] = top_n
    result = run_scan(config, sector=sector)
    return result


@router.get("/stock/{ticker}")
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


@router.get("/alerts")
def get_alerts(limit: int = Query(50, ge=1, le=200)):
    """Get current and historical alerts."""
    try:
        current = check_alerts()
    except Exception:
        current = []
    history = get_alert_history(limit)
    return {"current": current, "history": history}


@router.get("/briefing")
def morning_briefing(top_n: int = Query(20, ge=5, le=50)):
    """Get morning briefing with streak indicators."""
    try:
        briefing = generate_morning_briefing(top_n=top_n)
        return {"briefing": briefing}
    except Exception as e:
        raise HTTPException(500, "Briefing generation failed: %s" % str(e))


@router.get("/signals")
def get_signals(strategy: str = Query("balanced", description="Strategy to use")):
    """Get stocks with STRONG_BUY or BUY entry signals."""
    from ..scan_results_service import ScanResultsService
    data = ScanResultsService.get_latest()
    if not data:
        raise HTTPException(404, "No scan results. Run /scan first.")
    top = data.get("top", data.get("stocks", []))
    signals = [s for s in top if s.get("entry_signal") in ("STRONG_BUY", "BUY")]
    return {"signals": signals, "count": len(signals)}


@router.get("/scan/top/{n}")
def scan_top_n(n: int = 5):
    """Return only top N stocks from cached scan — lightweight for cron."""
    from ..scan_results_service import ScanResultsService
    scan = ScanResultsService.get_latest()
    if not scan:
        return {"error": "No cached scan"}

    all_scores = scan.get("all_scores", [])
    ranked = sorted(all_scores, key=lambda x: -x.get("composite_score", 0))[:n]

    return {
        "top": [
            {
                "rank": i + 1,
                "ticker": s.get("ticker", ""),
                "score": round(s.get("composite_score", 0), 2),
                "sector": s.get("sector", ""),
            }
            for i, s in enumerate(ranked)
        ],
        "total_stocks": len(all_scores),
        "scan_timestamp": scan.get("timestamp", ""),
    }


@router.get("/snapshots/recent")
async def snapshots_recent(days: int = 7):
    """Return last N daily snapshots for sparkline/delta data."""
    snapshot_dir = Path(__file__).parent.parent.parent / "data" / "daily_snapshots"
    if not snapshot_dir.exists():
        return []
    files = sorted(snapshot_dir.glob("*.json"), reverse=True)[:days]
    result = []
    for f in files:
        with open(f) as fh:
            data = json.load(fh)
        stocks = {}
        for s in data.get("top", []) + data.get("all_scores", []):
            stocks[s["ticker"]] = {
                "composite_score": s.get("composite_score", 0),
                "rank": s.get("rank", 999),
            }
        result.append({"date": f.stem, "stocks": stocks})
    return list(reversed(result))


@router.get("/accuracy")
def accuracy():
    """Get historical signal accuracy analysis."""
    try:
        return get_accuracy()
    except Exception as e:
        raise HTTPException(500, "Accuracy analysis failed: %s" % str(e))


@router.get("/accuracy/snapshot")
def accuracy_snapshot(strategy: str = Query("balanced")):
    """Take a snapshot of current signals for accuracy tracking."""
    try:
        return take_snapshot(strategy=strategy)
    except Exception as e:
        raise HTTPException(500, "Snapshot failed: %s" % str(e))


@router.get("/snapshots/verify")
def verify_snapshots():
    """Verify daily snapshot completeness and integrity."""
    try:
        report = run_verification()
        report["formatted"] = format_verification_report(report)
        return report
    except Exception as e:
        raise HTTPException(500, "Verification failed: %s" % str(e))


@router.get("/streaks")
def all_streaks():
    """Get all current streak data."""
    try:
        return {"streaks": get_all_streaks()}
    except Exception as e:
        raise HTTPException(500, "Failed to get streaks: %s" % str(e))


@router.get("/streaks/{ticker}")
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


@router.get("/chart/{ticker}")
async def chart_ticker(ticker: str, period: str = "3mo"):
    """Get OHLC chart data with support/resistance levels."""
    import asyncio
    import math

    def _load_chart():
        cache_path = DATA_DIR / "stock_data_cache.json"
        ticker_upper = ticker.upper()

        # Determine lookback days
        period_days = {"1mo": 30, "3mo": 90, "6mo": 180, "1y": 365, "2y": 730}
        days = period_days.get(period, 90)

        hist = None
        if cache_path.exists():
            with open(cache_path) as f:
                cache = json.load(f)
            if ticker_upper in cache:
                data = cache[ticker_upper]
                raw = pd.DataFrame(data["history"])
                raw.index = pd.to_datetime(data["history_index"], utc=True)
                cutoff = raw.index.max() - pd.Timedelta(days=days)
                raw = raw[raw.index >= cutoff]
                raw = raw[
                    raw["Close"].apply(lambda x: not (isinstance(x, float) and math.isnan(x)))
                ]
                hist = raw

        if hist is None or hist.empty:
            from ..yfinance_client import get_ticker_history

            raw = get_ticker_history(ticker_upper, period=period)
            if raw.empty:
                return None
            raw = raw[
                raw["Close"].apply(lambda x: not (isinstance(x, float) and math.isnan(x)))
            ]
            hist = raw

        if hist is None or hist.empty:
            return None

        ohlc = [
            {
                "date": str(idx.date()),
                "open": round(float(row["Open"]), 4),
                "high": round(float(row["High"]), 4),
                "low": round(float(row["Low"]), 4),
                "close": round(float(row["Close"]), 4),
            }
            for idx, row in hist.iterrows()
        ]

        from ..momentum import _support_resistance

        support, resistance = _support_resistance(hist)

        closes = hist["Close"].tolist()
        ma50 = (
            round(float(sum(closes[-50:]) / min(50, len(closes))), 4)
            if closes
            else None
        )

        return {
            "ticker": ticker_upper,
            "ohlc": ohlc,
            "support": round(support, 4) if support is not None else None,
            "resistance": round(resistance, 4) if resistance is not None else None,
            "ma50": ma50,
        }

    result = await asyncio.to_thread(_load_chart)
    if result is None:
        raise HTTPException(status_code=404, detail=f"No data found for {ticker}")
    return result
