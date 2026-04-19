"""Closed holdings archive — append-only log of sold positions.

Each entry records a full-close transaction:
- entry_price, entry_date  (original buy info)
- exit_price, exit_date    (sell info)
- realized_pnl, realized_pnl_pct, hold_days (computed at close time)
- note (optional)

Partial sells are NOT recorded here — those stay as notes on the open holding.
"""

import json
from datetime import date, datetime
from pathlib import Path
from typing import List, Optional

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
CLOSED_FILE = DATA_DIR / "closed_holdings.json"


def load_closed() -> List[dict]:
    if not CLOSED_FILE.exists():
        return []
    try:
        data = json.loads(CLOSED_FILE.read_text())
        return data.get("closed", []) if isinstance(data, dict) else []
    except Exception:
        return []


def save_closed(entries: List[dict]) -> None:
    DATA_DIR.mkdir(exist_ok=True)
    CLOSED_FILE.write_text(
        json.dumps({"closed": entries, "updated": datetime.now().isoformat()}, indent=2, default=str)
    )


def _parse_date(d: Optional[str]) -> Optional[date]:
    if not d:
        return None
    try:
        return date.fromisoformat(d)
    except ValueError:
        return None


def build_entry(
    ticker: str,
    holding: dict,
    exit_price: float,
    exit_date: str,
    close_note: Optional[str] = None,
) -> dict:
    """Build a closed-holdings entry from an open holding + exit info."""
    shares = float(holding.get("shares") or 0)
    entry_price = float(holding.get("entry_price") or 0)
    entry_date = holding.get("entry_date")

    realized_pnl = (exit_price - entry_price) * shares
    realized_pnl_pct = ((exit_price - entry_price) / entry_price * 100) if entry_price else 0.0

    hold_days = None
    ed = _parse_date(entry_date)
    xd = _parse_date(exit_date)
    if ed and xd:
        hold_days = (xd - ed).days

    entry = {
        "ticker": ticker.upper(),
        "shares": shares,
        "entry_price": entry_price,
        "entry_date": entry_date,
        "exit_price": float(exit_price),
        "exit_date": exit_date,
        "realized_pnl": round(realized_pnl, 2),
        "realized_pnl_pct": round(realized_pnl_pct, 2),
        "hold_days": hold_days,
    }
    if holding.get("entry_score") is not None:
        entry["entry_score"] = holding["entry_score"]
    if holding.get("note"):
        entry["entry_note"] = holding["note"]
    if close_note:
        entry["close_note"] = close_note
    return entry


def append(entry: dict) -> None:
    entries = load_closed()
    entries.append(entry)
    save_closed(entries)


def stats() -> dict:
    """Aggregate realized-P&L statistics from the archive."""
    entries = load_closed()
    if not entries:
        return {
            "count": 0,
            "total_realized_pnl": 0.0,
            "win_rate": None,
            "avg_hold_days": None,
            "best_trade": None,
            "worst_trade": None,
            "avg_return_pct": None,
        }

    total_pnl = sum(e.get("realized_pnl", 0) for e in entries)
    wins = [e for e in entries if e.get("realized_pnl", 0) > 0]
    hold_days_list = [e["hold_days"] for e in entries if e.get("hold_days") is not None]
    returns_pct = [e.get("realized_pnl_pct", 0) for e in entries]

    best = max(entries, key=lambda e: e.get("realized_pnl_pct", 0))
    worst = min(entries, key=lambda e: e.get("realized_pnl_pct", 0))

    return {
        "count": len(entries),
        "total_realized_pnl": round(total_pnl, 2),
        "win_rate": round(len(wins) / len(entries) * 100, 1),
        "avg_hold_days": round(sum(hold_days_list) / len(hold_days_list), 1) if hold_days_list else None,
        "avg_return_pct": round(sum(returns_pct) / len(returns_pct), 2),
        "best_trade": {"ticker": best["ticker"], "pnl_pct": best.get("realized_pnl_pct", 0), "pnl": best.get("realized_pnl", 0)},
        "worst_trade": {"ticker": worst["ticker"], "pnl_pct": worst.get("realized_pnl_pct", 0), "pnl": worst.get("realized_pnl", 0)},
    }
