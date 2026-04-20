"""Position-decay alerts — early warnings when held positions weaken.

Focused specifically on holdings.json tickers, NOT the top 20. The point is to
catch degradation before it becomes a forced sell. Pairs with src/alerts.py
(which monitors universe-wide top-N changes) — this module monitors *your book*.

Triggers per held ticker:
  - SELL/STRONG_SELL signal fires from the model
  - Entry signal degrades (BUY → HOLD, HOLD → WAIT, WAIT → AVOID)
  - Composite score drops >= 10 from entry_score
  - Composite score drops >= 5 since previous scan
  - Position within 3% of stop-loss threshold
  - Earnings within 3 days

Severity:
  urgent  — sell signal fired, near-stop, earnings <=1 day
  warning — signal degrade, near-stop <=3%, score decay >=10
  info    — minor score drift >=5, earnings 3-7 days

Dedup: per-ticker per-alert-type, suppressed for 24h after first fire.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
DECAY_STATE_FILE = DATA_DIR / "decay_alerts_state.json"

# Signal ordering (higher index = weaker)
_SIGNAL_RANK = {
    "STRONG_BUY": 0,
    "BUY": 1,
    "HOLD": 2,
    "WAIT": 3,
    "AVOID": 4,
}

DEDUP_HOURS = 24


def _load_state() -> dict:
    if not DECAY_STATE_FILE.exists():
        return {}
    try:
        return json.loads(DECAY_STATE_FILE.read_text())
    except Exception:
        return {}


def _save_state(state: dict) -> None:
    DATA_DIR.mkdir(exist_ok=True)
    DECAY_STATE_FILE.write_text(json.dumps(state, indent=2, default=str))


def _is_deduped(state: dict, ticker: str, alert_type: str, now: datetime) -> bool:
    rec = state.get(ticker, {}).get(alert_type)
    if not rec:
        return False
    try:
        last = datetime.fromisoformat(rec.get("last_fired", ""))
        return (now - last) < timedelta(hours=DEDUP_HOURS)
    except Exception:
        return False


def _record(state: dict, ticker: str, alert_type: str, payload: dict, now: datetime) -> None:
    state.setdefault(ticker, {})[alert_type] = {
        "last_fired": now.isoformat(),
        **payload,
    }


def check_position_decay(
    holdings: dict[str, dict],
    current_results: dict,
    previous_results: Optional[dict] = None,
    save_state: bool = True,
) -> list[dict]:
    """Check held positions for decay/warning conditions.

    Args:
        holdings: dict from rebalance.load_holdings() — {ticker: {shares, entry_price, entry_date, entry_score?}}
        current_results: latest scan dict with 'top' and 'all_scores'
        previous_results: previous scan (for delta detection); optional
        save_state: persist dedup state to disk

    Returns:
        List of alert dicts ordered by severity (urgent → warning → info).
    """
    if not holdings or not current_results:
        return []

    now = datetime.now()

    # Build ticker → score-record indexes
    def _index(results: dict) -> dict[str, dict]:
        idx = {}
        for s in (results.get("all_scores") or []):
            if s.get("ticker"):
                idx[s["ticker"]] = s
        for s in (results.get("top") or []):
            if s.get("ticker"):
                idx[s["ticker"]] = s
        return idx

    cur_idx = _index(current_results)
    prev_idx = _index(previous_results) if previous_results else {}

    state = _load_state()
    alerts: list[dict] = []

    for ticker, holding in holdings.items():
        ticker = ticker.upper()
        s = cur_idx.get(ticker)
        if not s:
            continue  # ticker not in scanner universe

        prev_s = prev_idx.get(ticker, {})
        cur_score = float(s.get("composite_score") or 0)
        prev_score = float(prev_s.get("composite_score") or cur_score)
        cur_signal = (s.get("entry_signal") or "").upper()
        prev_signal = (prev_s.get("entry_signal") or "").upper()
        sell_signal = (s.get("sell_signal") or "").upper()
        cur_price = float(s.get("current_price") or 0)
        entry_price = float(holding.get("entry_price") or 0)
        entry_score = float(holding.get("entry_score") or 0) or None
        days_until_earnings = s.get("days_until_earnings")

        pnl_pct = ((cur_price - entry_price) / entry_price * 100) if entry_price > 0 else 0
        stop_loss_pct = -15.0  # CLAUDE.md default

        # Common payload bits
        common = {
            "ticker": ticker,
            "current_score": round(cur_score, 1),
            "previous_score": round(prev_score, 1),
            "score_delta": round(cur_score - prev_score, 1),
            "entry_score": round(entry_score, 1) if entry_score else None,
            "current_signal": cur_signal,
            "previous_signal": prev_signal,
            "sell_signal": sell_signal,
            "current_price": round(cur_price, 2) if cur_price else None,
            "entry_price": round(entry_price, 2),
            "pnl_pct": round(pnl_pct, 2),
        }

        # --- URGENT: explicit sell signal fired ---
        if sell_signal in ("SELL", "STRONG_SELL"):
            alert_type = f"sell_signal_{sell_signal.lower()}"
            if not _is_deduped(state, ticker, alert_type, now):
                reasons = s.get("sell_reasons") or []
                alerts.append({
                    **common,
                    "alert_type": alert_type,
                    "severity": "urgent",
                    "message": f"{ticker} {sell_signal} signal fired" +
                               (f" — {reasons[0]}" if reasons else ""),
                    "details": {"sell_reasons": reasons[:3]},
                    "first_detected": now.isoformat(),
                })
                _record(state, ticker, alert_type, {"sell_signal": sell_signal}, now)

        # --- URGENT: near stop-loss (within 1%) ---
        if pnl_pct <= stop_loss_pct + 1 and pnl_pct > stop_loss_pct - 1:
            alert_type = "near_stop_urgent"
            if not _is_deduped(state, ticker, alert_type, now):
                alerts.append({
                    **common,
                    "alert_type": alert_type,
                    "severity": "urgent",
                    "message": f"{ticker} at {pnl_pct:+.1f}% — within 1% of stop-loss ({stop_loss_pct:+.0f}%)",
                    "details": {"stop_loss_pct": stop_loss_pct},
                    "first_detected": now.isoformat(),
                })
                _record(state, ticker, alert_type, {"pnl_pct": pnl_pct}, now)

        # --- URGENT: earnings <=1 day ---
        if days_until_earnings is not None and 0 <= days_until_earnings <= 1:
            alert_type = "earnings_imminent"
            if not _is_deduped(state, ticker, alert_type, now):
                alerts.append({
                    **common,
                    "alert_type": alert_type,
                    "severity": "urgent",
                    "message": f"{ticker} earnings in {days_until_earnings}d — consider closing or sizing down",
                    "details": {"days_until_earnings": days_until_earnings, "earnings_date": s.get("earnings_date")},
                    "first_detected": now.isoformat(),
                })
                _record(state, ticker, alert_type, {"days_until_earnings": days_until_earnings}, now)

        # --- WARNING: signal degraded ---
        if cur_signal and prev_signal:
            cur_rank = _SIGNAL_RANK.get(cur_signal)
            prev_rank = _SIGNAL_RANK.get(prev_signal)
            if cur_rank is not None and prev_rank is not None and cur_rank > prev_rank:
                alert_type = "signal_degraded"
                key = f"{prev_signal}->{cur_signal}"
                rec = state.get(ticker, {}).get(alert_type, {})
                # Re-fire if degradation moved to a new state
                if rec.get("transition") != key or not _is_deduped(state, ticker, alert_type, now):
                    alerts.append({
                        **common,
                        "alert_type": alert_type,
                        "severity": "warning",
                        "message": f"{ticker} signal degraded {prev_signal} → {cur_signal}",
                        "details": {"transition": key},
                        "first_detected": now.isoformat(),
                    })
                    _record(state, ticker, alert_type, {"transition": key}, now)

        # --- WARNING: near stop (within 3%) but not within 1% (urgent already handled) ---
        if stop_loss_pct - 1 < pnl_pct <= stop_loss_pct + 3 and not (stop_loss_pct - 1 < pnl_pct < stop_loss_pct + 1):
            # i.e. between -14% and -12% (exclusive of urgent zone)
            alert_type = "near_stop_warning"
            if not _is_deduped(state, ticker, alert_type, now):
                alerts.append({
                    **common,
                    "alert_type": alert_type,
                    "severity": "warning",
                    "message": f"{ticker} at {pnl_pct:+.1f}% — approaching stop-loss ({stop_loss_pct:+.0f}%)",
                    "details": {"stop_loss_pct": stop_loss_pct},
                    "first_detected": now.isoformat(),
                })
                _record(state, ticker, alert_type, {"pnl_pct": pnl_pct}, now)

        # --- WARNING: score decay vs entry >=10 ---
        if entry_score and (entry_score - cur_score) >= 10:
            alert_type = "entry_score_decay"
            decay = entry_score - cur_score
            rec = state.get(ticker, {}).get(alert_type, {})
            # Re-fire if decay grew by >=5 since last alert
            last_decay = float(rec.get("decay") or 0)
            if (decay - last_decay) >= 5 or not _is_deduped(state, ticker, alert_type, now):
                alerts.append({
                    **common,
                    "alert_type": alert_type,
                    "severity": "warning",
                    "message": f"{ticker} score decayed {decay:.1f}pts from entry ({entry_score:.1f} → {cur_score:.1f})",
                    "details": {"decay_pts": round(decay, 1)},
                    "first_detected": now.isoformat(),
                })
                _record(state, ticker, alert_type, {"decay": decay}, now)

        # --- INFO: score drift since last scan >=5 ---
        if (prev_score - cur_score) >= 5:
            alert_type = "score_drift_info"
            if not _is_deduped(state, ticker, alert_type, now):
                drift = prev_score - cur_score
                alerts.append({
                    **common,
                    "alert_type": alert_type,
                    "severity": "info",
                    "message": f"{ticker} score down {drift:.1f}pts since last scan ({prev_score:.1f} → {cur_score:.1f})",
                    "details": {"drift_pts": round(drift, 1)},
                    "first_detected": now.isoformat(),
                })
                _record(state, ticker, alert_type, {"drift": drift}, now)

        # --- INFO: earnings 3-7 days out ---
        if days_until_earnings is not None and 3 <= days_until_earnings <= 7:
            alert_type = "earnings_upcoming"
            if not _is_deduped(state, ticker, alert_type, now):
                alerts.append({
                    **common,
                    "alert_type": alert_type,
                    "severity": "info",
                    "message": f"{ticker} earnings in {days_until_earnings}d ({s.get('earnings_date', '?')})",
                    "details": {"days_until_earnings": days_until_earnings, "earnings_date": s.get("earnings_date")},
                    "first_detected": now.isoformat(),
                })
                _record(state, ticker, alert_type, {"days_until_earnings": days_until_earnings}, now)

    if save_state:
        _save_state(state)

    severity_order = {"urgent": 0, "warning": 1, "info": 2}
    alerts.sort(key=lambda a: (severity_order.get(a.get("severity", "info"), 9), -abs(a.get("score_delta", 0))))
    return alerts


def summarize(alerts: list[dict]) -> dict:
    counts = {"urgent": 0, "warning": 0, "info": 0}
    for a in alerts:
        sev = a.get("severity", "info")
        if sev in counts:
            counts[sev] += 1
    return {"total": len(alerts), **counts}
