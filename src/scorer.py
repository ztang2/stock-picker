"""Weighted composite scoring with percentile ranking."""

import logging
from typing import List, Optional

import numpy as np
import pandas as pd

from .strategies import get_strategy

logger = logging.getLogger(__name__)


def percentile_rank(series: pd.Series) -> pd.Series:
    """Convert raw scores to percentile ranks (0-100)."""
    return series.rank(pct=True, na_option="keep") * 100


def compute_composite(
    results: List[dict],
    weights: dict,
    strategy: str = "balanced",
) -> pd.DataFrame:
    """Take list of per-stock result dicts and produce ranked DataFrame.

    Each dict: {ticker, fundamentals: {score}, valuation: {score}, technicals: {score},
                risk: {score}, growth: {score}}
    """
    strat = get_strategy(strategy)
    strat_weights = strat["weights"]
    momentum_cfg = strat["momentum_bonus"]

    rows = []
    for r in results:
        row = {
            "ticker": r["ticker"],
            "fund_raw": (r.get("fundamentals") or {}).get("score"),
            "val_raw": (r.get("valuation") or {}).get("score"),
            "tech_raw": (r.get("technicals") or {}).get("score"),
            "risk_raw": (r.get("risk") or {}).get("score"),
            "growth_raw": (r.get("growth") or {}).get("score"),
        }
        rows.append(row)

    df = pd.DataFrame(rows)

    # Percentile rank each category
    df["fund_pct"] = percentile_rank(df["fund_raw"])
    df["val_pct"] = percentile_rank(df["val_raw"])
    df["tech_pct"] = percentile_rank(df["tech_raw"])
    df["risk_pct"] = percentile_rank(df["risk_raw"])
    df["growth_pct"] = percentile_rank(df["growth_raw"])

    # Use strategy weights
    w_fund = strat_weights.get("fundamentals", 0.30)
    w_val = strat_weights.get("valuation", 0.20)
    w_tech = strat_weights.get("technicals", 0.25)
    w_risk = strat_weights.get("risk", 0.10)
    w_growth = strat_weights.get("growth", 0.15)

    # For each row, redistribute weights proportionally across available categories
    categories = [
        ("fund_pct", w_fund),
        ("val_pct", w_val),
        ("tech_pct", w_tech),
        ("risk_pct", w_risk),
        ("growth_pct", w_growth),
    ]

    def _weighted_composite(row):
        available = [(row[col], w) for col, w in categories if pd.notna(row[col]) and w > 0]
        if not available:
            return 0.0
        total_w = sum(w for _, w in available)
        if total_w == 0:
            return 0.0
        return sum(val * (w / total_w) for val, w in available)

    df["composite"] = df.apply(_weighted_composite, axis=1)

    # Momentum bonus modifier (scaled per strategy)
    def _momentum_bonus(r: dict) -> float:
        if not momentum_cfg.get("enabled", True):
            return 0
        entry_score = (r.get("momentum") or {}).get("entry_score")
        if entry_score is None:
            return 0
        if entry_score > 80:
            return momentum_cfg.get("strong", 5)
        if entry_score > 60:
            return momentum_cfg.get("moderate", 2)
        if entry_score < 20:
            return momentum_cfg.get("weak", -3)
        return 0

    detail_map = {r["ticker"]: r for r in results}
    df["momentum_bonus"] = df["ticker"].map(lambda t: _momentum_bonus(detail_map.get(t, {})))
    df["composite"] = df["composite"] + df["momentum_bonus"]
    df["composite"] = df["composite"].clip(lower=0)

    df = df.sort_values("composite", ascending=False).reset_index(drop=True)
    df["rank"] = df.index + 1

    return df
