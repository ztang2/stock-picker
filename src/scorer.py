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
    sector_scores: Optional[dict] = None,
    regime: Optional[str] = None,
    **kwargs,
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
        # Sentiment score is already 0-100 from analyst consensus scoring
        sent_raw = (r.get("sentiment") or {}).get("score")
        
        # Convert sector_rank to 0-100 score (rank 1 = 100, last = 0)
        sector_rel_raw = None
        if sector_scores:
            sector_data = sector_scores.get(r["ticker"], {})
            sector_rank = sector_data.get("sector_rank")
            sector_size = sector_data.get("sector_size")
            if sector_rank is not None and sector_size is not None and sector_size > 1:
                # Invert rank: rank 1 (best) = 100, rank N (worst) = 0
                sector_rel_raw = ((sector_size - sector_rank) / (sector_size - 1)) * 100
        
        row = {
            "ticker": r["ticker"],
            "fund_raw": (r.get("fundamentals") or {}).get("score"),
            "val_raw": (r.get("valuation") or {}).get("score"),
            "tech_raw": (r.get("technicals") or {}).get("score"),
            "risk_raw": (r.get("risk") or {}).get("score"),
            "growth_raw": (r.get("growth") or {}).get("score"),
            "sent_raw": sent_raw,
            "sector_rel_raw": sector_rel_raw,
        }
        rows.append(row)

    df = pd.DataFrame(rows)

    # Percentile rank each category
    df["fund_pct"] = percentile_rank(df["fund_raw"])
    df["val_pct"] = percentile_rank(df["val_raw"])
    df["tech_pct"] = percentile_rank(df["tech_raw"])
    df["risk_pct"] = percentile_rank(df["risk_raw"])
    df["growth_pct"] = percentile_rank(df["growth_raw"])
    df["sent_pct"] = percentile_rank(df["sent_raw"])
    df["sector_rel_pct"] = percentile_rank(df["sector_rel_raw"])

    # Use strategy weights
    w_fund = strat_weights.get("fundamentals", 0.30)
    w_val = strat_weights.get("valuation", 0.20)
    w_tech = strat_weights.get("technicals", 0.25)
    w_risk = strat_weights.get("risk", 0.10)
    w_growth = strat_weights.get("growth", 0.15)
    w_sent = strat_weights.get("sentiment", 0.05)
    w_sector_rel = strat_weights.get("sector_relative", 0.10)
    
    # Apply regime-based weight adjustments
    if regime:
        from .market_regime import get_regime_weight_adjustments
        regime_adjustments = get_regime_weight_adjustments(regime)
        w_fund *= regime_adjustments.get("fundamentals", 1.0)
        w_val *= regime_adjustments.get("valuation", 1.0)
        w_tech *= regime_adjustments.get("technicals", 1.0)
        w_risk *= regime_adjustments.get("risk", 1.0)
        w_growth *= regime_adjustments.get("growth", 1.0)
        w_sent *= regime_adjustments.get("sentiment", 1.0)
        w_sector_rel *= regime_adjustments.get("sector_relative", 1.0)
        
        # Renormalize weights to sum to 1.0
        total_weight = w_fund + w_val + w_tech + w_risk + w_growth + w_sent + w_sector_rel
        if total_weight > 0:
            w_fund /= total_weight
            w_val /= total_weight
            w_tech /= total_weight
            w_risk /= total_weight
            w_growth /= total_weight
            w_sent /= total_weight
            w_sector_rel /= total_weight

    # For each row, redistribute weights proportionally across available categories
    categories = [
        ("fund_pct", w_fund),
        ("val_pct", w_val),
        ("tech_pct", w_tech),
        ("risk_pct", w_risk),
        ("growth_pct", w_growth),
        ("sent_pct", w_sent),
        ("sector_rel_pct", w_sector_rel),
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

    # Geopolitical event adjustments (industry-level bonus/penalty)
    geo_adjustments = kwargs.get("geo_adjustments", {})
    if geo_adjustments:
        def _geo_bonus(ticker: str) -> float:
            r = detail_map.get(ticker, {})
            industry = (r.get("info_cache") or {}).get("industry") or r.get("industry", "")
            return geo_adjustments.get(industry, 0)
        df["geo_bonus"] = df["ticker"].map(_geo_bonus)
        df["composite"] = df["composite"] + df["geo_bonus"]
        adjusted = df[df["geo_bonus"] != 0]
        if len(adjusted) > 0:
            logger.info(f"Geopolitical adjustments applied to {len(adjusted)} stocks "
                       f"(range: {adjusted['geo_bonus'].min():+.0f} to {adjusted['geo_bonus'].max():+.0f})")

    df["composite"] = df["composite"].clip(lower=0)

    df = df.sort_values("composite", ascending=False).reset_index(drop=True)
    df["rank"] = df.index + 1

    return df
