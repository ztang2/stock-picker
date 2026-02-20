"""Historical accuracy tracking for stock signals."""

import json
import logging
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional, List, Dict, Any

import yfinance as yf

logger = logging.getLogger(__name__)

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
HISTORY_FILE = DATA_DIR / "signal_history.json"


def _load_history() -> List[Dict[str, Any]]:
    if HISTORY_FILE.exists():
        try:
            return json.loads(HISTORY_FILE.read_text())
        except Exception:
            logger.warning("Failed to load signal history", exc_info=True)
    return []


def _save_history(history: List[Dict[str, Any]]):
    DATA_DIR.mkdir(exist_ok=True)
    HISTORY_FILE.write_text(json.dumps(history, indent=2, default=str))


def take_snapshot(strategy: str = "balanced") -> Dict[str, Any]:
    """Log current scan signals to history AND save full daily snapshot.
    Called via /accuracy/snapshot (daily cron at 4pm ET).
    """
    from .pipeline import RESULTS_FILE
    
    if not RESULTS_FILE.exists():
        return {"error": "No scan results. Run /scan first.", "logged": 0}
    
    data = json.loads(RESULTS_FILE.read_text())
    top = data.get("top", [])
    today = datetime.now().strftime("%Y-%m-%d")
    
    # Save full daily snapshot (for ML training and historical analysis)
    snapshot_dir = DATA_DIR / "daily_snapshots"
    snapshot_dir.mkdir(exist_ok=True)
    snapshot_file = snapshot_dir / f"{today}.json"
    if not snapshot_file.exists():
        snapshot_file.write_text(json.dumps(data, indent=2, default=str))
        logger.info("Saved daily snapshot: %s", snapshot_file)
    scan_strategy = data.get("strategy", strategy)
    
    history = _load_history()
    
    # Avoid duplicate snapshots for same day+strategy
    existing_keys = set()
    for entry in history:
        if entry.get("date") == today and entry.get("strategy") == scan_strategy:
            existing_keys.add(entry.get("ticker"))
    
    logged = 0
    for stock in top:
        ticker = stock.get("ticker", "")
        if ticker in existing_keys:
            continue
        signal = stock.get("entry_signal", "HOLD")
        entry = {
            "ticker": ticker,
            "signal": signal,
            "score": stock.get("composite_score"),
            "price_at_signal": None,
            "date": today,
            "strategy": scan_strategy,
        }
        # Try to get current price
        try:
            t = yf.Ticker(ticker)
            info = t.info or {}
            entry["price_at_signal"] = info.get("currentPrice") or info.get("regularMarketPrice")
        except Exception:
            pass
        history.append(entry)
        logged += 1
    
    _save_history(history)
    return {"logged": logged, "total_history": len(history), "date": today, "strategy": scan_strategy}


def get_accuracy() -> Dict[str, Any]:
    """Analyze historical signal accuracy."""
    history = _load_history()
    
    if not history:
        return {
            "total_signals": 0,
            "buy_signals": 0,
            "win_rate": None,
            "avg_return": None,
            "avg_alpha": None,
            "best_pick": None,
            "worst_pick": None,
            "by_strategy": {},
            "picks": [],
        }
    
    # Filter to BUY/STRONG_BUY signals only
    buy_signals = [h for h in history if h.get("signal") in ("BUY", "STRONG_BUY")]
    
    if not buy_signals:
        return {
            "total_signals": len(history),
            "buy_signals": 0,
            "win_rate": None,
            "avg_return": None,
            "avg_alpha": None,
            "best_pick": None,
            "worst_pick": None,
            "by_strategy": {},
            "picks": [],
        }
    
    # Fetch current prices and SPY for comparison
    now = datetime.now()
    picks = []  # type: List[Dict[str, Any]]
    
    # Get SPY history for benchmarking
    spy_prices = {}  # type: Dict[str, float]
    try:
        spy = yf.Ticker("SPY")
        spy_hist = spy.history(period="1y")
        if not spy_hist.empty:
            for idx, row in spy_hist.iterrows():
                spy_prices[idx.strftime("%Y-%m-%d")] = float(row["Close"])
    except Exception:
        logger.warning("Failed to fetch SPY data for accuracy", exc_info=True)
    
    spy_current = None
    if spy_prices:
        spy_current = list(spy_prices.values())[-1]
    
    for sig in buy_signals:
        ticker = sig.get("ticker", "")
        signal_date_str = sig.get("date", "")
        price_at_signal = sig.get("price_at_signal")
        
        if not price_at_signal or not signal_date_str:
            continue
        
        try:
            signal_date = datetime.strptime(signal_date_str, "%Y-%m-%d")
        except ValueError:
            continue
        
        days_elapsed = (now - signal_date).days
        
        # Fetch current price
        current_price = None
        try:
            t = yf.Ticker(ticker)
            info = t.info or {}
            current_price = info.get("currentPrice") or info.get("regularMarketPrice")
        except Exception:
            continue
        
        if not current_price:
            continue
        
        stock_return = (current_price - price_at_signal) / price_at_signal
        
        # SPY return over same period
        spy_return = None
        if spy_prices and spy_current:
            # Find closest SPY price to signal date
            closest_spy = None
            for d_str, p in spy_prices.items():
                try:
                    d = datetime.strptime(d_str, "%Y-%m-%d")
                    if abs((d - signal_date).days) <= 5:
                        closest_spy = p
                        break
                except ValueError:
                    pass
            if closest_spy:
                spy_return = (spy_current - closest_spy) / closest_spy
        
        alpha = (stock_return - spy_return) if spy_return is not None else None
        
        pick = {
            "ticker": ticker,
            "signal": sig.get("signal"),
            "score": sig.get("score"),
            "strategy": sig.get("strategy"),
            "date": signal_date_str,
            "price_at_signal": round(price_at_signal, 2),
            "current_price": round(current_price, 2),
            "return_pct": round(stock_return * 100, 2),
            "spy_return_pct": round(spy_return * 100, 2) if spy_return is not None else None,
            "alpha_pct": round(alpha * 100, 2) if alpha is not None else None,
            "days_held": days_elapsed,
            "period": "1w" if days_elapsed <= 10 else "1m" if days_elapsed <= 35 else "3m" if days_elapsed <= 100 else "6m+",
        }
        picks.append(pick)
    
    # Compute aggregates
    returns = [p["return_pct"] for p in picks]
    alphas = [p["alpha_pct"] for p in picks if p["alpha_pct"] is not None]
    wins = [r for r in returns if r > 0]
    
    win_rate = len(wins) / len(returns) * 100 if returns else None
    avg_return = sum(returns) / len(returns) if returns else None
    avg_alpha = sum(alphas) / len(alphas) if alphas else None
    
    best_pick = max(picks, key=lambda p: p["return_pct"]) if picks else None
    worst_pick = min(picks, key=lambda p: p["return_pct"]) if picks else None
    
    # By strategy
    by_strategy = {}  # type: Dict[str, Any]
    strategies_seen = set(p["strategy"] for p in picks if p.get("strategy"))
    for strat in strategies_seen:
        strat_picks = [p for p in picks if p.get("strategy") == strat]
        strat_returns = [p["return_pct"] for p in strat_picks]
        strat_wins = [r for r in strat_returns if r > 0]
        by_strategy[strat] = {
            "picks": len(strat_picks),
            "win_rate": round(len(strat_wins) / len(strat_returns) * 100, 1) if strat_returns else None,
            "avg_return": round(sum(strat_returns) / len(strat_returns), 2) if strat_returns else None,
        }
    
    return {
        "total_signals": len(history),
        "buy_signals": len(buy_signals),
        "evaluated": len(picks),
        "win_rate": round(win_rate, 1) if win_rate is not None else None,
        "avg_return": round(avg_return, 2) if avg_return is not None else None,
        "avg_alpha": round(avg_alpha, 2) if avg_alpha is not None else None,
        "best_pick": best_pick,
        "worst_pick": worst_pick,
        "by_strategy": by_strategy,
        "picks": sorted(picks, key=lambda p: p["date"], reverse=True),
    }
