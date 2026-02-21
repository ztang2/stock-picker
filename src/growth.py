"""Growth scoring module: revenue growth, earnings growth, margin trends."""

import logging
from typing import Optional

import numpy as np

logger = logging.getLogger(__name__)


def score_growth(info: dict) -> dict:
    """Compute growth metrics and a raw score (0-100).

    Uses yfinance info fields: revenueGrowth, earningsQuarterlyGrowth,
    grossMargins, operatingMargins, marketCap, totalRevenue.
    """
    metrics = {}  # type: dict

    # 1. Revenue growth (YoY)
    rev_growth = info.get("revenueGrowth")
    metrics["revenue_growth"] = rev_growth

    # 2. Earnings growth (quarterly YoY)
    earnings_growth = info.get("earningsQuarterlyGrowth")
    metrics["earnings_growth"] = earnings_growth

    # 3. Revenue acceleration proxy
    # Use revenueGrowth vs earningsGrowth as a rough proxy
    # If earnings growing faster than revenue, margins expanding
    rev_accel = None
    if rev_growth is not None and earnings_growth is not None:
        rev_accel = earnings_growth - rev_growth
    metrics["revenue_acceleration"] = rev_accel

    # 4. Gross margin (higher = better scaling)
    gross_margins = info.get("grossMargins")
    metrics["gross_margins"] = gross_margins

    # 5. Operating margin trend (proxy: operating vs gross margin gap)
    operating_margins = info.get("operatingMargins")
    metrics["operating_margins"] = operating_margins
    margin_efficiency = None
    if gross_margins is not None and operating_margins is not None and gross_margins > 0:
        margin_efficiency = operating_margins / gross_margins
    metrics["margin_efficiency"] = margin_efficiency

    # 6. Market cap vs revenue growth (small cap + high growth = more upside)
    market_cap = info.get("marketCap")
    metrics["market_cap"] = market_cap
    cap_growth_score = None
    if market_cap is not None and rev_growth is not None and rev_growth > 0:
        # Small cap bonus: <10B gets boost, >200B gets penalty
        if market_cap < 10e9:
            cap_multiplier = 1.3
        elif market_cap < 50e9:
            cap_multiplier = 1.1
        elif market_cap > 200e9:
            cap_multiplier = 0.85
        else:
            cap_multiplier = 1.0
        cap_growth_score = rev_growth * cap_multiplier
    metrics["cap_growth_factor"] = cap_growth_score

    # Compute composite score (0-100)
    components = []

    # Revenue growth: 0% → 10, 10% → 40, 20% → 60, 50%+ → 90
    if rev_growth is not None:
        rg_score = float(np.clip(rev_growth * 200 + 10, 0, 30))
        components.append(("revenue_growth", rg_score, 30))

    # Earnings growth: similar scaling
    if earnings_growth is not None:
        eg_score = float(np.clip(earnings_growth * 150 + 10, 0, 25))
        components.append(("earnings_growth", eg_score, 25))

    # Revenue acceleration: positive = good
    if rev_accel is not None:
        ra_score = float(np.clip(rev_accel * 100 + 10, 0, 15))
        components.append(("revenue_accel", ra_score, 15))

    # Gross margins: >60% excellent, >40% good, <20% poor
    if gross_margins is not None:
        gm_score = float(np.clip(gross_margins * 25, 0, 15))
        components.append(("gross_margins", gm_score, 15))

    # Cap-growth factor
    if cap_growth_score is not None:
        cg_score = float(np.clip(cap_growth_score * 100 + 5, 0, 15))
        components.append(("cap_growth", cg_score, 15))

    # Fix scoring inflation: component weights already sum to 100 max
    # Missing components contribute 0, not rescaled
    # Total possible: revenue(30) + earnings(25) + accel(15) + margins(15) + cap(15) = 100
    if components:
        raw = sum(c[1] for c in components)
        metrics["score"] = float(np.clip(raw, 0, 100))
    else:
        metrics["score"] = 0.0  # No data = 0 score

    return metrics
