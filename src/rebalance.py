"""Tolerance Band Rebalancing — continuous monitoring with swap suggestions.

Instead of fixed-time rebalancing, we monitor daily and only suggest swaps when:
1. A held stock's signal degrades significantly (tolerance band breach)
2. A replacement candidate is materially better (ML gap threshold)
3. Minimum hold period is respected (avoid churn)

Rules (from Kitces research + our tuning):
- 30-day minimum hold before considering a swap
- AVOID signal: 5-day grace period (confirm it's not noise)
- STRONG BUY replacement must persist 5+ days
- ML consensus gap > 15 points between held stock and replacement
- Max 1 swap per month (reduce transaction costs)
- Earnings guard: no swaps within 5 days of earnings
"""

import json
import logging
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
REBALANCE_STATE_FILE = DATA_DIR / "rebalance_state.json"
PORTFOLIO_FILE = DATA_DIR / "holdings.json"

# --- Configuration ---
MIN_HOLD_DAYS = 30          # Don't sell anything held < 30 days
AVOID_CONFIRM_DAYS = 5      # AVOID/SELL signal must persist N days
STRONG_BUY_CONFIRM_DAYS = 5 # Replacement must be STRONG_BUY for N days
ML_GAP_THRESHOLD = 15       # ML score gap required for swap
MAX_SWAPS_PER_MONTH = 1     # Max swaps in a rolling 30-day window
EARNINGS_BLACKOUT_DAYS = 5  # No swaps within N days of earnings


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


def load_holdings() -> Dict[str, dict]:
    """Load current holdings.
    
    Format: {
        "MCK": {"shares": 0.741, "entry_price": 944.72, "entry_date": "2026-02-17", "entry_score": 85.0},
        ...
    }
    """
    data = _load_json(PORTFOLIO_FILE)
    if data and isinstance(data, dict):
        return data.get("holdings", {})
    return {}


def save_holdings(holdings: Dict[str, dict]) -> None:
    """Save holdings to file."""
    _save_json(PORTFOLIO_FILE, {
        "holdings": holdings,
        "updated": datetime.now().isoformat(),
    })


def load_rebalance_state() -> dict:
    """Load rebalance tracking state.
    
    Tracks:
    - signal_streaks: {ticker: {"signal": str, "days": int, "since": str}}
    - swap_history: [{"date": str, "sold": str, "bought": str, "reason": str}]
    - candidate_streaks: {ticker: {"signal": str, "days": int, "since": str}}
    """
    data = _load_json(REBALANCE_STATE_FILE)
    if data and isinstance(data, dict):
        return data
    return {
        "signal_streaks": {},
        "swap_history": [],
        "candidate_streaks": {},
    }


def save_rebalance_state(state: dict) -> None:
    """Save rebalance state."""
    state["updated"] = datetime.now().isoformat()
    _save_json(REBALANCE_STATE_FILE, state)


def _days_held(entry_date_str: str) -> int:
    """Calculate days since entry."""
    try:
        # Handle both "YYYY-MM-DD" and "YYYY-MM-DDTHH:MM:SS" formats
        entry = datetime.fromisoformat(entry_date_str.split("T")[0])
        return (datetime.now() - entry).days
    except Exception:
        return 0  # If we can't parse, assume just bought (conservative — don't allow premature swaps)


def _swaps_in_last_30_days(swap_history: List[dict]) -> int:
    """Count swaps in the last 30 days."""
    cutoff = datetime.now() - timedelta(days=30)
    count = 0
    for swap in swap_history:
        try:
            swap_date = datetime.strptime(swap["date"], "%Y-%m-%d")
            if swap_date >= cutoff:
                count += 1
        except Exception:
            pass
    return count


def update_signal_streaks(
    state: dict,
    held_signals: Dict[str, dict],
    candidate_signals: Dict[str, dict],
    today: Optional[str] = None,
) -> dict:
    """Update signal streak tracking for held stocks and candidates.
    
    Args:
        state: Current rebalance state
        held_signals: {ticker: {"signal": "SELL"/"HOLD"/"BUY"/..., "score": float, "sell_score": float}}
        candidate_signals: {ticker: {"signal": "STRONG_BUY"/"BUY"/..., "score": float, "ml_score": float}}
        today: Date string override (for testing)
    
    Returns:
        Updated state
    """
    if today is None:
        today = datetime.now().strftime("%Y-%m-%d")
    
    # Update held stock signal streaks (tracking negative signals)
    streaks = state.get("signal_streaks", {})
    for ticker, sig_data in held_signals.items():
        signal = sig_data.get("sell_signal", "N/A")
        prev = streaks.get(ticker, {})
        
        if signal in ("SELL", "STRONG_SELL"):
            # Negative signal — increment streak
            if prev.get("signal") in ("SELL", "STRONG_SELL"):
                streaks[ticker] = {
                    "signal": signal,
                    "days": prev.get("days", 0) + 1,
                    "since": prev.get("since", today),
                    "sell_score": sig_data.get("sell_score", 0),
                }
            else:
                streaks[ticker] = {
                    "signal": signal,
                    "days": 1,
                    "since": today,
                    "sell_score": sig_data.get("sell_score", 0),
                }
        else:
            # Signal recovered — reset streak
            if ticker in streaks:
                del streaks[ticker]
    
    state["signal_streaks"] = streaks
    
    # Update candidate streaks (tracking STRONG_BUY persistence)
    cand_streaks = state.get("candidate_streaks", {})
    active_candidates = set()
    
    for ticker, sig_data in candidate_signals.items():
        signal = sig_data.get("entry_signal", "HOLD")
        if signal == "STRONG_BUY":
            active_candidates.add(ticker)
            prev = cand_streaks.get(ticker, {})
            if prev.get("signal") == "STRONG_BUY":
                cand_streaks[ticker] = {
                    "signal": "STRONG_BUY",
                    "days": prev.get("days", 0) + 1,
                    "since": prev.get("since", today),
                    "score": sig_data.get("composite_score", 0),
                    "ml_score": sig_data.get("ml_score", 0),
                }
            else:
                cand_streaks[ticker] = {
                    "signal": "STRONG_BUY",
                    "days": 1,
                    "since": today,
                    "score": sig_data.get("composite_score", 0),
                    "ml_score": sig_data.get("ml_score", 0),
                }
    
    # Remove candidates that are no longer STRONG_BUY
    for ticker in list(cand_streaks.keys()):
        if ticker not in active_candidates:
            del cand_streaks[ticker]
    
    state["candidate_streaks"] = cand_streaks
    return state


def evaluate_swaps(
    holdings: Dict[str, dict],
    state: dict,
    held_scores: Dict[str, dict],
    candidate_scores: Dict[str, dict],
    earnings_dates: Optional[Dict[str, str]] = None,
) -> List[dict]:
    """Evaluate potential swaps based on tolerance band rules.
    
    Args:
        holdings: Current holdings {ticker: {shares, entry_price, entry_date, ...}}
        state: Rebalance state with streaks
        held_scores: {ticker: {composite_score, ml_score, sell_signal, sell_score, ...}}
        candidate_scores: {ticker: {composite_score, ml_score, entry_signal, ...}}
        earnings_dates: {ticker: "YYYY-MM-DD"} for earnings blackout check
    
    Returns:
        List of swap suggestions with reasoning
    """
    suggestions = []
    today = datetime.now()
    today_str = today.strftime("%Y-%m-%d")
    
    # Check swap budget
    swap_history = state.get("swap_history", [])
    recent_swaps = _swaps_in_last_30_days(swap_history)
    if recent_swaps >= MAX_SWAPS_PER_MONTH:
        logger.info("Max swaps reached (%d in last 30 days), skipping evaluation", recent_swaps)
        return [{
            "action": "HOLD_ALL",
            "reason": f"已达到本月换股上限 ({recent_swaps}/{MAX_SWAPS_PER_MONTH})",
            "swaps_used": recent_swaps,
        }]
    
    signal_streaks = state.get("signal_streaks", {})
    cand_streaks = state.get("candidate_streaks", {})
    
    # Find held stocks that breach tolerance band
    sell_candidates = []
    for ticker, holding in holdings.items():
        days_held = _days_held(holding.get("entry_date", "2020-01-01"))
        
        # Min hold period check
        if days_held < MIN_HOLD_DAYS:
            logger.info("%s: held %d days (< %d min), skipping", ticker, days_held, MIN_HOLD_DAYS)
            continue
        
        # Earnings blackout check
        if earnings_dates and ticker in earnings_dates:
            try:
                earn_date = datetime.strptime(earnings_dates[ticker], "%Y-%m-%d")
                days_to_earnings = (earn_date - today).days
                if 0 <= days_to_earnings <= EARNINGS_BLACKOUT_DAYS:
                    logger.info("%s: earnings in %d days, blackout", ticker, days_to_earnings)
                    continue
            except Exception:
                pass
        
        # Check if sell signal has persisted long enough
        streak = signal_streaks.get(ticker, {})
        streak_days = streak.get("days", 0)
        sell_signal = streak.get("signal", "N/A")
        
        scores = held_scores.get(ticker, {})
        composite = scores.get("composite_score", 50)
        ml_score = scores.get("ml_score", 50)
        sell_score = scores.get("sell_score", 0)
        
        # Tolerance band breach conditions:
        # 1. STRONG_SELL persisting AVOID_CONFIRM_DAYS+
        # 2. SELL persisting AVOID_CONFIRM_DAYS+  
        # 3. Composite score dropped below 30 (absolute floor)
        breach = False
        breach_reason = ""
        urgency = "low"
        
        if sell_signal == "STRONG_SELL" and streak_days >= AVOID_CONFIRM_DAYS:
            breach = True
            breach_reason = f"STRONG_SELL 持续 {streak_days} 天 (sell_score: {sell_score:.0f})"
            urgency = "high"
        elif sell_signal == "SELL" and streak_days >= AVOID_CONFIRM_DAYS:
            breach = True
            breach_reason = f"SELL 信号持续 {streak_days} 天 (sell_score: {sell_score:.0f})"
            urgency = "medium"
        elif composite < 30:
            breach = True
            breach_reason = f"综合评分跌破底线 ({composite:.1f})"
            urgency = "medium"
        
        if breach:
            sell_candidates.append({
                "ticker": ticker,
                "reason": breach_reason,
                "urgency": urgency,
                "composite": composite,
                "ml_score": ml_score,
                "sell_score": sell_score,
                "days_held": days_held,
                "holding": holding,
            })
    
    if not sell_candidates:
        return [{
            "action": "HOLD_ALL",
            "reason": "所有持仓在容忍区间内，无需调整",
            "holdings_checked": len(holdings),
        }]
    
    # Sort sell candidates by urgency then sell_score
    urgency_order = {"high": 0, "medium": 1, "low": 2}
    sell_candidates.sort(key=lambda x: (urgency_order.get(x["urgency"], 3), -x["sell_score"]))
    
    # Find best replacement candidates
    # Must be STRONG_BUY for STRONG_BUY_CONFIRM_DAYS+ and not already held
    held_tickers = set(holdings.keys())
    valid_replacements = []
    
    for ticker, cand in cand_streaks.items():
        if ticker in held_tickers:
            continue
        if cand.get("days", 0) >= STRONG_BUY_CONFIRM_DAYS:
            # Earnings blackout for replacement too
            if earnings_dates and ticker in earnings_dates:
                try:
                    earn_date = datetime.strptime(earnings_dates[ticker], "%Y-%m-%d")
                    days_to_earnings = (earn_date - today).days
                    if 0 <= days_to_earnings <= EARNINGS_BLACKOUT_DAYS:
                        continue
                except Exception:
                    pass
            
            cand_detail = candidate_scores.get(ticker, {})
            valid_replacements.append({
                "ticker": ticker,
                "days_strong_buy": cand["days"],
                "composite": cand_detail.get("composite_score", cand.get("score", 0)),
                "ml_score": cand_detail.get("ml_score", cand.get("ml_score", 0)),
            })
    
    # Sort replacements by composite score
    valid_replacements.sort(key=lambda x: -x["composite"])
    
    # Match sell candidates with replacements (check ML gap)
    swaps_remaining = MAX_SWAPS_PER_MONTH - recent_swaps
    
    for sell_cand in sell_candidates[:swaps_remaining]:
        best_replacement = None
        
        for repl in valid_replacements:
            # Check ML gap threshold
            ml_gap = repl.get("ml_score", 0) - sell_cand.get("ml_score", 0)
            score_gap = repl["composite"] - sell_cand["composite"]
            
            if ml_gap >= ML_GAP_THRESHOLD or score_gap >= 20:
                best_replacement = repl
                best_replacement["ml_gap"] = ml_gap
                best_replacement["score_gap"] = score_gap
                break
        
        suggestion = {
            "action": "SWAP",
            "sell": sell_cand["ticker"],
            "sell_reason": sell_cand["reason"],
            "sell_urgency": sell_cand["urgency"],
            "sell_composite": sell_cand["composite"],
            "sell_ml_score": sell_cand["ml_score"],
            "days_held": sell_cand["days_held"],
            "shares": sell_cand["holding"].get("shares", 0),
            "entry_price": sell_cand["holding"].get("entry_price", 0),
        }
        
        if best_replacement:
            suggestion["buy"] = best_replacement["ticker"]
            suggestion["buy_composite"] = best_replacement["composite"]
            suggestion["buy_ml_score"] = best_replacement.get("ml_score", 0)
            suggestion["buy_days_strong_buy"] = best_replacement["days_strong_buy"]
            suggestion["ml_gap"] = best_replacement.get("ml_gap", 0)
            suggestion["score_gap"] = best_replacement.get("score_gap", 0)
            # Remove from valid replacements so we don't double-assign
            valid_replacements = [r for r in valid_replacements if r["ticker"] != best_replacement["ticker"]]
        else:
            suggestion["buy"] = None
            suggestion["buy_note"] = "无合格替代候选（需 STRONG_BUY 持续5天+且ML差距>15）"
        
        suggestions.append(suggestion)
    
    # Add any remaining sell candidates as warnings (beyond swap budget)
    for sell_cand in sell_candidates[swaps_remaining:]:
        suggestions.append({
            "action": "WATCH",
            "ticker": sell_cand["ticker"],
            "reason": f"信号恶化但已达换股上限: {sell_cand['reason']}",
            "urgency": sell_cand["urgency"],
        })
    
    return suggestions


def record_swap(state: dict, sold: str, bought: str, reason: str) -> dict:
    """Record a completed swap in history."""
    swap_history = state.get("swap_history", [])
    swap_history.append({
        "date": datetime.now().strftime("%Y-%m-%d"),
        "sold": sold,
        "bought": bought,
        "reason": reason,
        "timestamp": datetime.now().isoformat(),
    })
    # Keep last 50 swaps
    state["swap_history"] = swap_history[-50:]
    return state


def format_rebalance_report(suggestions: List[dict], holdings: Dict[str, dict]) -> str:
    """Format swap suggestions into a readable report for Discord."""
    lines = []
    lines.append("⚖️ **Tolerance Band Rebalance Check**")
    lines.append("")
    
    has_swaps = any(s.get("action") == "SWAP" for s in suggestions)
    has_watches = any(s.get("action") == "WATCH" for s in suggestions)
    hold_all = any(s.get("action") == "HOLD_ALL" for s in suggestions)
    
    if hold_all:
        reason = suggestions[0].get("reason", "")
        lines.append(f"✅ {reason}")
        return "\n".join(lines)
    
    if has_swaps:
        lines.append("🔄 **建议换股:**")
        for s in suggestions:
            if s.get("action") != "SWAP":
                continue
            
            urgency_emoji = "🔴" if s["sell_urgency"] == "high" else "🟡" if s["sell_urgency"] == "medium" else "⚪"
            lines.append(f"\n{urgency_emoji} **卖出 {s['sell']}** (持有 {s['days_held']} 天)")
            lines.append(f"  原因: {s['sell_reason']}")
            lines.append(f"  评分: {s['sell_composite']:.1f} | ML: {s['sell_ml_score']:.1f}")
            
            if s.get("buy"):
                lines.append(f"  ➡️ **买入 {s['buy']}**")
                lines.append(f"  评分: {s['buy_composite']:.1f} | ML: {s['buy_ml_score']:.1f}")
                lines.append(f"  STRONG_BUY 持续: {s['buy_days_strong_buy']} 天")
                lines.append(f"  ML差距: +{s.get('ml_gap', 0):.1f} | 评分差距: +{s.get('score_gap', 0):.1f}")
            else:
                lines.append(f"  ⚠️ {s.get('buy_note', '无合格替代')}")
        lines.append("")
    
    if has_watches:
        lines.append("👀 **关注 (超出换股预算):**")
        for s in suggestions:
            if s.get("action") != "WATCH":
                continue
            urgency_emoji = "🔴" if s["urgency"] == "high" else "🟡"
            lines.append(f"  {urgency_emoji} {s['ticker']}: {s['reason']}")
        lines.append("")
    
    # Portfolio summary
    lines.append(f"📋 持仓数: {len(holdings)} | 本月可换: {MAX_SWAPS_PER_MONTH}")
    
    return "\n".join(lines)
