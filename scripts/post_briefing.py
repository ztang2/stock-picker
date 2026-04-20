#!/usr/bin/env python3
"""Post daily portfolio briefing to Discord.

Composes a Discord message from:
  - Portfolio P&L (from /risk/summary)
  - Position decay alerts (from /alerts/decay)
  - Market regime + new BUY signals (from /scan/cached)
  - Realized P&L stats (from /closed-holdings/stats)

Usage:
    python3 scripts/post_briefing.py            # post to Discord
    python3 scripts/post_briefing.py --dry-run  # print to stdout instead
"""

import argparse
import json
import sys
from pathlib import Path
from typing import Optional
from urllib import request, error

# Allow `from src.*` imports when run as a script
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.discord_notify import post_message  # noqa: E402

API_BASE = "http://localhost:8000"
TIMEOUT = 30


def _get(path: str) -> Optional[dict]:
    try:
        with request.urlopen(f"{API_BASE}{path}", timeout=TIMEOUT) as r:
            return json.loads(r.read().decode("utf-8"))
    except error.HTTPError as e:
        print(f"WARN: GET {path} → {e.code}", file=sys.stderr)
    except Exception as e:
        print(f"WARN: GET {path} failed: {e}", file=sys.stderr)
    return None


def _fmt_pct(v: Optional[float], plus: bool = True) -> str:
    if v is None:
        return "—"
    sign = "+" if plus and v >= 0 else ""
    return f"{sign}{v:.2f}%"


def _fmt_dollar(v: Optional[float], plus: bool = True) -> str:
    if v is None:
        return "—"
    sign = "+" if plus and v >= 0 else ""
    return f"{sign}${v:,.2f}"


def build_briefing() -> str:
    risk = _get("/risk/summary") or {}
    decay = _get("/alerts/decay") or {"alerts": [], "summary": {}}
    scan = _get("/scan/cached") or {}
    closed = _get("/closed-holdings/stats") or {}
    changes = _get("/scan/changes?days_back=1") or {}

    lines: list[str] = []

    # === Header ===
    regime = (scan.get("market_regime") or {}).get("regime") or "?"
    spy_price = (scan.get("market_regime") or {}).get("spy_price")
    spy_str = f"SPY ${spy_price:.2f}" if spy_price else "SPY —"
    lines.append(f"📊 **Daily Briefing** · regime: `{regime}` · {spy_str}")
    lines.append("")

    # === Portfolio P&L ===
    pv = risk.get("portfolio_value") or 0
    pnl = risk.get("total_pnl") or 0
    pnl_pct = risk.get("total_pnl_pct") or 0
    pnl_emoji = "🟢" if pnl >= 0 else "🔴"
    lines.append(f"{pnl_emoji} **Portfolio**: ${pv:,.2f}  ({_fmt_dollar(pnl)} / {_fmt_pct(pnl_pct)})")

    positions = risk.get("stop_loss_alerts") or []
    if positions:
        positions = sorted(positions, key=lambda p: -(p.get("pnl_pct") or 0))
        for p in positions:
            ticker = p.get("ticker", "?")
            pp = p.get("pnl_pct") or 0
            pd = p.get("pnl_dollar") or 0
            ep = p.get("entry_price") or 0
            cp = p.get("current_price") or 0
            arrow = "📈" if pp >= 0 else "📉"
            lines.append(f"  {arrow} `{ticker:<5}` {_fmt_pct(pp):>8} ({_fmt_dollar(pd):>10})  ${ep:.2f} → ${cp:.2f}")
    lines.append("")

    # === Position Decay Alerts ===
    alerts = decay.get("alerts") or []
    summary = decay.get("summary") or {}
    if alerts:
        urgent = summary.get("urgent", 0)
        warning = summary.get("warning", 0)
        info = summary.get("info", 0)
        badge = []
        if urgent: badge.append(f"🚨 {urgent} urgent")
        if warning: badge.append(f"⚠️ {warning} warning")
        if info: badge.append(f"ℹ️ {info} info")
        lines.append(f"**Position Health**: {' · '.join(badge)}")
        for a in alerts:
            sev_emoji = {"urgent": "🚨", "warning": "⚠️", "info": "ℹ️"}.get(a.get("severity", "info"), "•")
            lines.append(f"  {sev_emoji} {a.get('message', '')}")
        lines.append("")
    else:
        lines.append("✅ **Position Health**: all positions healthy")
        lines.append("")

    # === Top BUYs not held ===
    held_tickers = {p["ticker"] for p in positions}
    top = scan.get("top") or []
    new_buys = [
        s for s in top[:10]
        if s.get("ticker") not in held_tickers
        and (s.get("entry_signal") or "").upper() in ("BUY", "STRONG_BUY")
    ][:5]
    if new_buys:
        lines.append(f"🎯 **Top BUYs (not held)**:")
        for s in new_buys:
            t = s.get("ticker", "?")
            sig = s.get("entry_signal", "?")
            sc = s.get("composite_score") or 0
            sec = s.get("sector", "?")[:12]
            lines.append(f"  • `{t:<5}` {sc:>5.1f}  [{sig}]  {sec}")
        lines.append("")

    # === What Changed (since previous trading day) ===
    if changes and not changes.get("error"):
        changes_summary = changes.get("summary") or {}
        held_changes = changes.get("held_changes") or []
        new_in_top = changes.get("new_in_top") or []
        dropped = changes.get("dropped_from_top") or []
        if held_changes or new_in_top or dropped:
            prev_d = changes.get("previous_date", "?")
            lines.append(f"🔄 **What Changed** (since {prev_d})")
            # Holdings with signal change OR rank delta >= 5
            sig_changes = [c for c in held_changes if c.get("signal_changed")]
            big_rank_moves = [c for c in held_changes if not c.get("signal_changed") and abs(c.get("rank_delta") or 0) >= 5]
            for c in sig_changes:
                lines.append(f"  ⚠️ `{c['ticker']}` signal {c['previous_signal']}→{c['current_signal']} ({_fmt_pct(c.get('score_delta'))}pts)")
            for c in big_rank_moves[:3]:
                rd = c.get("rank_delta") or 0
                arrow = "📈" if rd > 0 else "📉"
                lines.append(f"  {arrow} `{c['ticker']}` rank #{c['previous_rank']}→#{c['current_rank']} (Δ{rd:+d})")
            if new_in_top:
                tickers = ", ".join(s["ticker"] for s in new_in_top[:5])
                more = f" +{len(new_in_top) - 5}" if len(new_in_top) > 5 else ""
                lines.append(f"  ➕ New in top 20: {tickers}{more}")
            if dropped:
                tickers = ", ".join(s["ticker"] for s in dropped[:5])
                more = f" +{len(dropped) - 5}" if len(dropped) > 5 else ""
                lines.append(f"  ➖ Dropped from top 20: {tickers}{more}")
            lines.append("")

    # === Realized P&L ===
    if closed and closed.get("count", 0) > 0:
        cnt = closed.get("count", 0)
        total = closed.get("total_realized_pnl") or 0
        wr = closed.get("win_rate")
        avg_hold = closed.get("avg_hold_days")
        lines.append(f"📜 **Realized**: {cnt} closed · {_fmt_dollar(total)} · "
                     f"{_fmt_pct(wr, plus=False) if wr else '—'} win · "
                     f"{int(avg_hold) if avg_hold else '—'}d avg hold")

    return "\n".join(lines).rstrip() + "\n"


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--dry-run", action="store_true", help="Print to stdout instead of posting")
    args = p.parse_args()

    msg = build_briefing()
    if args.dry_run:
        print(msg)
        return 0

    ok = post_message(msg, username="Stock Picker")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
