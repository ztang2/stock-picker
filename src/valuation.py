"""Valuation analysis: P/E, P/S, PEG ratio."""

import logging
import numpy as np

logger = logging.getLogger(__name__)


def score_valuation(info: dict) -> dict:
    """Compute valuation metrics and raw score (0-100).

    Lower valuation multiples → higher score (value investing bias).
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

    valid = [c for c in components if c is not None]
    if valid:
        metrics["score"] = sum(valid) / len(valid) * 3
    else:
        metrics["score"] = None

    return metrics
