"""Signal alerts system: track changes and generate alerts."""

import json
import logging
import time
from pathlib import Path
from typing import Dict, List, Optional

from .streak_tracker import get_all_streaks

logger = logging.getLogger(__name__)

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
ALERTS_FILE = DATA_DIR / "alerts.json"
PREV_RESULTS_FILE = DATA_DIR / "prev_scan_results.json"


def _load_json(path: Path) -> Optional[dict]:
    if path.exists():
        try:
            return json.loads(path.read_text())
        except Exception:
            return None
    return None


def _save_json(path: Path, data: object) -> None:
    DATA_DIR.mkdir(exist_ok=True)
    path.write_text(json.dumps(data, indent=2, default=str))


def _load_alerts_history() -> List[dict]:
    data = _load_json(ALERTS_FILE)
    if isinstance(data, list):
        return data
    return []


def _save_alerts(alerts: List[dict]) -> None:
    # Keep last 200
    _save_json(ALERTS_FILE, alerts[-200:])


def check_alerts(
    current_results: Optional[dict] = None,
    previous_results: Optional[dict] = None,
    earnings_data: Optional[Dict[str, dict]] = None,
) -> List[dict]:
    """Compare current scan results with previous and generate alerts.

    Args:
        current_results: Current scan output dict with 'top' list.
        previous_results: Previous scan output. If None, loads from file.
        earnings_data: Optional {ticker: earnings_info} for earnings warnings.

    Returns:
        List of alert dicts with type, ticker, message, severity, timestamp.
    """
    alerts = []  # type: List[dict]
    now = time.strftime("%Y-%m-%dT%H:%M:%S")

    if current_results is None:
        from .pipeline import RESULTS_FILE
        current_results = _load_json(RESULTS_FILE)

    if current_results is None:
        return alerts

    current_top = current_results.get("top", [])
    current_tickers = {s["ticker"]: s for s in current_top}

    # Load previous
    if previous_results is None:
        previous_results = _load_json(PREV_RESULTS_FILE)

    prev_tickers = {}  # type: Dict[str, dict]
    if previous_results:
        for s in previous_results.get("top", []):
            prev_tickers[s["ticker"]] = s

    # 1. New stocks entering top N
    for ticker in current_tickers:
        if ticker not in prev_tickers:
            s = current_tickers[ticker]
            alerts.append({
                "type": "new_entry",
                "ticker": ticker,
                "message": "%s entered top %d (score: %.1f)" % (ticker, len(current_top), s.get("composite_score", 0)),
                "severity": "info",
                "timestamp": now,
            })

    # 2. Stocks dropping out
    for ticker in prev_tickers:
        if ticker not in current_tickers:
            alerts.append({
                "type": "dropped",
                "ticker": ticker,
                "message": "%s dropped out of top rankings" % ticker,
                "severity": "warning",
                "timestamp": now,
            })

    # 3. Score changes > 10 points
    for ticker in current_tickers:
        if ticker in prev_tickers:
            curr_score = current_tickers[ticker].get("composite_score", 0) or 0
            prev_score = prev_tickers[ticker].get("composite_score", 0) or 0
            diff = curr_score - prev_score
            if abs(diff) > 10:
                direction = "up" if diff > 0 else "down"
                alerts.append({
                    "type": "score_change",
                    "ticker": ticker,
                    "message": "%s score moved %s by %.1f (%.1f → %.1f)" % (ticker, direction, abs(diff), prev_score, curr_score),
                    "severity": "info" if diff > 0 else "warning",
                    "timestamp": now,
                })

    # 4. Entry signal changed to STRONG_BUY
    for ticker, s in current_tickers.items():
        entry_signal = s.get("entry_signal", "")
        prev_signal = prev_tickers.get(ticker, {}).get("entry_signal", "")
        if entry_signal == "STRONG_BUY" and prev_signal != "STRONG_BUY":
            alerts.append({
                "type": "strong_buy",
                "ticker": ticker,
                "message": "%s entry signal changed to STRONG_BUY" % ticker,
                "severity": "critical",
                "timestamp": now,
            })

    # 4b. Sell signal warnings (STRONG_SELL or SELL)
    for ticker, s in current_tickers.items():
        sell_signal = s.get("sell_signal", "N/A")
        sell_urgency = s.get("sell_urgency", "none")
        sell_reasons = s.get("sell_reasons", [])
        
        if sell_signal == "STRONG_SELL":
            alerts.append({
                "type": "strong_sell",
                "ticker": ticker,
                "message": "%s has STRONG SELL signal: %s" % (ticker, "; ".join(sell_reasons[:2])),
                "severity": "critical",
                "timestamp": now,
            })
        elif sell_signal == "SELL":
            alerts.append({
                "type": "sell_warning",
                "ticker": ticker,
                "message": "%s has SELL signal: %s" % (ticker, "; ".join(sell_reasons[:2])),
                "severity": "warning",
                "timestamp": now,
            })

    # 5. Earnings within 7 days
    if earnings_data:
        for ticker, edata in earnings_data.items():
            if ticker in current_tickers and edata.get("earnings_soon"):
                ed = edata.get("next_earnings_date", "unknown")
                alerts.append({
                    "type": "earnings_warning",
                    "ticker": ticker,
                    "message": "%s has earnings coming up on %s" % (ticker, ed),
                    "severity": "warning",
                    "timestamp": now,
                })

    # Save current as previous for next comparison
    _save_json(PREV_RESULTS_FILE, current_results)

    # Append to history
    if alerts:
        history = _load_alerts_history()
        history.extend(alerts)
        _save_alerts(history)

    return alerts


def get_alert_history(limit: int = 50) -> List[dict]:
    """Return recent alert history."""
    history = _load_alerts_history()
    return history[-limit:]


def generate_morning_briefing(current_results: Optional[dict] = None, top_n: int = 20) -> str:
    """
    Generate a morning briefing with streak indicators.
    
    Indicators:
    - 📅 Established pick (7+ consecutive days)
    - 🆕 New entry (1-3 days)
    - 🔥 Hot streak (3-6 days)
    
    Args:
        current_results: Current scan results dict. If None, loads from file.
        top_n: Number of top stocks to include in briefing
    
    Returns:
        Formatted briefing string
    """
    if current_results is None:
        from .pipeline import RESULTS_FILE
        current_results = _load_json(RESULTS_FILE)
    
    if current_results is None:
        return "No scan results available. Run /scan first."
    
    top_stocks = current_results.get("top", [])[:top_n]
    timestamp = current_results.get("timestamp", "Unknown")
    strategy = current_results.get("strategy", "balanced")
    market_regime = current_results.get("market_regime", {})
    
    streaks = get_all_streaks()
    
    # Determine regime emoji
    regime = market_regime.get("regime", "sideways")
    regime_emoji = "🐂" if regime == "bull" else "🐻" if regime == "bear" else "➡️"
    regime_label = f"{regime_emoji} {regime.upper()} MARKET"
    regime_desc = market_regime.get("description", "")
    
    # Build briefing
    lines = []
    lines.append("=" * 60)
    lines.append(f"📊 MORNING BRIEFING - {timestamp}")
    lines.append(f"Strategy: {strategy.upper()} | Market: {regime_label}")
    if regime_desc:
        lines.append(f"    {regime_desc}")
    lines.append("=" * 60)
    lines.append("")
    
    # Group by streak category
    established = []  # 7+ days
    hot_streak = []   # 3-6 days
    new_entries = []  # 1-2 days
    
    for stock in top_stocks:
        ticker = stock.get("ticker")
        consecutive_days = stock.get("consecutive_days", 0)
        
        if consecutive_days >= 7:
            established.append(stock)
        elif consecutive_days >= 3:
            hot_streak.append(stock)
        else:
            new_entries.append(stock)
    
    # Print sections
    if established:
        lines.append("📅 ESTABLISHED PICKS (7+ days in top 20)")
        lines.append("-" * 60)
        for stock in established:
            ticker = stock.get("ticker")
            name = stock.get("name", "")[:25]
            score = stock.get("composite_score", 0)
            signal = stock.get("entry_signal", "HOLD")
            days = stock.get("consecutive_days", 0)
            rank = stock.get("rank", 0)
            
            signal_emoji = "🟢" if signal == "STRONG_BUY" else "🔵" if signal == "BUY" else "⚪"
            lines.append(f"  #{rank:>2} {signal_emoji} {ticker:<6} {name:<25} Score: {score:>6.2f} | {days} days")
        lines.append("")
    
    if hot_streak:
        lines.append("🔥 HOT STREAKS (3-6 days)")
        lines.append("-" * 60)
        for stock in hot_streak:
            ticker = stock.get("ticker")
            name = stock.get("name", "")[:25]
            score = stock.get("composite_score", 0)
            signal = stock.get("entry_signal", "HOLD")
            days = stock.get("consecutive_days", 0)
            rank = stock.get("rank", 0)
            
            signal_emoji = "🟢" if signal == "STRONG_BUY" else "🔵" if signal == "BUY" else "⚪"
            lines.append(f"  #{rank:>2} {signal_emoji} {ticker:<6} {name:<25} Score: {score:>6.2f} | {days} days")
        lines.append("")
    
    if new_entries:
        lines.append("🆕 NEW ENTRIES (1-2 days)")
        lines.append("-" * 60)
        for stock in new_entries:
            ticker = stock.get("ticker")
            name = stock.get("name", "")[:25]
            score = stock.get("composite_score", 0)
            signal = stock.get("entry_signal", "HOLD")
            days = stock.get("consecutive_days", 0)
            rank = stock.get("rank", 0)
            
            signal_emoji = "🟢" if signal == "STRONG_BUY" else "🔵" if signal == "BUY" else "⚪"
            lines.append(f"  #{rank:>2} {signal_emoji} {ticker:<6} {name:<25} Score: {score:>6.2f} | {days} days")
        lines.append("")
    
    # Summary stats
    lines.append("=" * 60)
    lines.append(f"Total: {len(top_stocks)} stocks | ")
    lines.append(f"Established: {len(established)} | Hot: {len(hot_streak)} | New: {len(new_entries)}")
    lines.append("=" * 60)
    
    return "\n".join(lines)
