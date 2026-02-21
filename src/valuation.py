"""Valuation analysis: P/E, P/S, PEG ratio."""

import logging
from typing import Optional

import numpy as np

logger = logging.getLogger(__name__)


def score_valuation(info: dict, growth_score: Optional[float] = None) -> dict:
    """Compute valuation metrics and raw score (0-100).

    Lower valuation multiples → higher score (value investing bias).
    
    Args:
        info: Stock info dict from yfinance
        growth_score: Optional growth score (0-100). If > 80, dampens valuation penalty for high-growth stocks.
    """
    metrics: dict = {}

    pe = info.get("forwardPE") or info.get("trailingPE")
    ps = info.get("priceToSalesTrailing12Months")
    peg = info.get("pegRatio")

    metrics["pe_ratio"] = pe
    metrics["ps_ratio"] = ps
    metrics["peg_ratio"] = peg

    components = []

    # P/E: <10 → 33, 15 → 25, 25 → 10, >50 → 0
    if pe is not None and pe > 0:
        components.append(np.clip(33 - (pe - 10) * 0.825, 0, 33.3))
    else:
        components.append(None)

    # P/S: <1 → 33, 5 → 16, >10 → 0
    if ps is not None and ps > 0:
        components.append(np.clip(33.3 - ps * 3.33, 0, 33.3))
    else:
        components.append(None)

    # PEG: <1 → 33, 1 → 25, 2 → 16, >3 → 0
    if peg is not None and peg > 0:
        components.append(np.clip(33.3 - (peg - 0.5) * 13.3, 0, 33.3))
    else:
        components.append(None)

    # Fix scoring inflation: use TOTAL component count (3), not just available count
    # Missing metrics contribute 0, not skipped
    TOTAL_COMPONENTS = 3
    score_sum = sum(c for c in components if c is not None)
    metrics["score"] = (score_sum / TOTAL_COMPONENTS) * 3
    
    # Growth-adjusted valuation: gradual scaling instead of binary threshold
    # Scales from 1.0 at score 50 to 1.25 at score 100
    if growth_score is not None and growth_score > 50:
        multiplier = 1.0 + max(0, (growth_score - 50)) / 100 * 0.5
        metrics["score"] = min(metrics["score"] * multiplier, 100.0)
        metrics["growth_adjusted"] = True
    
    # PEG ratio boost: if PEG < 1.5, it's growth at a reasonable price
    if peg is not None and peg > 0 and peg < 1.5 and metrics["score"] is not None:
        metrics["score"] = min(metrics["score"] + 15, 100.0)
        metrics["peg_boosted"] = True

    return metrics
