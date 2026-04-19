"""One-time backfill: reconstruct closed_holdings.json from git history of holdings.json.

Strategy:
  1. Walk every commit that touched data/holdings.json, in order.
  2. For each transition, identify tickers that were removed (full close).
  3. Derive exit_price from (in priority order):
       a) commit message pattern like "SELL TICKER <n>sh @ $<price>"
       b) daily snapshot close price on the commit date (nearest trading day)
       c) None (flagged for manual review)
  4. Build closed-holdings entry per full-close event. Partial sells (shares
     decreased but position retained) are NOT recorded here — those stay as
     notes on the open holding.

Usage:
    python3 -m src.backfill_closed_holdings --dry-run          # print proposed, don't write
    python3 -m src.backfill_closed_holdings --dry-run --verbose
    python3 -m src.backfill_closed_holdings --write            # write (fails if archive non-empty)
    python3 -m src.backfill_closed_holdings --write --force    # overwrite existing archive
"""

import argparse
import json
import re
import subprocess
import sys
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Optional

from .closed_holdings import CLOSED_FILE, DATA_DIR, build_entry, save_closed, load_closed

REPO_ROOT = Path(__file__).resolve().parent.parent
HOLDINGS_PATH = "data/holdings.json"
SNAPSHOTS_DIR = DATA_DIR / "daily_snapshots"

# "SELL TICKER 1.23sh @ $45.67" or "Sell TICKER..."
SELL_RE = re.compile(
    r"\b(?:SELL|Sell)\s+([A-Z]{1,6})\s+[\d.]+\s*sh(?:ares)?\s*@\s*\$?([\d.]+)",
)


def _run_git(*args: str) -> str:
    out = subprocess.check_output(["git", *args], cwd=REPO_ROOT, text=True, errors="replace")
    return out


def _commits_touching_holdings() -> list[tuple[str, str, str]]:
    """Returns [(sha, iso_date, subject), ...] oldest→newest."""
    raw = _run_git(
        "log",
        "--reverse",
        "--pretty=format:%H\t%cI\t%s",
        "--",
        HOLDINGS_PATH,
    )
    out = []
    for line in raw.strip().split("\n"):
        if not line:
            continue
        parts = line.split("\t", 2)
        if len(parts) == 3:
            sha, iso, subject = parts
            out.append((sha, iso[:10], subject))
    return out


def _holdings_at(sha: str) -> dict:
    """Returns {ticker: {...}} dict at the given commit."""
    try:
        raw = _run_git("show", f"{sha}:{HOLDINGS_PATH}")
    except subprocess.CalledProcessError:
        return {}
    try:
        data = json.loads(raw)
        return data.get("holdings", {}) if isinstance(data, dict) else {}
    except json.JSONDecodeError:
        return {}


def _snapshot_close(ticker: str, ref_date: str, window_days: int = 5) -> Optional[float]:
    """Find close price for ticker in daily snapshots, searching ±window_days."""
    try:
        anchor = date.fromisoformat(ref_date)
    except ValueError:
        return None
    # Walk backward first, then forward
    for offset in range(0, window_days + 1):
        for delta in ((-offset,), (offset,)) if offset else ((0,),):
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
                        price = s.get("current_price") or s.get("price")
                        if price:
                            return float(price)
    return None


def _parse_sell_price(subject: str, ticker: str) -> Optional[float]:
    for m in SELL_RE.finditer(subject):
        if m.group(1).upper() == ticker.upper():
            try:
                return float(m.group(2))
            except ValueError:
                continue
    return None


def backfill(dry_run: bool, force: bool, verbose: bool) -> int:
    existing = load_closed()
    if existing and not force and not dry_run:
        print(
            f"ERROR: {CLOSED_FILE.name} already has {len(existing)} entries. "
            f"Use --force to overwrite or --dry-run to preview.",
            file=sys.stderr,
        )
        return 1

    commits = _commits_touching_holdings()
    if not commits:
        print("No commits touch data/holdings.json — nothing to backfill.", file=sys.stderr)
        return 1

    print(f"Scanning {len(commits)} commits touching {HOLDINGS_PATH}...", file=sys.stderr)

    prev = {}
    reconstructed: list[dict] = []
    unresolved: list[tuple[str, str]] = []

    for sha, commit_date, subject in commits:
        current = _holdings_at(sha)
        removed = set(prev.keys()) - set(current.keys())

        for ticker in sorted(removed):
            prior = prev[ticker]
            # 1) commit message
            price = _parse_sell_price(subject, ticker)
            source = "commit-message"
            # 2) daily snapshot
            if price is None:
                price = _snapshot_close(ticker, commit_date)
                source = "snapshot" if price is not None else None
            # 3) none
            if price is None:
                unresolved.append((ticker, commit_date))
                if verbose:
                    print(f"  [UNRESOLVED] {ticker} sold {commit_date} — no price found")
                continue

            entry = build_entry(
                ticker=ticker,
                holding=prior,
                exit_price=price,
                exit_date=commit_date,
                close_note=f"Backfilled from git ({source}): {subject[:80]}",
            )
            reconstructed.append(entry)
            if verbose:
                print(
                    f"  [{source}] {ticker} sold {commit_date} @ ${price:.2f} "
                    f"(held {entry['hold_days']}d, {entry['realized_pnl_pct']:+.1f}%)"
                )

        prev = current

    print(
        f"\nReconstructed: {len(reconstructed)} closes / Unresolved: {len(unresolved)}",
        file=sys.stderr,
    )
    if unresolved:
        print("Unresolved closes (no exit price — add manually if needed):", file=sys.stderr)
        for t, d in unresolved:
            print(f"  - {t} on {d}", file=sys.stderr)

    if dry_run:
        print("\n--- DRY RUN: would write the following ---")
        print(json.dumps({"closed": reconstructed, "count": len(reconstructed)}, indent=2, default=str))
        return 0

    save_closed(reconstructed)
    print(f"Wrote {len(reconstructed)} entries to {CLOSED_FILE}")
    return 0


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--dry-run", action="store_true", help="Print proposed entries without writing")
    p.add_argument("--write", action="store_true", help="Write to closed_holdings.json")
    p.add_argument("--force", action="store_true", help="Overwrite existing archive")
    p.add_argument("--verbose", "-v", action="store_true", help="Per-ticker output")
    args = p.parse_args()

    if not args.dry_run and not args.write:
        p.error("specify --dry-run or --write")

    return backfill(dry_run=args.dry_run, force=args.force, verbose=args.verbose)


if __name__ == "__main__":
    sys.exit(main())
