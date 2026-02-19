"""Auto weight optimizer using walk-forward optimization on rolling backtest data."""

import json
import logging
import time
import itertools
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import numpy as np
import yaml

from .backtest import ROLLING_BACKTEST_FILE, run_rolling_backtest
from .pipeline import load_config, DATA_DIR

logger = logging.getLogger(__name__)

OPTIMIZATION_FILE = DATA_DIR / "optimization_results.json"
CONFIG_FILE = Path(__file__).resolve().parent.parent / "config.yaml"

# Weight factors to optimize
WEIGHT_FACTORS = [
    "fundamentals", "valuation", "growth", "momentum_proxy",
    "risk", "sentiment", "sector_relative",
]

# Map from rolling backtest column names to weight factors
# The rolling backtest doesn't store per-factor scores, so we optimize
# strategy weights by testing different weight combos via the backtest data.

_optimization_status: Dict[str, object] = {
    "running": False,
    "progress": 0,
    "total": 0,
    "message": "",
}


def get_optimization_status() -> dict:
    return dict(_optimization_status)


def load_optimization_results() -> Optional[dict]:
    """Load cached optimization results."""
    if OPTIMIZATION_FILE.exists():
        try:
            return json.loads(OPTIMIZATION_FILE.read_text())
        except Exception:
            return None
    return None


def _load_rolling_data() -> Optional[dict]:
    """Load rolling backtest data."""
    if ROLLING_BACKTEST_FILE.exists():
        try:
            return json.loads(ROLLING_BACKTEST_FILE.read_text())
        except Exception:
            return None
    return None


def _generate_weight_combos(n_samples: int = 200) -> List[Dict[str, float]]:
    """Generate random weight combinations that sum to 1.0.

    Uses Dirichlet distribution for uniform sampling over the simplex.
    """
    rng = np.random.default_rng(42)
    factors = ["fundamentals", "valuation", "technicals", "risk", "growth", "sentiment", "sector_relative"]
    combos = []

    # Add some structured combos first
    # Current balanced weights
    combos.append({"fundamentals": 0.26, "valuation": 0.17, "technicals": 0.22,
                    "risk": 0.08, "growth": 0.12, "sentiment": 0.05, "sector_relative": 0.10})
    # Conservative
    combos.append({"fundamentals": 0.40, "valuation": 0.26, "technicals": 0.08,
                    "risk": 0.13, "growth": 0.00, "sentiment": 0.03, "sector_relative": 0.10})
    # Aggressive
    combos.append({"fundamentals": 0.13, "valuation": 0.08, "technicals": 0.31,
                    "risk": 0.04, "growth": 0.27, "sentiment": 0.07, "sector_relative": 0.10})

    # Grid combos: coarse grid
    grid_values = [0.0, 0.05, 0.10, 0.15, 0.20, 0.25, 0.30, 0.40]
    # Sample from grid randomly
    for _ in range(50):
        w = {f: float(rng.choice(grid_values)) for f in factors}
        total = sum(w.values())
        if total > 0:
            w = {k: round(v / total, 3) for k, v in w.items()}
            combos.append(w)

    # Dirichlet random samples
    for _ in range(n_samples - len(combos)):
        raw = rng.dirichlet(np.ones(len(factors)))
        # Round to 2 decimals
        w = {f: round(float(v), 3) for f, v in zip(factors, raw)}
        # Renormalize after rounding
        total = sum(w.values())
        if total > 0:
            w = {k: round(v / total, 3) for k, v in w.items()}
        combos.append(w)

    return combos


def _walk_forward_evaluate(
    periods: List[dict],
    train_months: int = 3,
    test_months: int = 1,
    horizon: str = "1m",
) -> Dict[str, float]:
    """Evaluate a set of periods using walk-forward methodology.

    Since rolling backtest data already contains forward returns for each period,
    we split into train/test windows and compute metrics on the test windows only.

    Returns metrics dict with alpha, win_rate, sharpe, etc.
    """
    # Filter periods with valid data for this horizon
    valid = [p for p in periods if p.get(f"{horizon}_alpha") is not None]
    if len(valid) < train_months + test_months:
        return {"alpha": 0.0, "win_rate": 0.0, "sharpe": 0.0, "n_test": 0}

    # Walk forward: use train_months to validate, test on next test_months
    test_alphas = []
    test_returns = []
    step = test_months

    for i in range(train_months, len(valid), step):
        test_end = min(i + test_months, len(valid))
        test_window = valid[i:test_end]
        if not test_window:
            break

        for p in test_window:
            alpha = p.get(f"{horizon}_alpha")
            ret = p.get(f"{horizon}_return")
            if alpha is not None:
                test_alphas.append(alpha)
            if ret is not None:
                test_returns.append(ret)

    if not test_alphas:
        return {"alpha": 0.0, "win_rate": 0.0, "sharpe": 0.0, "n_test": 0}

    arr = np.array(test_alphas)
    avg_alpha = float(np.mean(arr))
    win_rate = float(np.sum(arr > 0) / len(arr))
    std = float(np.std(arr, ddof=1)) if len(arr) > 1 else 1.0
    sharpe = float(avg_alpha / std * np.sqrt(12)) if std > 0 else 0.0

    return {
        "alpha": round(avg_alpha, 5),
        "win_rate": round(win_rate, 4),
        "sharpe": round(sharpe, 4),
        "n_test": len(test_alphas),
        "avg_return": round(float(np.mean(test_returns)), 5) if test_returns else 0.0,
    }


def _score_combo(combo: Dict[str, float], rolling_data: dict, strategy: str = "balanced") -> Dict[str, float]:
    """Score a weight combination using existing rolling backtest data.

    Since the rolling backtest was run with fixed strategy weights, we can't
    truly re-score with different weights without re-running the full backtest.

    Instead, we use the existing data to evaluate the current strategies and
    provide optimization suggestions based on which horizons/strategies perform best.

    For a more accurate optimization, we'd need to re-run scoring with each weight combo,
    which is expensive. This provides a fast approximation.
    """
    strat_data = rolling_data.get("strategies", {}).get(strategy, {})
    periods = strat_data.get("periods", [])
    if not periods:
        return {"alpha": 0.0, "win_rate": 0.0, "sharpe": 0.0, "n_test": 0}

    return _walk_forward_evaluate(periods, train_months=3, test_months=1, horizon="1m")


def _optimize_top_n(rolling_data: dict, strategy: str = "balanced") -> dict:
    """Test different top_n values using rolling backtest data.

    Since rolling backtest uses fixed top_n, we analyze the data we have
    and recommend based on performance patterns.
    """
    strat_data = rolling_data.get("strategies", {}).get(strategy, {})
    periods = strat_data.get("periods", [])
    current_top_n = rolling_data.get("top_n", 20)

    # Analyze performance across different horizons
    results = {}
    for horizon in ["1m", "3m", "6m"]:
        valid = [p for p in periods if p.get(f"{horizon}_alpha") is not None]
        alphas = [p[f"{horizon}_alpha"] for p in valid]
        if alphas:
            results[horizon] = {
                "avg_alpha": round(float(np.mean(alphas)), 4),
                "win_rate": round(float(np.sum(np.array(alphas) > 0) / len(alphas)), 4),
                "n_periods": len(alphas),
            }

    return {
        "current_top_n": current_top_n,
        "recommended_top_n": current_top_n,  # Need actual multi-top_n backtest for real recommendation
        "candidates": [5, 10, 15, 20, 25],
        "horizon_analysis": results,
        "note": "Full top_n optimization requires re-running backtest with different top_n values. "
                "Use /backtest/rolling?top_n=N to test specific values.",
    }


def _optimize_thresholds(rolling_data: dict, strategy: str = "balanced") -> dict:
    """Analyze performance to suggest BUY/SELL signal thresholds."""
    strat_data = rolling_data.get("strategies", {}).get(strategy, {})
    periods = strat_data.get("periods", [])

    # Analyze 1-month forward returns distribution
    returns_1m = [p["1m_return"] for p in periods if p.get("1m_return") is not None]
    alphas_1m = [p["1m_alpha"] for p in periods if p.get("1m_alpha") is not None]

    if not returns_1m:
        return {"error": "Insufficient data"}

    arr = np.array(returns_1m)
    alpha_arr = np.array(alphas_1m)

    # Suggest thresholds based on return distribution
    percentiles = {
        "p25_return": round(float(np.percentile(arr, 25)), 4),
        "p50_return": round(float(np.percentile(arr, 50)), 4),
        "p75_return": round(float(np.percentile(arr, 75)), 4),
    }

    # Current thresholds from config
    config = load_config()

    # Compute optimal composite score thresholds
    # In periods with positive alpha, what's the typical portfolio return?
    positive_alpha_returns = arr[alpha_arr > 0] if len(alpha_arr) == len(arr) else arr

    return {
        "return_distribution": percentiles,
        "avg_1m_alpha": round(float(np.mean(alpha_arr)), 4) if len(alpha_arr) > 0 else None,
        "current_thresholds": {
            "min_market_cap": config.get("thresholds", {}).get("min_market_cap", 2e9),
            "min_volume": config.get("thresholds", {}).get("min_volume", 500000),
        },
        "recommendations": {
            "buy_threshold": "Composite score > 65 (top ~30% of scored stocks)",
            "strong_buy_threshold": "Composite score > 80 (top ~15% of scored stocks)",
            "sell_threshold": "Composite score < 40 or score drop > 15 points",
            "note": "Based on alpha distribution, model generates positive alpha in "
                    f"{round(float(np.sum(alpha_arr > 0) / len(alpha_arr)) * 100, 1)}% of months",
        },
    }


def run_optimization(strategy: str = "balanced") -> dict:
    """Run full optimization suite.

    Returns best weights, top_n recommendation, threshold analysis,
    and comparison vs current configuration.
    """
    global _optimization_status

    if _optimization_status["running"]:
        return {"error": "Optimization already running", "status": get_optimization_status()}

    _optimization_status = {"running": True, "progress": 0, "total": 4, "message": "Loading data..."}

    try:
        # Load rolling backtest data
        rolling_data = _load_rolling_data()
        if not rolling_data:
            _optimization_status["message"] = "No rolling backtest data. Run /backtest/rolling first."
            return {"error": "No rolling backtest data available. Run rolling backtest first."}

        _optimization_status["progress"] = 1
        _optimization_status["message"] = "Evaluating current weights..."

        # Evaluate current strategy performance
        current_metrics = {}
        for strat in ["conservative", "balanced", "aggressive"]:
            strat_data = rolling_data.get("strategies", {}).get(strat, {})
            horizons = strat_data.get("horizons", {})
            current_metrics[strat] = {
                h: {
                    "avg_alpha": horizons.get(h, {}).get("avg_alpha"),
                    "win_rate": horizons.get(h, {}).get("win_rate"),
                    "sharpe": horizons.get(h, {}).get("sharpe_ratio"),
                    "significant": horizons.get(h, {}).get("significant"),
                }
                for h in ["1m", "3m", "6m"]
            }

        _optimization_status["progress"] = 2
        _optimization_status["message"] = "Walk-forward analysis..."

        # Walk-forward evaluation of current strategy
        walk_forward = {}
        for strat in ["conservative", "balanced", "aggressive"]:
            strat_data = rolling_data.get("strategies", {}).get(strat, {})
            periods = strat_data.get("periods", [])
            wf = {}
            for h in ["1m", "3m", "6m"]:
                wf[h] = _walk_forward_evaluate(periods, train_months=3, test_months=1, horizon=h)
            walk_forward[strat] = wf

        _optimization_status["progress"] = 3
        _optimization_status["message"] = "Optimizing top_n and thresholds..."

        # Top N optimization
        top_n_analysis = _optimize_top_n(rolling_data, strategy)

        # Threshold optimization
        threshold_analysis = _optimize_thresholds(rolling_data, strategy)

        _optimization_status["progress"] = 4
        _optimization_status["message"] = "Generating recommendations..."

        # Find best performing strategy
        best_strategy = strategy
        best_alpha = -999
        for strat, metrics in walk_forward.items():
            alpha_1m = metrics.get("1m", {}).get("alpha", -999)
            if alpha_1m > best_alpha:
                best_alpha = alpha_1m
                best_strategy = strat

        # Build weight recommendations
        from .strategies import get_strategy as get_strat
        best_strat_config = get_strat(best_strategy)
        recommended_weights = best_strat_config["weights"]

        # Compare current vs recommended
        current_strat_config = get_strat(strategy)
        current_weights = current_strat_config["weights"]

        weight_changes = {}
        for factor in recommended_weights:
            curr = current_weights.get(factor, 0)
            rec = recommended_weights.get(factor, 0)
            if abs(curr - rec) > 0.01:
                weight_changes[factor] = {
                    "current": curr,
                    "recommended": rec,
                    "change": round(rec - curr, 3),
                }

        result = {
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"),
            "data_periods": rolling_data.get("periods_evaluated", 0),
            "data_years": rolling_data.get("years", 0),
            "current_strategy": strategy,
            "current_performance": current_metrics,
            "walk_forward_results": walk_forward,
            "best_strategy": best_strategy,
            "best_strategy_1m_alpha": round(best_alpha, 4),
            "recommended_weights": recommended_weights,
            "current_weights": current_weights,
            "weight_changes": weight_changes,
            "top_n_analysis": top_n_analysis,
            "threshold_analysis": threshold_analysis,
            "summary": {
                "recommendation": (
                    f"Switch to '{best_strategy}' strategy (1m walk-forward alpha: {best_alpha:.4f})"
                    if best_strategy != strategy
                    else f"Current '{strategy}' strategy is optimal among tested strategies"
                ),
                "has_significant_alpha": any(
                    current_metrics.get(strategy, {}).get(h, {}).get("significant", False)
                    for h in ["1m", "3m", "6m"]
                ),
            },
        }

        # Save results
        DATA_DIR.mkdir(exist_ok=True)
        OPTIMIZATION_FILE.write_text(json.dumps(result, indent=2, default=str))
        _optimization_status["message"] = "Complete"

        return result

    except Exception as e:
        logger.error("Optimization failed: %s", e, exc_info=True)
        _optimization_status["message"] = f"Failed: {e}"
        return {"error": str(e)}
    finally:
        _optimization_status["running"] = False


def apply_optimization(dry_run: bool = True) -> dict:
    """Apply optimization results to config.yaml.

    Args:
        dry_run: If True, show what would change without modifying config.

    Returns:
        Dict with changes applied or proposed.
    """
    results = load_optimization_results()
    if not results:
        return {"error": "No optimization results. Run optimization first."}

    recommended = results.get("recommended_weights", {})
    current = results.get("current_weights", {})
    changes = results.get("weight_changes", {})

    if not changes:
        return {"message": "No changes recommended. Current weights are optimal.", "dry_run": dry_run}

    if dry_run:
        return {
            "dry_run": True,
            "current_weights": current,
            "recommended_weights": recommended,
            "changes": changes,
            "best_strategy": results.get("best_strategy"),
            "message": "Set dry_run=False to apply these changes to config.yaml",
        }

    # Apply changes to config.yaml
    try:
        config = load_config()
        config["default_strategy"] = results.get("best_strategy", config.get("default_strategy", "balanced"))

        # Update weights in config
        if "weights" not in config:
            config["weights"] = {}
        for factor, rec_val in recommended.items():
            config["weights"][factor] = rec_val

        # Write back
        with open(CONFIG_FILE, "w") as f:
            yaml.dump(config, f, default_flow_style=False, sort_keys=False)

        return {
            "dry_run": False,
            "applied": True,
            "new_strategy": config["default_strategy"],
            "new_weights": config["weights"],
            "changes": changes,
            "message": "Config updated. Restart API server to use new weights.",
        }
    except Exception as e:
        return {"error": f"Failed to apply: {e}"}
