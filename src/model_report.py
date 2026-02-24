"""Factor attribution report — analyze which scoring factors contribute most to alpha."""

import json
import logging
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional

import numpy as np

from .backtest import ROLLING_BACKTEST_FILE, load_backtest_history
from .pipeline import load_config, DATA_DIR, RESULTS_FILE

logger = logging.getLogger(__name__)


def _load_rolling_data() -> Optional[dict]:
    """Load rolling backtest data."""
    if ROLLING_BACKTEST_FILE.exists():
        try:
            return json.loads(ROLLING_BACKTEST_FILE.read_text())
        except Exception:
            return None
    return None


def _load_scan_results() -> Optional[dict]:
    """Load latest scan results for factor score analysis."""
    if RESULTS_FILE.exists():
        try:
            return json.loads(RESULTS_FILE.read_text())
        except Exception:
            return None
    return None


def _analyze_strategy_factors(rolling_data: dict, strategy: str, months: int = 3) -> dict:
    """Analyze factor performance for a strategy over recent months."""
    strat_data = rolling_data.get("strategies", {}).get(strategy, {})
    periods = strat_data.get("periods", [])
    horizons = strat_data.get("horizons", {})

    if not periods:
        return {"error": "No data for strategy"}

    # Use last N months of periods
    recent = periods[-months:] if len(periods) >= months else periods

    # Compute performance metrics for recent periods
    metrics = {}
    for h in ["1m", "3m", "6m"]:
        alphas = [p[f"{h}_alpha"] for p in recent if p.get(f"{h}_alpha") is not None]
        returns = [p[f"{h}_return"] for p in recent if p.get(f"{h}_return") is not None]
        spy_returns = [p[f"{h}_spy"] for p in recent if p.get(f"{h}_spy") is not None]

        if alphas:
            arr = np.array(alphas)
            metrics[h] = {
                "avg_alpha": round(float(np.mean(arr)), 4),
                "win_rate": round(float(np.sum(arr > 0) / len(arr)), 4),
                "avg_return": round(float(np.mean(returns)), 4) if returns else None,
                "avg_spy": round(float(np.mean(spy_returns)), 4) if spy_returns else None,
                "best_alpha": round(float(np.max(arr)), 4),
                "worst_alpha": round(float(np.min(arr)), 4),
                "n_periods": len(alphas),
            }

    # All-time horizon stats
    all_time = {}
    for h in ["1m", "3m", "6m"]:
        h_data = horizons.get(h, {})
        if h_data and not h_data.get("insufficient_data"):
            all_time[h] = {
                "avg_alpha": h_data.get("avg_alpha"),
                "win_rate": h_data.get("win_rate"),
                "sharpe": h_data.get("sharpe_ratio"),
                "significant": h_data.get("significant", False),
                "n_periods": h_data.get("num_periods"),
            }

    return {
        "recent": metrics,
        "all_time": all_time,
    }


def _analyze_factor_scores_from_scan() -> Optional[dict]:
    """Analyze factor score distributions from latest scan results."""
    scan = _load_scan_results()
    if not scan:
        return None

    top_stocks = scan.get("top", scan.get("stocks", []))
    if not top_stocks:
        return None

    factors = ["fundamentals", "valuation", "technicals", "risk", "growth"]
    factor_analysis = {}

    for factor in factors:
        scores = []
        for stock in top_stocks:
            score = stock.get(f"{factor}_score")
            if score is not None:
                scores.append(score)

        if scores:
            arr = np.array(scores)
            factor_analysis[factor] = {
                "mean": round(float(np.mean(arr)), 1),
                "median": round(float(np.median(arr)), 1),
                "std": round(float(np.std(arr)), 1),
                "min": round(float(np.min(arr)), 1),
                "max": round(float(np.max(arr)), 1),
                "n_stocks": len(scores),
            }

    return factor_analysis


def _compute_factor_effectiveness(rolling_data: dict) -> dict:
    """Compare strategy performances to infer which factor weights work best.

    Since conservative emphasizes fundamentals+valuation, balanced is mixed,
    and aggressive emphasizes technicals+growth, we can infer factor effectiveness
    by comparing strategy alphas.
    """
    strategies_horizons = {}
    for strat in ["conservative", "balanced", "aggressive"]:
        strat_data = rolling_data.get("strategies", {}).get(strat, {})
        horizons = strat_data.get("horizons", {})
        h1m = horizons.get("1m", {})
        strategies_horizons[strat] = {
            "alpha": h1m.get("avg_alpha", 0),
            "win_rate": h1m.get("win_rate", 0),
            "sharpe": h1m.get("sharpe_ratio", 0),
        }

    # Infer factor effectiveness from strategy comparison
    # Conservative = high fundamentals/valuation, low technicals/growth
    # Aggressive = high technicals/growth, low fundamentals/valuation
    cons = strategies_horizons.get("conservative", {})
    bal = strategies_horizons.get("balanced", {})
    agg = strategies_horizons.get("aggressive", {})

    cons_alpha = cons.get("alpha", 0) or 0
    bal_alpha = bal.get("alpha", 0) or 0
    agg_alpha = agg.get("alpha", 0) or 0

    factors = {}

    # Fundamentals: strongest in conservative
    factors["fundamentals"] = {
        "inferred_contribution": "high" if cons_alpha > agg_alpha else "moderate" if cons_alpha > 0 else "low",
        "evidence": f"Conservative (fund=40%) alpha: {cons_alpha:.4f}, Aggressive (fund=13%) alpha: {agg_alpha:.4f}",
        "working": cons_alpha > 0 or bal_alpha > 0,
    }

    # Valuation: strongest in conservative
    factors["valuation"] = {
        "inferred_contribution": "high" if cons_alpha > agg_alpha else "moderate",
        "evidence": f"Conservative (val=26%) vs Aggressive (val=8%)",
        "working": cons_alpha > 0,
    }

    # Technicals: strongest in aggressive
    factors["technicals"] = {
        "inferred_contribution": "high" if agg_alpha > cons_alpha else "moderate" if agg_alpha > 0 else "low",
        "evidence": f"Aggressive (tech=31%) alpha: {agg_alpha:.4f}, Conservative (tech=8%) alpha: {cons_alpha:.4f}",
        "working": agg_alpha > 0 or bal_alpha > 0,
    }

    # Growth: strongest in aggressive
    factors["growth"] = {
        "inferred_contribution": "high" if agg_alpha > cons_alpha else "moderate" if agg_alpha > 0 else "low",
        "evidence": f"Aggressive (growth=27%) vs Conservative (growth=0%)",
        "working": agg_alpha > 0,
    }

    # Risk: strongest in conservative
    factors["risk"] = {
        "inferred_contribution": "moderate",
        "evidence": f"Conservative (risk=13%) vs Aggressive (risk=4%)",
        "working": cons_alpha > 0,
    }

    # Sentiment: small weight everywhere
    factors["sentiment"] = {
        "inferred_contribution": "low",
        "evidence": "3-7% weight across strategies, hard to isolate",
        "working": bal_alpha > 0,
    }

    # Sector relative: same weight everywhere
    factors["sector_relative"] = {
        "inferred_contribution": "moderate",
        "evidence": "10% weight across all strategies",
        "working": True,
    }

    return {
        "factors": factors,
        "strategy_comparison": strategies_horizons,
        "best_strategy_1m": max(strategies_horizons.items(), key=lambda x: x[1].get("alpha", 0))[0],
    }


def generate_factor_report(months: int = 3) -> dict:
    """Generate comprehensive factor attribution report.

    Args:
        months: Number of recent months to analyze.

    Returns:
        Dict with factor analysis, strategy comparison, and recommendations.
    """
    rolling_data = _load_rolling_data()
    if not rolling_data:
        return {"error": "No rolling backtest data. Run /backtest/rolling first."}

    report = {
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "analysis_months": months,
        "data_years": rolling_data.get("years", 0),
        "total_periods": rolling_data.get("periods_evaluated", 0),
    }

    # Strategy-level analysis
    report["strategies"] = {}
    for strat in ["conservative", "balanced", "aggressive"]:
        report["strategies"][strat] = _analyze_strategy_factors(rolling_data, strat, months)

    # Factor effectiveness
    report["factor_effectiveness"] = _compute_factor_effectiveness(rolling_data)

    # Current scan factor distributions
    factor_scores = _analyze_factor_scores_from_scan()
    if factor_scores:
        report["current_factor_distributions"] = factor_scores

    # Recommendations
    best_strat = report["factor_effectiveness"].get("best_strategy_1m", "balanced")
    factors = report["factor_effectiveness"].get("factors", {})

    working = [f for f, d in factors.items() if d.get("working")]
    not_working = [f for f, d in factors.items() if not d.get("working")]

    report["recommendations"] = {
        "best_strategy": best_strat,
        "working_factors": working,
        "underperforming_factors": not_working,
        "suggestion": (
            f"Best performing strategy: {best_strat}. "
            f"Factors contributing to alpha: {', '.join(working)}. "
            + (f"Consider reducing weight on: {', '.join(not_working)}. " if not_working else "")
        ),
    }

    return report


def format_report_discord(report: dict) -> str:
    """Format factor report for Discord (no markdown tables)."""
    if "error" in report:
        return f"❌ **Factor Report Error:** {report['error']}"

    lines = []
    lines.append("📊 **Factor Attribution Report**")
    lines.append(f"*{report.get('timestamp', 'N/A')} | {report.get('data_years', '?')}yr data | {report.get('analysis_months', '?')}mo analysis window*")
    lines.append("")

    # Strategy comparison
    lines.append("**Strategy Performance (1-month alpha):**")
    for strat in ["conservative", "balanced", "aggressive"]:
        strat_data = report.get("strategies", {}).get(strat, {})
        recent = strat_data.get("recent", {}).get("1m", {})
        all_time = strat_data.get("all_time", {}).get("1m", {})

        emoji = {"conservative": "🛡️", "balanced": "⚖️", "aggressive": "🚀"}.get(strat, "")
        alpha_r = recent.get("avg_alpha", "N/A")
        wr_r = recent.get("win_rate", "N/A")
        alpha_a = all_time.get("avg_alpha", "N/A")
        wr_a = all_time.get("win_rate", "N/A")
        sig = "✅" if all_time.get("significant") else "❌"

        alpha_r_str = f"{alpha_r:+.2%}" if isinstance(alpha_r, (int, float)) else alpha_r
        wr_r_str = f"{wr_r:.0%}" if isinstance(wr_r, (int, float)) else wr_r
        alpha_a_str = f"{alpha_a:+.2%}" if isinstance(alpha_a, (int, float)) else alpha_a
        wr_a_str = f"{wr_a:.0%}" if isinstance(wr_a, (int, float)) else wr_a

        lines.append(f"{emoji} **{strat.title()}**: Recent α={alpha_r_str}, WR={wr_r_str} | All-time α={alpha_a_str}, WR={wr_a_str} {sig}")

    lines.append("")

    # Factor effectiveness
    lines.append("**Factor Effectiveness:**")
    factors = report.get("factor_effectiveness", {}).get("factors", {})
    for factor, data in factors.items():
        status = "✅" if data.get("working") else "⚠️"
        contrib = data.get("inferred_contribution", "?")
        lines.append(f"{status} **{factor}**: {contrib} contribution")

    lines.append("")

    # Recommendations
    recs = report.get("recommendations", {})
    lines.append("**💡 Recommendation:**")
    lines.append(recs.get("suggestion", "No recommendation available."))

    return "\n".join(lines)
