"""Dynamic backtest — replays the picker's day-to-day decisions over historical snapshots.

Unlike `src/backtest.py` (which picks top-20 from N months ago and holds passively
to today), this engine walks each daily snapshot and applies the model's actual
operating mode: sell when sell signals fire, buy when slots open, respect min-hold,
stop-loss at -15%. The result is a realistic measurement of the strategy you
actually run, not the strategy nobody runs.

Usage:
    python3 -m src.dynamic_backtest
    python3 -m src.dynamic_backtest --start 2026-03-01 --max-positions 10 --verbose
    python3 -m src.dynamic_backtest --json > /tmp/dynamic.json
"""

import argparse
import json
import sys
from dataclasses import dataclass, field
from datetime import date, datetime
from glob import glob
from pathlib import Path
from typing import Optional

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
SNAPSHOTS_DIR = DATA_DIR / "daily_snapshots"


@dataclass
class Position:
    ticker: str
    shares: float
    entry_price: float
    entry_date: date
    entry_score: float
    last_price: float = 0.0
    last_score: float = 0.0


@dataclass
class Transaction:
    date: date
    action: str  # "BUY" or "SELL"
    ticker: str
    shares: float
    price: float
    pnl: Optional[float] = None
    reason: Optional[str] = None
    score: Optional[float] = None


@dataclass
class BacktestState:
    cash: float
    positions: dict[str, Position] = field(default_factory=dict)
    transactions: list[Transaction] = field(default_factory=list)
    equity_curve: list[dict] = field(default_factory=list)


def _parse_date(s: str) -> date:
    return date.fromisoformat(s)


def _load_snapshot(path: Path) -> Optional[dict]:
    try:
        return json.loads(path.read_text())
    except Exception:
        return None


def _snapshot_paths(start: Optional[date], end: Optional[date]) -> list[Path]:
    paths = sorted(SNAPSHOTS_DIR.glob("*.json"))
    out = []
    for p in paths:
        try:
            d = _parse_date(p.stem)
        except ValueError:
            continue
        if start and d < start:
            continue
        if end and d > end:
            continue
        out.append(p)
    return out


def _index(snap: dict) -> dict[str, dict]:
    """Map ticker -> stock dict from snapshot. Prefer top, augment with all_scores."""
    by_ticker = {}
    for s in snap.get("all_scores", []) or []:
        if s.get("ticker"):
            by_ticker[s["ticker"]] = s
    for s in snap.get("top", []) or []:
        if s.get("ticker"):
            by_ticker[s["ticker"]] = s  # top wins (more enriched)
    return by_ticker


def _evaluate_sells(state: BacktestState, today: date, by_ticker: dict, min_hold_days: int,
                    stop_loss_pct: float) -> list[str]:
    """Return list of tickers to sell, with reasons recorded into transactions."""
    to_sell = []
    for tkr, pos in list(state.positions.items()):
        s = by_ticker.get(tkr)
        if not s:
            continue  # ticker dropped from universe — hold at last known price
        price = s.get("current_price")
        if not price:
            continue

        pos.last_price = float(price)
        pos.last_score = float(s.get("composite_score") or 0)

        days_held = (today - pos.entry_date).days
        pnl_pct = (pos.last_price - pos.entry_price) / pos.entry_price * 100

        # Stop-loss overrides min-hold
        if pnl_pct <= stop_loss_pct:
            to_sell.append((tkr, f"stop-loss {pnl_pct:.1f}% <= {stop_loss_pct:.1f}%"))
            continue

        if days_held < min_hold_days:
            continue

        sell_signal = (s.get("sell_signal") or "").upper()
        if sell_signal in ("SELL", "STRONG_SELL"):
            reasons = s.get("sell_reasons") or []
            reason_str = "; ".join(reasons[:2]) if reasons else sell_signal
            to_sell.append((tkr, f"{sell_signal}: {reason_str}"))
            continue

        entry_signal = (s.get("entry_signal") or "").upper()
        if entry_signal in ("AVOID", "WAIT"):
            to_sell.append((tkr, f"entry signal degraded to {entry_signal}"))
            continue

        # Score decay
        if pos.entry_score - pos.last_score >= 15:
            to_sell.append((tkr, f"score decay {pos.entry_score:.0f}->{pos.last_score:.0f}"))
            continue

    # Execute sells
    sold = []
    for tkr, reason in to_sell:
        pos = state.positions[tkr]
        proceeds = pos.shares * pos.last_price
        state.cash += proceeds
        pnl = (pos.last_price - pos.entry_price) * pos.shares
        state.transactions.append(
            Transaction(date=today, action="SELL", ticker=tkr, shares=pos.shares,
                        price=pos.last_price, pnl=round(pnl, 2), reason=reason)
        )
        sold.append(tkr)
        del state.positions[tkr]
    return sold


def _evaluate_buys(state: BacktestState, today: date, snap: dict, max_positions: int,
                   min_score: float, target_weight: float) -> list[str]:
    """Fill empty slots with top BUY signals not already held."""
    bought = []
    open_slots = max_positions - len(state.positions)
    if open_slots <= 0 or state.cash <= 0:
        return bought

    # Use snapshot's top list (already sector-capped + ranked)
    top = snap.get("top", []) or []
    candidates = [
        s for s in top
        if s.get("ticker") not in state.positions
        and (s.get("entry_signal") or "").upper() in ("BUY", "STRONG_BUY")
        and (s.get("composite_score") or 0) >= min_score
        and s.get("current_price")
    ]

    # Position sizing: target_weight of total equity, capped by available cash
    position_value = sum(p.shares * p.last_price for p in state.positions.values())
    total_equity = state.cash + position_value
    target_dollar = total_equity * target_weight

    for c in candidates[:open_slots]:
        tkr = c["ticker"]
        price = float(c["current_price"])
        slot_dollar = min(target_dollar, state.cash)
        if slot_dollar < price:  # can't afford even 1 share
            continue
        shares = slot_dollar / price
        cost = shares * price
        state.cash -= cost
        state.positions[tkr] = Position(
            ticker=tkr,
            shares=shares,
            entry_price=price,
            entry_date=today,
            entry_score=float(c.get("composite_score") or 0),
            last_price=price,
            last_score=float(c.get("composite_score") or 0),
        )
        state.transactions.append(
            Transaction(date=today, action="BUY", ticker=tkr, shares=shares,
                        price=price, score=c.get("composite_score"))
        )
        bought.append(tkr)
        if state.cash <= 0:
            break
    return bought


def _spy_returns(start_date: date, end_date: date) -> Optional[tuple[float, float, float]]:
    """Fetch SPY price at start and end via yfinance; returns (start_price, end_price, return_pct)."""
    try:
        import yfinance as yf
        from datetime import timedelta
        spy = yf.Ticker("SPY").history(
            start=(start_date - timedelta(days=5)).isoformat(),
            end=(end_date + timedelta(days=2)).isoformat(),
        )
        if spy is None or spy.empty:
            return None
        # Find first date >= start_date and last date <= end_date
        spy.index = spy.index.tz_localize(None) if spy.index.tz else spy.index
        first = spy[spy.index.date >= start_date]
        last = spy[spy.index.date <= end_date]
        if first.empty or last.empty:
            return None
        sp = float(first["Close"].iloc[0])
        ep = float(last["Close"].iloc[-1])
        return sp, ep, (ep - sp) / sp * 100
    except Exception as e:
        print(f"SPY fetch failed: {e}", file=sys.stderr)
        return None


def run(
    start: Optional[date] = None,
    end: Optional[date] = None,
    starting_cash: float = 10_000.0,
    max_positions: int = 10,
    min_score: float = 60.0,
    target_weight: float = 0.10,
    min_hold_days: int = 7,
    stop_loss_pct: float = -15.0,
    verbose: bool = False,
) -> dict:
    paths = _snapshot_paths(start, end)
    if len(paths) < 2:
        raise SystemExit(f"Need at least 2 snapshots in range; found {len(paths)}.")

    state = BacktestState(cash=starting_cash)
    first_date = _parse_date(paths[0].stem)
    last_date = _parse_date(paths[-1].stem)

    skipped = 0
    for p in paths:
        snap = _load_snapshot(p)
        if not snap or not snap.get("top") or not snap.get("all_scores"):
            skipped += 1
            continue
        today = _parse_date(p.stem)
        by_ticker = _index(snap)

        # Update last_price for all held positions BEFORE sells (so equity is current)
        for tkr, pos in state.positions.items():
            s = by_ticker.get(tkr)
            if s and s.get("current_price"):
                pos.last_price = float(s["current_price"])

        sold = _evaluate_sells(state, today, by_ticker, min_hold_days, stop_loss_pct)
        bought = _evaluate_buys(state, today, snap, max_positions, min_score, target_weight)

        position_value = sum(p.shares * p.last_price for p in state.positions.values())
        total = state.cash + position_value
        state.equity_curve.append({
            "date": today.isoformat(),
            "cash": round(state.cash, 2),
            "position_value": round(position_value, 2),
            "total": round(total, 2),
            "positions": len(state.positions),
        })

        if verbose and (sold or bought):
            print(f"{today}  ${total:>9,.0f}  pos={len(state.positions):2}  "
                  f"sold={','.join(sold) or '-':<20}  bought={','.join(bought) or '-'}")

    # Liquidate remaining positions at last known price for final return
    final_position_value = sum(p.shares * p.last_price for p in state.positions.values())
    final_total = state.cash + final_position_value

    total_return_pct = (final_total - starting_cash) / starting_cash * 100

    spy_data = _spy_returns(first_date, last_date)

    realized_pnl = sum(t.pnl or 0 for t in state.transactions if t.action == "SELL")
    n_trades = sum(1 for t in state.transactions if t.action == "SELL")
    n_buys = sum(1 for t in state.transactions if t.action == "BUY")
    wins = sum(1 for t in state.transactions if t.action == "SELL" and (t.pnl or 0) > 0)
    win_rate = (wins / n_trades * 100) if n_trades > 0 else None

    # Max drawdown of equity curve
    peak = starting_cash
    max_dd = 0.0
    for pt in state.equity_curve:
        if pt["total"] > peak:
            peak = pt["total"]
        dd = (pt["total"] - peak) / peak * 100
        if dd < max_dd:
            max_dd = dd

    result = {
        "config": {
            "start": first_date.isoformat(),
            "end": last_date.isoformat(),
            "trading_days": len(state.equity_curve),
            "snapshots_skipped": skipped,
            "starting_cash": starting_cash,
            "max_positions": max_positions,
            "min_score": min_score,
            "target_weight_pct": target_weight * 100,
            "min_hold_days": min_hold_days,
            "stop_loss_pct": stop_loss_pct,
        },
        "performance": {
            "ending_value": round(final_total, 2),
            "total_return_pct": round(total_return_pct, 2),
            "realized_pnl": round(realized_pnl, 2),
            "unrealized_pnl": round(final_position_value - sum(p.shares * p.entry_price for p in state.positions.values()), 2),
            "max_drawdown_pct": round(max_dd, 2),
            "n_buys": n_buys,
            "n_sells": n_trades,
            "trade_win_rate_pct": round(win_rate, 1) if win_rate is not None else None,
        },
        "vs_spy": (
            {
                "spy_start": round(spy_data[0], 2),
                "spy_end": round(spy_data[1], 2),
                "spy_return_pct": round(spy_data[2], 2),
                "alpha_pct": round(total_return_pct - spy_data[2], 2),
            }
            if spy_data else None
        ),
        "open_positions": [
            {
                "ticker": p.ticker,
                "shares": round(p.shares, 4),
                "entry_price": round(p.entry_price, 2),
                "entry_date": p.entry_date.isoformat(),
                "current_price": round(p.last_price, 2),
                "pnl_pct": round((p.last_price - p.entry_price) / p.entry_price * 100, 2),
            }
            for p in state.positions.values()
        ],
        "transactions": [
            {
                "date": t.date.isoformat(), "action": t.action, "ticker": t.ticker,
                "shares": round(t.shares, 4), "price": round(t.price, 2),
                **({"pnl": t.pnl, "reason": t.reason} if t.action == "SELL" else {"score": t.score}),
            }
            for t in state.transactions
        ],
        "equity_curve": state.equity_curve,
    }
    return result


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--start", help="Start date (YYYY-MM-DD); defaults to earliest snapshot")
    p.add_argument("--end", help="End date (YYYY-MM-DD); defaults to latest snapshot")
    p.add_argument("--cash", type=float, default=10_000, help="Starting cash (default 10000)")
    p.add_argument("--max-positions", type=int, default=10, help="Max concurrent positions (default 10)")
    p.add_argument("--min-score", type=float, default=60, help="Min composite score to enter (default 60)")
    p.add_argument("--target-weight", type=float, default=0.10, help="Target % of equity per position (default 0.10)")
    p.add_argument("--min-hold-days", type=int, default=7, help="Min hold before sell signals trigger (default 7)")
    p.add_argument("--stop-loss", type=float, default=-15, help="Stop-loss % (default -15)")
    p.add_argument("--verbose", "-v", action="store_true", help="Per-trade output")
    p.add_argument("--json", action="store_true", help="Emit full JSON instead of human summary")
    args = p.parse_args()

    result = run(
        start=_parse_date(args.start) if args.start else None,
        end=_parse_date(args.end) if args.end else None,
        starting_cash=args.cash,
        max_positions=args.max_positions,
        min_score=args.min_score,
        target_weight=args.target_weight,
        min_hold_days=args.min_hold_days,
        stop_loss_pct=args.stop_loss,
        verbose=args.verbose,
    )

    if args.json:
        print(json.dumps(result, indent=2, default=str))
        return 0

    cfg = result["config"]
    perf = result["performance"]
    spy = result["vs_spy"]

    print(f"\n=== Dynamic backtest: {cfg['start']} → {cfg['end']} ===")
    print(f"  {cfg['trading_days']} trading days, {cfg['snapshots_skipped']} snapshots skipped")
    print(f"  config: max_pos={cfg['max_positions']}, target_wt={cfg['target_weight_pct']:.0f}%, "
          f"min_score={cfg['min_score']}, min_hold={cfg['min_hold_days']}d, stop={cfg['stop_loss_pct']:.0f}%")
    print()
    print(f"  Starting:        ${cfg['starting_cash']:>10,.2f}")
    print(f"  Ending:          ${perf['ending_value']:>10,.2f}")
    print(f"  Total return:    {perf['total_return_pct']:>+10.2f}%")
    print(f"  Realized P&L:    ${perf['realized_pnl']:>+10,.2f}")
    print(f"  Unrealized:      ${perf['unrealized_pnl']:>+10,.2f}")
    print(f"  Max drawdown:    {perf['max_drawdown_pct']:>+10.2f}%")
    print(f"  Trades:          {perf['n_buys']} buys, {perf['n_sells']} sells, "
          f"{perf['trade_win_rate_pct'] or 0:.0f}% win rate")
    if spy:
        print()
        print(f"  SPY:             {spy['spy_return_pct']:>+10.2f}%  (${spy['spy_start']} → ${spy['spy_end']})")
        print(f"  Alpha vs SPY:    {spy['alpha_pct']:>+10.2f}%")
    print()
    print(f"  Open positions ({len(result['open_positions'])}):")
    for op in result["open_positions"]:
        print(f"    {op['ticker']:<6} {op['shares']:>9.2f} sh @ ${op['entry_price']:>7.2f} → "
              f"${op['current_price']:>7.2f}  ({op['pnl_pct']:>+6.2f}%)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
