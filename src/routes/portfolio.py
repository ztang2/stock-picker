"""Portfolio management endpoints."""

import json
import logging
import os
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import Optional

import pandas as pd
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from ..yfinance_client import download as yf_download

from ..pipeline import run_scan, get_stock_detail
from ..portfolio import build_portfolio
from ..accuracy import get_accuracy, take_snapshot
from ..rebalance import (
    load_holdings,
    save_holdings,
    load_rebalance_state,
    save_rebalance_state,
    update_signal_streaks,
    evaluate_swaps,
    format_rebalance_report,
)
from ..risk_manager import get_portfolio_summary, check_ceasefire_signals
from .. import closed_holdings as closed_holdings_svc
from ..position_decay import check_position_decay, summarize as decay_summarize
from ..validation import validate_predictions, format_validation_report
from ..snapshot_verify import run_verification, format_verification_report
from ..position_sizing import (
    get_single_ticker_sizing,
    get_portfolio_sizing,
    get_rebalance_suggestions,
)
from ..diversification import compute_diversification, compute_correlation, compute_whatif
from .deps import load_config, RESULTS_FILE, DATA_DIR, logger, verify_api_key

router = APIRouter(tags=["portfolio"])

# Global robin report status tracking
_robin_status = {"running": False, "started_at": None, "finished_at": None, "error": None, "cache_age_seconds": None}
ROBIN_CACHE_FILE = DATA_DIR / "robin_report_cache.json"


def _compute_robin_report():
    """Internal function to compute the robin report (the actual logic from robin_report endpoint).

    This is extracted so it can be called both synchronously and from a background thread.
    """
    holdings_data = load_holdings()

    # --- Holdings with live prices + P&L + rank ---
    # Load cached scan for ranks
    from ..scan_results_service import ScanResultsService
    scan = ScanResultsService.get_latest() or {}

    all_scores = scan.get("all_scores", [])
    ranked = (
        sorted(all_scores, key=lambda x: -x.get("composite_score", 0))
        if isinstance(all_scores, list)
        else []
    )

    # Build ticker→rank+score map
    rank_map = {}
    for i, s in enumerate(ranked):
        rank_map[s.get("ticker", "")] = {
            "rank": i + 1,
            "score": round(s.get("composite_score", 0), 2),
        }

    all_holdings = dict(holdings_data)

    # Fetch live prices (fallback to 5d for weekends/holidays)
    tickers_str = " ".join(all_holdings.keys())
    live_prices = {t: None for t in all_holdings}
    for period in ["1d", "5d"]:
        try:
            live_data = yf_download(tickers_str, period=period, progress=False)
            if len(all_holdings) == 1:
                t = list(all_holdings.keys())[0]
                if len(live_data) > 0:
                    live_prices[t] = float(live_data["Close"].iloc[-1])
            else:
                for t in all_holdings:
                    try:
                        val = float(live_data["Close"][t].iloc[-1])
                        if val and val > 0:
                            live_prices[t] = val
                    except:
                        pass
            # If we got most prices, stop
            if sum(1 for v in live_prices.values() if v) >= len(all_holdings) * 0.5:
                break
        except:
            pass

    # Build holdings report
    positions = []
    total_value = 0
    total_cost = 0
    winners = 0
    losers = 0

    for ticker, info in all_holdings.items():
        shares = info.get("shares", 0)
        entry = info.get("entry_price", 0)
        price = live_prices.get(ticker)
        cost = shares * entry
        value = shares * price if price else cost
        pnl = value - cost
        pnl_pct = (pnl / cost * 100) if cost > 0 else 0

        total_value += value
        total_cost += cost
        if pnl > 0:
            winners += 1
        else:
            losers += 1

        r = rank_map.get(ticker, {})
        positions.append(
            {
                "ticker": ticker,
                "shares": shares,
                "entry_price": entry,
                "current_price": round(price, 2) if price else None,
                "pnl": round(pnl, 2),
                "pnl_pct": round(pnl_pct, 2),
                "rank": r.get("rank", "N/A"),
                "score": r.get("score", "N/A"),
                "entry_date": info.get("entry_date", ""),
            }
        )

    positions.sort(key=lambda x: -x["pnl"])

    # --- Top 5 from scan ---
    top5 = []
    for s in ranked[:5]:
        top5.append(
            {
                "rank": ranked.index(s) + 1,
                "ticker": s.get("ticker", ""),
                "score": round(s.get("composite_score", 0), 2),
                "sector": s.get("sector", ""),
            }
        )

    # --- Risk alerts ---
    risk_alerts = []

    # Trailing stops
    try:
        trailing_file = os.path.join(DATA_DIR, "trailing_stops.json")
        if os.path.exists(trailing_file):
            with open(trailing_file) as f:
                ts_data = json.load(f)
            for ticker, ts_info in ts_data.items():
                if ticker in all_holdings and live_prices.get(ticker):
                    high = ts_info.get("high_price", live_prices[ticker])
                    drop = (live_prices[ticker] - high) / high * 100 if high > 0 else 0
                    if drop <= -10:
                        risk_alerts.append(
                            f"🔴 {ticker} trailing stop: -{abs(drop):.1f}% from peak ${high:.2f} → ${live_prices[ticker]:.2f}"
                        )
    except:
        pass

    # Position concentration
    for p in positions:
        if total_value > 0:
            weight = (
                (p["shares"] * (p["current_price"] or p["entry_price"]))
                / total_value
                * 100
            )
            if weight > 20:
                risk_alerts.append(f"⚠️ {p['ticker']} overweight: {weight:.1f}% (limit 20%)")

    # Ceasefire
    try:
        cf_signals = check_ceasefire_signals()
        if cf_signals.get("urgency") in ("HIGH", "CRITICAL"):
            risk_alerts.append(
                f"🚨 CEASEFIRE WARNING ({cf_signals['urgency']}): {'; '.join(cf_signals.get('signals', []))}"
            )
    except:
        pass

    total_pnl = total_value - total_cost
    total_pnl_pct = (total_pnl / total_cost * 100) if total_cost > 0 else 0

    return {
        "report_type": "post_market",
        "generated_at": datetime.now().isoformat(),
        "scan_timestamp": scan.get("timestamp", ""),
        "portfolio": {
            "total_value": round(total_value, 2),
            "total_cost": round(total_cost, 2),
            "total_pnl": round(total_pnl, 2),
            "total_pnl_pct": round(total_pnl_pct, 2),
            "positions_count": len(positions),
            "winners": winners,
            "losers": losers,
        },
        "positions": positions,
        "top5_pipeline": top5,
        "risk_alerts": risk_alerts,
        "note": "ALL numbers are pre-computed. Report them exactly as shown.",
    }


def _run_robin_background():
    """Run robin report computation in background thread."""
    global _robin_status
    try:
        _robin_status["running"] = True
        _robin_status["started_at"] = time.strftime("%Y-%m-%dT%H:%M:%S")
        _robin_status["finished_at"] = None
        _robin_status["error"] = None

        # Compute the report
        report = _compute_robin_report()

        # Save to cache with timestamp
        cache_data = {
            "timestamp": datetime.now().isoformat(),
            "data": report,
        }
        ROBIN_CACHE_FILE.parent.mkdir(exist_ok=True)
        with open(ROBIN_CACHE_FILE, "w") as f:
            json.dump(cache_data, f, indent=2)

        _robin_status["finished_at"] = time.strftime("%Y-%m-%dT%H:%M:%S")
    except Exception as e:
        _robin_status["error"] = str(e)
        logger.error("Background robin report computation failed: %s", e, exc_info=True)
    finally:
        _robin_status["running"] = False


def _get_cached_robin_report():
    """Load robin report from cache if available, with cache age info."""
    if not ROBIN_CACHE_FILE.exists():
        return None

    try:
        with open(ROBIN_CACHE_FILE) as f:
            cache_data = json.load(f)

        # Calculate cache age
        cache_timestamp = cache_data.get("timestamp")
        if cache_timestamp:
            cache_dt = datetime.fromisoformat(cache_timestamp)
            cache_age = (datetime.now() - cache_dt).total_seconds()
            _robin_status["cache_age_seconds"] = int(cache_age)

        report = cache_data.get("data", {})
        # Add cache metadata
        report["_cached"] = True
        report["_cache_timestamp"] = cache_timestamp
        report["_cache_age_seconds"] = _robin_status.get("cache_age_seconds")

        return report
    except Exception as e:
        logger.warning("Failed to load robin report cache: %s", e)
        return None


@router.get("/portfolio")
def portfolio(
    stocks: int = Query(10, ge=3, le=30, description="Number of stocks in portfolio"),
):
    """Build a diversified portfolio from top scored stocks."""
    from ..scan_results_service import ScanResultsService
    cached_data = ScanResultsService.get_latest()
    if cached_data:
        data = cached_data
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


@router.get("/portfolio/check")
def portfolio_check():
    """Comprehensive post-market check: validation, holdings, rebalance, snapshots.

    Consolidates all post-market logic into a single defensive endpoint.
    Each section is wrapped in try/except so one failure doesn't kill the whole check.
    """

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
            "report": "⚠️ Validation check failed — see error field",
        }

    # --- Load scan results with defensive key access ---
    scan_data = None
    try:
        from ..scan_results_service import ScanResultsService
        scan_data = ScanResultsService.get_latest()
    except Exception as e:
        logger.error("Failed to load scan results", exc_info=True)
        response["scan_data_error"] = f"Failed to load scan results: {e}"

    # Defensive key access: check both 'top' and 'stocks' keys
    top_stocks = []
    if scan_data:
        top_stocks = scan_data.get("top", scan_data.get("stocks", []))

    sanity_warnings = scan_data.get("sanity_warnings", []) if scan_data else []

    # --- Holdings Section ---
    holdings_list = []
    holdings_dict = {}
    try:
        # Load holdings from canonical source (holdings.json)
        holdings_dict = load_holdings()

        # Enrich with current prices and scores
        if holdings_dict:
            tickers = list(holdings_dict.keys())
            # Batch fetch prices
            prices = {}
            try:
                data = yf_download(
                    tickers, period="2d", progress=False, threads=True
                )
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
                        prev_close = (
                            data["Close"].iloc[-2]
                            if isinstance(data["Close"], pd.Series)
                            else data["Close"].iloc[-2]
                        )
                        curr_close = (
                            data["Close"].iloc[-1]
                            if isinstance(data["Close"], pd.Series)
                            else data["Close"].iloc[-1]
                        )
                        for ticker in tickers:
                            if ticker in holdings_dict:
                                if isinstance(prev_close, pd.Series):
                                    prev = prev_close
                                    curr = curr_close
                                else:
                                    prev = (
                                        prev_close[ticker]
                                        if ticker in prev_close
                                        else None
                                    )
                                    curr = (
                                        curr_close[ticker]
                                        if ticker in curr_close
                                        else None
                                    )

                                if (
                                    prev is not None
                                    and curr is not None
                                    and pd.notna(prev)
                                    and pd.notna(curr)
                                ):
                                    holdings_dict[ticker][
                                        "today_change_pct"
                                    ] = round(
                                        ((float(curr) - float(prev)) / float(prev))
                                        * 100,
                                        2,
                                    )
            except Exception as e:
                logger.warning("Failed to fetch prices: %s", e)

            # Build holdings list with scores from scan (check all_scores too)
            top_dict = {s.get("ticker"): s for s in top_stocks}
            all_scores_dict = {}
            if scan_data and scan_data.get("all_scores"):
                all_scores_dict = {
                    s.get("ticker"): s for s in scan_data.get("all_scores", [])
                }

            for ticker, h in holdings_dict.items():
                entry_price = h.get("entry_price", 0)
                current_price = prices.get(ticker, entry_price)
                total_return_pct = (
                    ((current_price - entry_price) / entry_price * 100)
                    if entry_price > 0
                    else 0
                )

                # Try top list first, then all_scores
                score_data = top_dict.get(
                    ticker, all_scores_dict.get(ticker, {})
                )

                # Handle both 'composite_score' (from top) and 'composite' (from all_scores)
                score = score_data.get(
                    "composite_score", score_data.get("composite", 0)
                )
                signal = score_data.get("entry_signal", score_data.get("signal", "N/A"))

                holdings_list.append(
                    {
                        "ticker": ticker,
                        "entry_price": round(entry_price, 2),
                        "current_price": round(current_price, 2),
                        "today_change_pct": h.get("today_change_pct", 0),
                        "total_return_pct": round(total_return_pct, 2),
                        "score": score,
                        "signal": signal,
                    }
                )

        response["holdings"] = holdings_list
    except Exception as e:
        logger.error("Holdings check failed", exc_info=True)
        response["holdings"] = []
        response["holdings_error"] = f"Holdings check failed: {e}"

    # --- Rebalance Section ---
    try:
        if scan_data and top_stocks:
            top_dict = {s.get("ticker"): s for s in top_stocks}
            holdings = {
                h["ticker"]: {
                    "shares": holdings_dict.get(h["ticker"], {}).get("shares", 0),
                    "entry_price": h["entry_price"],
                    "entry_date": "2026-02-17",
                }
                for h in holdings_list
            }
            state = load_rebalance_state()

            held_signals = {t: top_dict.get(t, {}) for t in holdings}
            candidate_signals = {t: s for t, s in top_dict.items() if t not in holdings}

            state = update_signal_streaks(state, held_signals, candidate_signals)
            save_rebalance_state(state)

            suggestions = evaluate_swaps(
                holdings, state, held_signals, candidate_signals
            )
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


@router.get("/holdings/rank")
def holdings_rank():
    """Pre-computed holdings rank from cached scan — lightweight endpoint for Robin cron.
    Returns ONLY holdings data so the LLM doesn't need to parse 800+ stock JSON."""

    holdings_data = load_holdings()

    holding_tickers = set(holdings_data.keys())
    # Always include NFLX
    holding_tickers.add("NFLX")

    # Load cached scan
    from ..scan_results_service import ScanResultsService
    scan = ScanResultsService.get_latest()
    if not scan:
        return {"error": "No cached scan available"}

    all_scores = scan.get("all_scores", [])
    if isinstance(all_scores, list):
        ranked = sorted(all_scores, key=lambda x: -x.get("composite_score", 0))
    else:
        return {"error": "Unexpected all_scores format"}

    # Find holdings in ranked list
    results = []
    for rank_idx, stock in enumerate(ranked):
        ticker = stock.get("ticker", "")
        if ticker in holding_tickers:
            results.append(
                {
                    "ticker": ticker,
                    "rank": rank_idx + 1,
                    "composite_score": round(stock.get("composite_score", 0), 2),
                    "signal": stock.get("signal", ""),
                    "ml_signal": stock.get("ml_signal", ""),
                    "sector": stock.get("sector", ""),
                }
            )

    results.sort(key=lambda x: x["rank"])

    return {
        "holdings_ranked": results,
        "total_stocks": len(ranked),
        "scan_timestamp": scan.get("timestamp", ""),
        "note": "Ranks and scores are EXACT from cached scan. Do NOT modify these numbers.",
    }


@router.get("/robin/report")
def robin_report():
    """All-in-one endpoint for Robin cron — everything pre-computed in one call.
    Combines: holdings + rank + P&L + risk alerts + top 5 + rebalance.
    Robin doesn't need to call multiple endpoints or process large JSON.

    Serves from cache when available (with cache age metadata), non-blocking.
    """
    # Try to get from cache first
    cached_report = _get_cached_robin_report()
    if cached_report:
        return cached_report

    # If no cache, trigger background computation and return indicator
    if not _robin_status["running"]:
        t = threading.Thread(target=_run_robin_background, daemon=True)
        t.start()

    # Return empty response with status while computing
    return {
        "report_type": "post_market",
        "status": "computing",
        "message": "Robin report is being pre-computed in background. Check again in a few seconds.",
        "cache_age_seconds": _robin_status.get("cache_age_seconds"),
    }


@router.get("/robin/refresh")
def robin_refresh():
    """Force re-computation of robin report cache.

    Triggers background pre-computation immediately. Returns status.
    Non-blocking — call /robin/status to check progress.
    """
    if _robin_status["running"]:
        return {
            "status": "already_running",
            "started_at": _robin_status["started_at"],
            "message": "Robin report computation already in progress.",
        }

    t = threading.Thread(target=_run_robin_background, daemon=True)
    t.start()

    return {
        "status": "triggered",
        "message": "Robin report refresh started in background.",
        "started_at": _robin_status["started_at"],
    }


@router.get("/robin/status")
def robin_status():
    """Check robin report background computation status.

    Returns whether computation is running, when it started/finished,
    cache age, and any errors.
    """
    return {
        "running": _robin_status["running"],
        "started_at": _robin_status["started_at"],
        "finished_at": _robin_status["finished_at"],
        "error": _robin_status["error"],
        "cache_age_seconds": _robin_status.get("cache_age_seconds"),
        "cache_file_exists": ROBIN_CACHE_FILE.exists(),
    }


@router.get("/portfolio/diversification")
async def portfolio_diversification():
    """Analyze portfolio diversification."""
    from ..scan_results_service import ScanResultsService
    scan_data = ScanResultsService.get_latest() or {}
    return compute_diversification(scan_data)


@router.get("/portfolio/correlation")
async def portfolio_correlation():
    """Analyze portfolio correlation."""
    from ..scan_results_service import ScanResultsService
    scan_data = ScanResultsService.get_latest() or {}
    return compute_correlation(scan_data)


@router.get("/portfolio/whatif")
async def portfolio_whatif(ticker: str):
    """Analyze impact of adding a ticker to portfolio."""
    from ..scan_results_service import ScanResultsService
    scan_data = ScanResultsService.get_latest() or {}
    return compute_whatif(ticker, scan_data)


# --- Holdings CRUD ---

@router.get("/portfolio/holdings")
def list_holdings():
    return {"holdings": load_holdings()}


class HoldingCreate(BaseModel):
    shares: float = Field(..., gt=0)
    entry_price: float = Field(..., gt=0)
    entry_date: Optional[str] = None
    entry_score: Optional[float] = None
    note: Optional[str] = None


class HoldingUpdate(BaseModel):
    shares: Optional[float] = Field(None, gt=0)
    entry_price: Optional[float] = Field(None, gt=0)
    entry_date: Optional[str] = None
    entry_score: Optional[float] = None
    note: Optional[str] = None


def _lookup_current_score(ticker: str) -> Optional[float]:
    """Look up a ticker's composite_score from the latest scan. None if not found."""
    try:
        from ..scan_results_service import ScanResultsService
        scan = ScanResultsService.get_latest() or {}
        for s in (scan.get("all_scores") or []) + (scan.get("top") or []):
            if s.get("ticker") == ticker:
                score = s.get("composite_score")
                if score is not None:
                    return float(score)
    except Exception:
        pass
    return None


@router.post("/portfolio/holdings/{ticker}")
def create_holding(ticker: str, body: HoldingCreate, _: None = Depends(verify_api_key)):
    ticker = ticker.upper()
    holdings = load_holdings()
    if ticker in holdings:
        raise HTTPException(status_code=409, detail=f"{ticker} already exists; use PATCH to update")
    entry = {"shares": body.shares, "entry_price": body.entry_price}
    entry["entry_date"] = body.entry_date or datetime.now().date().isoformat()
    # entry_score: explicit override > current scan lookup
    score = body.entry_score if body.entry_score is not None else _lookup_current_score(ticker)
    if score is not None:
        entry["entry_score"] = round(score, 2)
    if body.note:
        entry["note"] = body.note
    holdings[ticker] = entry
    save_holdings(holdings)
    return {"ticker": ticker, "holding": entry}


@router.patch("/portfolio/holdings/{ticker}")
def update_holding(ticker: str, body: HoldingUpdate, _: None = Depends(verify_api_key)):
    ticker = ticker.upper()
    holdings = load_holdings()
    if ticker not in holdings:
        raise HTTPException(status_code=404, detail=f"{ticker} not in holdings")
    entry = holdings[ticker]
    for field in ("shares", "entry_price", "entry_date", "entry_score", "note"):
        val = getattr(body, field)
        if val is not None:
            entry[field] = val
    holdings[ticker] = entry
    save_holdings(holdings)
    return {"ticker": ticker, "holding": entry}


@router.delete("/portfolio/holdings/{ticker}")
def delete_holding(ticker: str, _: None = Depends(verify_api_key)):
    """Hard-delete a holding WITHOUT archiving. Use for typos/erroneous adds only."""
    ticker = ticker.upper()
    holdings = load_holdings()
    if ticker not in holdings:
        raise HTTPException(status_code=404, detail=f"{ticker} not in holdings")
    removed = holdings.pop(ticker)
    save_holdings(holdings)
    return {"ticker": ticker, "removed": removed}


class HoldingAdd(BaseModel):
    added_shares: float = Field(..., gt=0)
    added_price: float = Field(..., gt=0)
    added_date: Optional[str] = None
    note: Optional[str] = None


@router.post("/portfolio/holdings/{ticker}/add")
def add_to_holding(ticker: str, body: HoldingAdd, _: None = Depends(verify_api_key)):
    """Add more shares to an existing holding; recompute weighted-avg entry price."""
    ticker = ticker.upper()
    holdings = load_holdings()
    if ticker not in holdings:
        raise HTTPException(status_code=404, detail=f"{ticker} not in holdings; use POST /portfolio/holdings/{{ticker}} to create")

    entry = holdings[ticker]
    old_shares = float(entry.get("shares") or 0)
    old_price = float(entry.get("entry_price") or 0)
    new_shares = old_shares + body.added_shares
    # Weighted average — guard against zero (defensive, entry_price should never be 0)
    new_price = (
        (old_shares * old_price + body.added_shares * body.added_price) / new_shares
        if new_shares > 0
        else body.added_price
    )

    added_date = body.added_date or datetime.now().date().isoformat()
    head = f"Added {body.added_shares}sh @ ${body.added_price:.2f} on {added_date}"
    if body.note:
        head += f" ({body.note})"
    existing_note = entry.get("note", "").strip()
    entry["note"] = f"{head}. {existing_note}" if existing_note else head

    entry["shares"] = round(new_shares, 6)
    entry["entry_price"] = round(new_price, 2)
    # entry_date preserved (original position date — keeps hold-time meaningful)
    holdings[ticker] = entry
    save_holdings(holdings)
    return {"ticker": ticker, "holding": entry}


class HoldingClose(BaseModel):
    exit_price: float = Field(..., gt=0)
    exit_date: str
    note: Optional[str] = None


@router.post("/portfolio/holdings/{ticker}/close")
def close_holding(ticker: str, body: HoldingClose, _: None = Depends(verify_api_key)):
    """Record a sale: archive the position with realized P&L, then remove from holdings."""
    ticker = ticker.upper()
    holdings = load_holdings()
    if ticker not in holdings:
        raise HTTPException(status_code=404, detail=f"{ticker} not in holdings")
    entry = closed_holdings_svc.build_entry(
        ticker, holdings[ticker], body.exit_price, body.exit_date, body.note
    )
    closed_holdings_svc.append(entry)
    holdings.pop(ticker)
    save_holdings(holdings)
    return {"ticker": ticker, "closed": entry}


@router.get("/closed-holdings")
def list_closed_holdings():
    return {"closed": closed_holdings_svc.load_closed()}


@router.get("/closed-holdings/stats")
def closed_holdings_stats():
    return closed_holdings_svc.stats()


@router.get("/alerts/decay")
def position_decay_alerts(save_state: bool = Query(True)):
    """Position-decay alerts on held positions: sell signals, signal degrades,
    score decay vs entry, near-stop, earnings proximity. Distinct from /alerts
    which monitors top-N changes universe-wide."""
    from ..scan_results_service import ScanResultsService
    holdings = load_holdings()
    current = ScanResultsService.get_latest()
    if not current:
        return {"alerts": [], "summary": {"total": 0, "urgent": 0, "warning": 0, "info": 0},
                "error": "no scan results available"}
    prev_path = DATA_DIR / "prev_scan_results.json"
    prev = None
    if prev_path.exists():
        try:
            prev = json.loads(prev_path.read_text())
        except Exception:
            pass
    alerts = check_position_decay(holdings, current, prev, save_state=save_state)
    return {"alerts": alerts, "summary": decay_summarize(alerts)}
