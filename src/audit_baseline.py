"""
Audit Baseline Review — Compare 2/28 baseline predictions against actual performance.

Run on 3/30 to evaluate: did our model's top picks actually outperform?

Usage:
    python -m src.audit_baseline
"""

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Dict, List

import numpy as np
import pandas as pd
import yfinance as yf

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format='%(message)s')

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
BASELINE_FILE = DATA_DIR / "audit_baseline_20260228.json"


def load_baseline() -> Dict:
    """Load the 2/28 baseline."""
    if not BASELINE_FILE.exists():
        raise FileNotFoundError(f"Baseline not found: {BASELINE_FILE}")
    return json.loads(BASELINE_FILE.read_text())


def get_performance(tickers: List[str], start_date: str, end_date: str) -> Dict[str, float]:
    """Get price performance for tickers between two dates."""
    data = yf.download(tickers + ['SPY'], start=start_date, end=end_date, progress=False, threads=True)
    
    if isinstance(data.columns, pd.MultiIndex):
        available = data.columns.get_level_values(1).unique()
        results = {}
        for t in tickers + ['SPY']:
            if t in available:
                try:
                    close = data.xs(t, level=1, axis=1)['Close'].dropna()
                    if len(close) >= 2:
                        results[t] = float(close.iloc[-1] / close.iloc[0] - 1)
                except:
                    pass
        return results
    return {}


def run_audit():
    """Run the full audit comparison."""
    baseline = load_baseline()
    
    baseline_date = baseline.get("date", "2026-02-28")
    audit_date = datetime.now().strftime("%Y-%m-%d")
    
    logger.info(f"📊 AUDIT: {baseline_date} → {audit_date}")
    logger.info(f"{'='*70}")
    
    # Get all tickers from baseline
    top_stocks = baseline.get("top_20", baseline.get("top", []))
    tickers = [s["ticker"] for s in top_stocks]
    
    # Get actual performance
    perf = get_performance(tickers, baseline_date, audit_date)
    spy_return = perf.get("SPY", 0)
    
    logger.info(f"\nSPY return: {spy_return:+.2%}")
    logger.info(f"\n{'Rank':<6}{'Ticker':<8}{'Score':<8}{'Signal':<12}{'Return':>10}{'vs SPY':>10}{'Beat?':>8}")
    logger.info("-" * 62)
    
    beat_count = 0
    total_count = 0
    buy_returns = []
    hold_returns = []
    all_returns = []
    
    for s in top_stocks:
        ticker = s["ticker"]
        score = s.get("composite_score", 0)
        signal = s.get("entry_signal", "HOLD")
        ret = perf.get(ticker)
        
        if ret is None:
            logger.info(f"{s.get('rank', '?'):<6}{ticker:<8}{score:<8.1f}{signal:<12}{'N/A':>10}{'N/A':>10}")
            continue
        
        excess = ret - spy_return
        beat = ret > spy_return
        if beat:
            beat_count += 1
        total_count += 1
        all_returns.append(excess)
        
        if signal in ("BUY", "STRONG_BUY"):
            buy_returns.append(excess)
        else:
            hold_returns.append(excess)
        
        emoji = "✅" if beat else "❌"
        logger.info(f"{s.get('rank', '?'):<6}{ticker:<8}{score:<8.1f}{signal:<12}{ret:>+10.2%}{excess:>+10.2%}  {emoji}")
    
    logger.info(f"\n{'='*70}")
    logger.info(f"SUMMARY")
    logger.info(f"  Beat SPY rate: {beat_count}/{total_count} ({beat_count/total_count:.1%})" if total_count > 0 else "  No data")
    logger.info(f"  Avg excess return: {np.mean(all_returns):+.2%}" if all_returns else "  No returns")
    logger.info(f"  BUY signal excess: {np.mean(buy_returns):+.2%} ({len(buy_returns)} stocks)" if buy_returns else "  No BUY signals")
    logger.info(f"  HOLD signal excess: {np.mean(hold_returns):+.2%} ({len(hold_returns)} stocks)" if hold_returns else "  No HOLD signals")
    
    # Score correlation with performance
    if total_count > 5:
        scores = [s.get("composite_score", 0) for s in top_stocks if perf.get(s["ticker"]) is not None]
        returns = [perf[s["ticker"]] - spy_return for s in top_stocks if perf.get(s["ticker"]) is not None]
        ic = np.corrcoef(scores, returns)[0][1] if len(scores) > 2 else 0
        logger.info(f"  Score-Return IC: {ic:.3f}")
    
    # Save audit results
    audit_result = {
        "baseline_date": baseline_date,
        "audit_date": audit_date,
        "spy_return": spy_return,
        "beat_spy_rate": beat_count / total_count if total_count > 0 else 0,
        "avg_excess": float(np.mean(all_returns)) if all_returns else 0,
        "buy_excess": float(np.mean(buy_returns)) if buy_returns else 0,
        "total_stocks": total_count,
        "stocks": [
            {
                "ticker": s["ticker"],
                "score": s.get("composite_score"),
                "signal": s.get("entry_signal"),
                "return": perf.get(s["ticker"]),
                "excess": perf.get(s["ticker"], 0) - spy_return if perf.get(s["ticker"]) is not None else None,
            }
            for s in top_stocks
        ],
    }
    
    output = DATA_DIR / f"audit_result_{audit_date.replace('-','')}.json"
    output.write_text(json.dumps(audit_result, indent=2))
    logger.info(f"\nSaved to {output}")
    
    return audit_result


if __name__ == "__main__":
    run_audit()
