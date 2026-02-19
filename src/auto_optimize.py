"""Automated monthly model weight optimization.

Runs a grid search over key weights, backtests each combo,
and applies new weights only if they meaningfully improve performance.
"""

import itertools
import json
import logging
import time
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

from .pipeline import load_config, DATA_DIR
from .strategies import STRATEGIES

logger = logging.getLogger(__name__)

OPTIMIZATION_LOG = DATA_DIR / "optimization_log.json"

# Grid search space
WEIGHT_GRID = [0.10, 0.20, 0.30, 0.40]
# Keys we optimize (must sum to ~1.0 with the rest)
TUNABLE_KEYS = ["fundamentals", "valuation", "momentum_technicals"]
# Fixed-proportion keys (sentiment, sector_relative, risk) get the remainder
FIXED_RATIOS = {
    "risk": 0.30,
    "sentiment": 0.15,
    "sector_relative": 0.30,
    "growth": 0.25,
}


def _distribute_remainder(fund_w: float, val_w: float, tech_w: float) -> Optional[Dict[str, float]]:
    """Build a full weight dict from the 3 tunable weights.

    The tunable weights (fundamentals, valuation, technicals) take priority.
    Remaining budget is split among risk, growth, sentiment, sector_relative
    using fixed ratios. Returns None if weights are invalid.
    """
    remainder = 1.0 - fund_w - val_w - tech_w
    if remainder < 0.01:
        return None  # no room for other factors

    total_ratio = sum(FIXED_RATIOS.values())
    weights = {
        "fundamentals": round(fund_w, 3),
        "valuation": round(val_w, 3),
        "technicals": round(tech_w, 3),
    }
    for key, ratio in FIXED_RATIOS.items():
        weights[key] = round(remainder * ratio / total_ratio, 3)

    # Normalize to exactly 1.0
    total = sum(weights.values())
    if total > 0:
        for k in weights:
            weights[k] = round(weights[k] / total, 3)
    return weights


def _get_current_weights(strategy: str = "balanced") -> Dict[str, float]:
    """Get current weights from strategy config."""
    strat = STRATEGIES.get(strategy, STRATEGIES["balanced"])
    return dict(strat["weights"])


def _run_backtest_with_weights(weights: Dict[str, float], months_back: int = 6) -> Optional[dict]:
    """Run backtest using specific weights. Returns results dict or None on failure."""
    try:
        from .backtest import run_backtest
        from .scorer import compute_composite
        from .pipeline import load_config

        # Temporarily patch config weights
        config = load_config()
        old_weights = config.get("weights", {})
        config["weights"] = weights

        result = run_backtest(months_back=months_back, top_n=20)
        config["weights"] = old_weights  # restore

        if "error" in result:
            return None

        # Extract key metrics from the longest available period
        periods = result.get("periods", {})
        if not periods:
            return None

        # Prefer longest period
        for key in ["6m", "3m", "1m", "full"]:
            if key in periods:
                return {
                    "period": key,
                    "alpha": periods[key].get("alpha"),
                    "win_rate": periods[key].get("win_rate"),
                    "portfolio_return": periods[key].get("portfolio_return"),
                    "spy_return": periods[key].get("spy_return"),
                    "max_drawdown": periods[key].get("max_drawdown"),
                    "weights_used": weights,
                }
        return None
    except Exception as e:
        logger.error("Backtest with custom weights failed: %s", e)
        return None


def _simple_grid_search(strategy: str = "balanced", months_back: int = 6) -> Dict:
    """Basic grid search over key weights.

    Tests combinations of fundamentals, valuation, and technicals weights.
    Returns best weights and comparison results.
    """
    logger.info("Starting grid search optimization for strategy=%s", strategy)

    current_weights = _get_current_weights(strategy)

    # Run backtest with current weights first
    logger.info("Backtesting current weights: %s", current_weights)
    current_result = _run_backtest_with_weights(current_weights, months_back)

    if not current_result:
        return {
            "error": "Could not backtest current weights",
            "current_weights": current_weights,
        }

    # Generate weight combos
    combos = []
    for f_w, v_w, t_w in itertools.product(WEIGHT_GRID, WEIGHT_GRID, WEIGHT_GRID):
        if f_w + v_w + t_w > 0.85:  # leave room for other factors
            continue
        if f_w + v_w + t_w < 0.30:  # need meaningful allocation
            continue
        full_weights = _distribute_remainder(f_w, v_w, t_w)
        if full_weights:
            combos.append(full_weights)

    logger.info("Testing %d weight combinations", len(combos))

    best_result = current_result
    best_weights = current_weights
    tested = 0

    for weights in combos:
        tested += 1
        if tested % 5 == 0:
            logger.info("Grid search progress: %d/%d", tested, len(combos))

        result = _run_backtest_with_weights(weights, months_back)
        if not result:
            continue

        # Compare: prioritize alpha, then win_rate
        if result.get("alpha") is not None and best_result.get("alpha") is not None:
            if result["alpha"] > best_result["alpha"]:
                best_result = result
                best_weights = weights

    return {
        "current_weights": current_weights,
        "current_result": current_result,
        "best_weights": best_weights,
        "best_result": best_result,
        "combos_tested": tested,
    }


def run_monthly_optimization(strategy: str = "balanced", months_back: int = 6) -> dict:
    """Run monthly auto-optimization.

    1. Grid search over key weights
    2. Backtest current vs proposed
    3. Apply only if alpha improves >0.1% AND win rate >55%
    4. Log results
    5. Return summary

    Returns dict with results and decision.
    """
    timestamp = datetime.now().isoformat()
    logger.info("=== Monthly optimization started at %s ===", timestamp)

    # Try using optimizer.py first if available
    try:
        from .optimizer import run_optimization, apply_optimization
        opt_result = run_optimization()
        proposed_weights = opt_result.get("proposed_weights")
        if proposed_weights:
            logger.info("Using optimizer.py proposed weights")
    except (ImportError, Exception) as e:
        logger.info("optimizer.py not available (%s), falling back to grid search", e)
        proposed_weights = None

    current_weights = _get_current_weights(strategy)

    if proposed_weights:
        # Backtest both
        current_result = _run_backtest_with_weights(current_weights, months_back)
        proposed_result = _run_backtest_with_weights(proposed_weights, months_back)
        best_weights = proposed_weights
        best_result = proposed_result
        combos_tested = 1
    else:
        # Grid search fallback
        search = _simple_grid_search(strategy, months_back)
        if "error" in search:
            entry = {
                "date": timestamp,
                "decision": "error",
                "reason": search["error"],
                "old_weights": current_weights,
                "new_weights": None,
                "old_backtest": None,
                "new_backtest": None,
            }
            _save_log_entry(entry)
            return {"decision": "error", "reason": search["error"], "entry": entry}

        current_result = search["current_result"]
        best_weights = search["best_weights"]
        best_result = search["best_result"]
        combos_tested = search["combos_tested"]

    # Decision logic
    decision = "rejected"
    reason = ""

    if current_result is None or best_result is None:
        decision = "error"
        reason = "Could not complete backtests"
    elif best_weights == current_weights:
        decision = "no_change"
        reason = "Current weights are already optimal"
    else:
        old_alpha = current_result.get("alpha") or 0
        new_alpha = best_result.get("alpha") or 0
        new_win_rate = best_result.get("win_rate") or 0
        alpha_improvement = new_alpha - old_alpha

        if alpha_improvement > 0.001 and new_win_rate > 0.55:
            decision = "applied"
            reason = (
                f"Alpha improved by {alpha_improvement:.4f} "
                f"({old_alpha:.4f} -> {new_alpha:.4f}), "
                f"win rate {new_win_rate:.2%} > 55%"
            )
            # Apply: update strategy weights
            _apply_weights(strategy, best_weights)
        elif new_win_rate <= 0.55:
            reason = f"Win rate {new_win_rate:.2%} below 55% threshold"
        else:
            reason = (
                f"Alpha improvement {alpha_improvement:.4f} below 0.1% threshold "
                f"({old_alpha:.4f} -> {new_alpha:.4f})"
            )

    # Build log entry
    entry = {
        "date": timestamp,
        "strategy": strategy,
        "decision": decision,
        "reason": reason,
        "old_weights": current_weights,
        "new_weights": best_weights if decision == "applied" else None,
        "old_backtest": current_result,
        "new_backtest": best_result,
        "combos_tested": combos_tested,
    }
    _save_log_entry(entry)

    # Generate Discord summary
    summary = _generate_discord_summary(entry)

    logger.info("=== Optimization complete: %s — %s ===", decision, reason)

    return {
        "decision": decision,
        "reason": reason,
        "entry": entry,
        "discord_summary": summary,
    }


def _apply_weights(strategy: str, weights: Dict[str, float]):
    """Apply new weights to the strategy definition.

    Updates the in-memory STRATEGIES dict. For persistence, also saves
    to data/weight_overrides.json.
    """
    if strategy in STRATEGIES:
        STRATEGIES[strategy]["weights"] = weights
        logger.info("Applied new weights to %s strategy: %s", strategy, weights)

    # Persist override
    override_file = DATA_DIR / "weight_overrides.json"
    overrides = {}
    if override_file.exists():
        try:
            overrides = json.loads(override_file.read_text())
        except Exception:
            pass
    overrides[strategy] = {
        "weights": weights,
        "applied_at": datetime.now().isoformat(),
    }
    DATA_DIR.mkdir(exist_ok=True)
    override_file.write_text(json.dumps(overrides, indent=2))


def _save_log_entry(entry: dict):
    """Append entry to optimization log."""
    DATA_DIR.mkdir(exist_ok=True)
    history = get_optimization_history()
    history.append(entry)
    history = history[-100:]  # keep last 100
    OPTIMIZATION_LOG.write_text(json.dumps(history, indent=2, default=str))


def get_optimization_history() -> List[dict]:
    """Load past optimization entries."""
    if OPTIMIZATION_LOG.exists():
        try:
            return json.loads(OPTIMIZATION_LOG.read_text())
        except Exception:
            return []
    return []


def _generate_discord_summary(entry: dict) -> str:
    """Generate a Discord-friendly summary message."""
    decision = entry.get("decision", "unknown")
    reason = entry.get("reason", "")
    strategy = entry.get("strategy", "balanced")
    date = entry.get("date", "")[:10]

    emoji = {"applied": "✅", "rejected": "❌", "no_change": "🔄", "error": "⚠️"}.get(decision, "❓")

    lines = [
        f"**{emoji} Monthly Weight Optimization — {date}**",
        f"Strategy: **{strategy}**",
        f"Decision: **{decision.upper()}**",
        f"Reason: {reason}",
    ]

    old_bt = entry.get("old_backtest") or {}
    new_bt = entry.get("new_backtest") or {}

    if old_bt:
        lines.append(
            f"Current: alpha={old_bt.get('alpha', 'N/A')}, "
            f"win_rate={old_bt.get('win_rate', 'N/A')}"
        )
    if new_bt and decision == "applied":
        lines.append(
            f"New: alpha={new_bt.get('alpha', 'N/A')}, "
            f"win_rate={new_bt.get('win_rate', 'N/A')}"
        )

    if decision == "applied":
        old_w = entry.get("old_weights", {})
        new_w = entry.get("new_weights", {})
        changes = []
        for k in sorted(set(list(old_w.keys()) + list(new_w.keys()))):
            ov = old_w.get(k, 0)
            nv = new_w.get(k, 0)
            if abs(ov - nv) > 0.005:
                changes.append(f"  {k}: {ov:.1%} → {nv:.1%}")
        if changes:
            lines.append("Weight changes:")
            lines.extend(changes)

    combos = entry.get("combos_tested")
    if combos:
        lines.append(f"Combos tested: {combos}")

    return "\n".join(lines)
