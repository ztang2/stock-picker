"""Holdings CLI — add, remove, update, list entries in data/holdings.json.

Usage:
    python -m src.holdings list
    python -m src.holdings add EQT 12.25 57.12 [--date 2026-04-16] [--score 82.7] [--note "..."]
    python -m src.holdings remove NFLX
    python -m src.holdings set EQT --shares 15 --price 58.00
"""

import argparse
import sys
from datetime import date

from .rebalance import load_holdings, save_holdings


def _print_holdings(holdings: dict) -> None:
    if not holdings:
        print("(no holdings)")
        return
    print(f"{'TICKER':<8} {'SHARES':>12} {'ENTRY':>10} {'DATE':>12}  NOTE")
    print("-" * 60)
    for ticker in sorted(holdings.keys()):
        h = holdings[ticker]
        note = h.get("note", "")
        print(
            f"{ticker:<8} {h.get('shares', 0):>12.4f} "
            f"{h.get('entry_price', 0):>10.2f} "
            f"{h.get('entry_date', ''):>12}  {note}"
        )


def cmd_list(_args) -> int:
    _print_holdings(load_holdings())
    return 0


def cmd_add(args) -> int:
    holdings = load_holdings()
    ticker = args.ticker.upper()
    if ticker in holdings:
        print(f"Error: {ticker} already exists. Use `set` to update.", file=sys.stderr)
        return 1
    entry = {
        "shares": args.shares,
        "entry_price": args.price,
        "entry_date": args.date or date.today().isoformat(),
    }
    if args.score is not None:
        entry["entry_score"] = args.score
    if args.note:
        entry["note"] = args.note
    holdings[ticker] = entry
    save_holdings(holdings)
    print(f"Added {ticker}: {args.shares} shares @ {args.price}")
    return 0


def cmd_remove(args) -> int:
    holdings = load_holdings()
    ticker = args.ticker.upper()
    if ticker not in holdings:
        print(f"Error: {ticker} not in holdings.", file=sys.stderr)
        return 1
    removed = holdings.pop(ticker)
    save_holdings(holdings)
    print(f"Removed {ticker} ({removed.get('shares')} shares)")
    return 0


def cmd_set(args) -> int:
    holdings = load_holdings()
    ticker = args.ticker.upper()
    if ticker not in holdings:
        print(f"Error: {ticker} not in holdings. Use `add` first.", file=sys.stderr)
        return 1
    entry = holdings[ticker]
    if args.shares is not None:
        entry["shares"] = args.shares
    if args.price is not None:
        entry["entry_price"] = args.price
    if args.date is not None:
        entry["entry_date"] = args.date
    if args.score is not None:
        entry["entry_score"] = args.score
    if args.note is not None:
        entry["note"] = args.note
    holdings[ticker] = entry
    save_holdings(holdings)
    print(f"Updated {ticker}: {entry}")
    return 0


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="python -m src.holdings", description=__doc__)
    sub = parser.add_subparsers(dest="cmd", required=True)

    sub.add_parser("list", help="List all holdings")

    p_add = sub.add_parser("add", help="Add a new holding")
    p_add.add_argument("ticker")
    p_add.add_argument("shares", type=float)
    p_add.add_argument("price", type=float, help="entry price")
    p_add.add_argument("--date", help="YYYY-MM-DD (default: today)")
    p_add.add_argument("--score", type=float, help="entry score (optional)")
    p_add.add_argument("--note", help="free-form note")

    p_rm = sub.add_parser("remove", help="Remove a holding")
    p_rm.add_argument("ticker")

    p_set = sub.add_parser("set", help="Update fields on an existing holding")
    p_set.add_argument("ticker")
    p_set.add_argument("--shares", type=float)
    p_set.add_argument("--price", type=float)
    p_set.add_argument("--date")
    p_set.add_argument("--score", type=float)
    p_set.add_argument("--note")

    args = parser.parse_args(argv)
    handlers = {"list": cmd_list, "add": cmd_add, "remove": cmd_remove, "set": cmd_set}
    return handlers[args.cmd](args)


if __name__ == "__main__":
    sys.exit(main())
