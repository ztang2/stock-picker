"""What changed since yesterday — daily delta computation across scans.

Uses data/daily_snapshots/ (one JSON per trading day) as the source of truth
for "as of date X" rank + score state. Computes deltas between two snapshots:

  - Held-position rank/score/signal changes
  - Top score-risers (stocks gaining the most composite score)
  - Top score-fallers
  - New entries to top 20
  - Drops from top 20

Pairs with src/position_decay.py: decay focuses on *held* position health,
this focuses on *universe-wide* rank movement.
"""

import json
from datetime import date, timedelta
from pathlib import Path
from typing import Optional

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
SNAPSHOTS_DIR = DATA_DIR / "daily_snapshots"


def _list_snapshot_dates() -> list[date]:
    """Return all available snapshot dates, oldest → newest."""
    dates = []
    for p in SNAPSHOTS_DIR.glob("*.json"):
        try:
            dates.append(date.fromisoformat(p.stem))
        except ValueError:
            continue
    return sorted(dates)


def _load_snapshot(d: date) -> Optional[dict]:
    p = SNAPSHOTS_DIR / f"{d.isoformat()}.json"
    if not p.exists():
        return None
    try:
        return json.loads(p.read_text())
    except Exception:
        return None


def _index_by_ticker(snap: dict) -> dict[str, dict]:
    by = {}
    for s in (snap.get("all_scores") or []):
        if s.get("ticker"):
            by[s["ticker"]] = s
    for s in (snap.get("top") or []):
        if s.get("ticker"):
            by[s["ticker"]] = s
    return by


def _rank_in_universe(snap_idx: dict[str, dict], ticker: str) -> Optional[int]:
    """Get global rank by composite_score (1 = best). Returns None if ticker missing."""
    if ticker not in snap_idx:
        return None
    sorted_tickers = sorted(snap_idx.keys(), key=lambda t: -(snap_idx[t].get("composite_score") or 0))
    try:
        return sorted_tickers.index(ticker) + 1
    except ValueError:
        return None


def compute_changes(
    holdings: Optional[dict[str, dict]] = None,
    days_back: int = 1,
    top_n: int = 20,
    top_movers_count: int = 5,
) -> dict:
    """Compute delta between today's scan and N days ago.

    Args:
        holdings: dict of {ticker: holding_info} for held-position deltas
        days_back: how many trading days back to compare against
        top_n: top-N for "in top list" classification
        top_movers_count: how many risers/fallers to surface
    """
    dates = _list_snapshot_dates()
    if len(dates) < 2:
        return {"error": f"Need at least 2 snapshots; have {len(dates)}"}

    today = dates[-1]
    # Pick previous = N trading days back (or earliest available)
    target_idx = max(0, len(dates) - 1 - days_back)
    previous = dates[target_idx]

    cur_snap = _load_snapshot(today) or {}
    prev_snap = _load_snapshot(previous) or {}

    cur_idx = _index_by_ticker(cur_snap)
    prev_idx = _index_by_ticker(prev_snap)

    # --- Compute global ranks (by composite_score across all_scores) ---
    def _build_ranks(idx: dict[str, dict]) -> dict[str, int]:
        sorted_t = sorted(idx.keys(), key=lambda t: -(idx[t].get("composite_score") or 0))
        return {t: i + 1 for i, t in enumerate(sorted_t)}

    cur_ranks = _build_ranks(cur_idx)
    prev_ranks = _build_ranks(prev_idx)

    # --- Held-position changes ---
    held_changes = []
    if holdings:
        for ticker in holdings:
            ticker = ticker.upper()
            cur = cur_idx.get(ticker)
            prev = prev_idx.get(ticker)
            if not cur or not prev:
                continue
            cur_rank = cur_ranks.get(ticker)
            prev_rank = prev_ranks.get(ticker)
            cur_score = cur.get("composite_score") or 0
            prev_score = prev.get("composite_score") or 0
            cur_signal = cur.get("entry_signal", "")
            prev_signal = prev.get("entry_signal", "")
            score_delta = round(cur_score - prev_score, 2)
            rank_delta = (prev_rank - cur_rank) if (cur_rank and prev_rank) else None
            # Only include if something actually changed
            if (rank_delta and abs(rank_delta) >= 1) or abs(score_delta) >= 0.5 or cur_signal != prev_signal:
                held_changes.append({
                    "ticker": ticker,
                    "current_rank": cur_rank,
                    "previous_rank": prev_rank,
                    "rank_delta": rank_delta,
                    "current_score": round(cur_score, 2),
                    "previous_score": round(prev_score, 2),
                    "score_delta": score_delta,
                    "current_signal": cur_signal,
                    "previous_signal": prev_signal,
                    "signal_changed": cur_signal != prev_signal,
                })
        # Sort: signal changes first, then biggest rank/score moves
        held_changes.sort(key=lambda c: (
            0 if c["signal_changed"] else 1,
            -abs(c.get("score_delta") or 0),
        ))

    # --- Universe-wide top movers ---
    score_deltas = []
    for ticker in cur_idx.keys() & prev_idx.keys():
        cs = cur_idx[ticker].get("composite_score") or 0
        ps = prev_idx[ticker].get("composite_score") or 0
        score_deltas.append({
            "ticker": ticker,
            "current_score": round(cs, 2),
            "previous_score": round(ps, 2),
            "score_delta": round(cs - ps, 2),
            "current_rank": cur_ranks.get(ticker),
            "previous_rank": prev_ranks.get(ticker),
            "current_signal": cur_idx[ticker].get("entry_signal", ""),
            "sector": cur_idx[ticker].get("sector", ""),
        })

    risers = [d for d in score_deltas if d["score_delta"] > 0]
    fallers = [d for d in score_deltas if d["score_delta"] < 0]
    top_risers = sorted(risers, key=lambda x: -x["score_delta"])[:top_movers_count]
    top_fallers = sorted(fallers, key=lambda x: x["score_delta"])[:top_movers_count]

    # --- New entries / drops in top N ---
    cur_top = {s["ticker"] for s in (cur_snap.get("top") or [])[:top_n]}
    prev_top = {s["ticker"] for s in (prev_snap.get("top") or [])[:top_n]}
    new_tickers = cur_top - prev_top
    dropped_tickers = prev_top - cur_top

    new_in_top = [
        {
            "ticker": t,
            "current_rank": cur_ranks.get(t),
            "current_score": round(cur_idx[t].get("composite_score") or 0, 2),
            "current_signal": cur_idx[t].get("entry_signal", ""),
            "sector": cur_idx[t].get("sector", ""),
        }
        for t in sorted(new_tickers, key=lambda x: cur_ranks.get(x, 999))
        if t in cur_idx
    ]
    dropped_from_top = [
        {
            "ticker": t,
            "previous_rank": prev_ranks.get(t),
            "current_rank": cur_ranks.get(t),
            "previous_score": round(prev_idx[t].get("composite_score") or 0, 2),
            "current_score": round(cur_idx.get(t, {}).get("composite_score") or 0, 2),
            "sector": prev_idx[t].get("sector", ""),
        }
        for t in sorted(dropped_tickers, key=lambda x: prev_ranks.get(x, 999))
        if t in prev_idx
    ]

    return {
        "current_date": today.isoformat(),
        "previous_date": previous.isoformat(),
        "days_back": (today - previous).days,
        "held_changes": held_changes,
        "top_risers": top_risers,
        "top_fallers": top_fallers,
        "new_in_top": new_in_top,
        "dropped_from_top": dropped_from_top,
        "summary": {
            "held_changed": len(held_changes),
            "new_in_top": len(new_in_top),
            "dropped_from_top": len(dropped_from_top),
            "total_universe_movers": len([d for d in score_deltas if abs(d["score_delta"]) >= 1]),
        },
    }
