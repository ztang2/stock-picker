"""Backfill entry_score for existing holdings using daily_snapshots.

For each holding without an entry_score, look up the snapshot from the holding's
entry_date and find the ticker's composite_score. Skip holdings whose entry_date
predates the snapshot collection (those are unrecoverable).

Usage:
    python3 -m src.backfill_entry_scores --dry-run
    python3 -m src.backfill_entry_scores --write
    python3 -m src.backfill_entry_scores --write --force  # overwrite existing scores
"""

import argparse
import json
import sys
from datetime import date, timedelta
from pathlib import Path
from typing import Optional

from .rebalance import load_holdings, save_holdings

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
SNAPSHOTS_DIR = DATA_DIR / "daily_snapshots"


def _find_snapshot_score(ticker: str, target_date: str, window_days: int = 5) -> tuple[Optional[float], Optional[str]]:
    """Look for ticker's composite_score in snapshot at or near target_date.
    Searches +/- window_days. Returns (score, snapshot_date_used) or (None, None).
    """
    try:
        anchor = date.fromisoformat(target_date)
    except ValueError:
        return None, None
    for offset in range(0, window_days + 1):
        for delta in ((0,),) if offset == 0 else ((-offset,), (offset,)):
            d = anchor + timedelta(days=delta[0])
            snap = SNAPSHOTS_DIR / f"{d.isoformat()}.json"
            if not snap.exists():
                continue
            try:
                data = json.loads(snap.read_text())
            except (json.JSONDecodeError, OSError):
                continue
            for key in ("all_scores", "top", "stocks"):
                for s in data.get(key, []) or []:
                    if s.get("ticker") == ticker:
                        score = s.get("composite_score")
                        if score is not None:
                            return float(score), d.isoformat()
    return None, None


def backfill(dry_run: bool, force: bool, verbose: bool) -> int:
    holdings = load_holdings()
    if not holdings:
        print("No holdings to backfill.", file=sys.stderr)
        return 0

    updates: list[tuple[str, float, str]] = []  # (ticker, score, snapshot_date)
    skipped: list[tuple[str, str]] = []         # (ticker, reason)

    for ticker, h in holdings.items():
        existing = h.get("entry_score")
        if existing is not None and not force:
            if verbose:
                print(f"  [SKIP] {ticker}: already has entry_score={existing}")
            continue
        entry_date = h.get("entry_date")
        if not entry_date:
            skipped.append((ticker, "no entry_date"))
            continue
        score, snap_date = _find_snapshot_score(ticker, entry_date)
        if score is None:
            skipped.append((ticker, f"no snapshot near {entry_date}"))
            continue
        updates.append((ticker, score, snap_date))
        if verbose:
            day_offset = (date.fromisoformat(snap_date) - date.fromisoformat(entry_date)).days
            offset_s = "" if day_offset == 0 else f" ({day_offset:+d}d)"
            existing_s = f" (was {existing})" if existing is not None else ""
            print(f"  [FILL] {ticker}: entry_date={entry_date}, snapshot={snap_date}{offset_s}, score={score:.2f}{existing_s}")

    print(f"\nWould update: {len(updates)}  Skipped: {len(skipped)}", file=sys.stderr)
    for t, r in skipped:
        print(f"  - {t}: {r}", file=sys.stderr)

    if dry_run or not updates:
        if dry_run:
            print("\n--- DRY RUN: no writes ---")
        return 0

    for ticker, score, _ in updates:
        holdings[ticker]["entry_score"] = round(score, 2)
    save_holdings(holdings)
    print(f"\nWrote {len(updates)} entry_score values to data/holdings.json")
    return 0


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--dry-run", action="store_true", help="Print proposed updates without writing")
    p.add_argument("--write", action="store_true", help="Apply updates to data/holdings.json")
    p.add_argument("--force", action="store_true", help="Overwrite existing entry_score values")
    p.add_argument("--verbose", "-v", action="store_true", help="Per-ticker output")
    args = p.parse_args()

    if not args.dry_run and not args.write:
        p.error("specify --dry-run or --write")

    return backfill(dry_run=args.dry_run, force=args.force, verbose=args.verbose)


if __name__ == "__main__":
    sys.exit(main())
