"""Analyst consensus sentiment scoring.

Uses yfinance info fields (already fetched, zero additional API calls):
- recommendationMean: 1.0 (Strong Buy) to 5.0 (Strong Sell)
- targetMeanPrice: analyst price target
- numberOfAnalystOpinions: coverage count
"""

import logging
from typing import Dict, Any, Optional

logger = logging.getLogger(__name__)


def score_analyst_sentiment(info: dict) -> Dict[str, Any]:
    """Score sentiment from analyst consensus data already in yfinance info.
    
    Returns dict with score (0-100), plus breakdown fields.
    """
    rec_mean = info.get("recommendationMean")  # 1.0=strongBuy, 5.0=strongSell
    target_price = info.get("targetMeanPrice")
    current_price = info.get("currentPrice") or info.get("regularMarketPrice")
    analyst_count = info.get("numberOfAnalystOpinions", 0) or 0
    rec_key = info.get("recommendationKey", "none")
    
    # Coverage filter: too few analysts = neutral
    if analyst_count < 3:
        return {
            "score": 50,
            "consensus_score": None,
            "pt_upside_score": None,
            "recommendation": rec_key,
            "pt_upside_pct": None,
            "analyst_count": analyst_count,
            "details": f"Low coverage ({analyst_count} analysts), defaulting to neutral",
        }
    
    components = []
    consensus_score = None
    pt_upside_score = None
    pt_upside_pct = None
    
    # 1. Consensus score (50% weight): map 1-5 scale to 0-100
    if rec_mean is not None:
        consensus_score = max(0, min(100, (5.0 - rec_mean) / 4.0 * 100))
        components.append(consensus_score)
    
    # 2. Price target upside (50% weight): map upside % to 0-100
    if target_price and current_price and current_price > 0:
        pt_upside_pct = (target_price - current_price) / current_price
        # +30% upside = 100, 0% = 50, -30% = 0
        pt_upside_score = max(0, min(100, 50 + (pt_upside_pct / 0.30) * 50))
        components.append(pt_upside_score)
    
    if components:
        final_score = sum(components) / len(components)
    else:
        final_score = 50  # No data = neutral
    
    return {
        "score": round(final_score, 2),
        "consensus_score": round(consensus_score, 2) if consensus_score is not None else None,
        "pt_upside_score": round(pt_upside_score, 2) if pt_upside_score is not None else None,
        "recommendation": rec_key,
        "pt_upside_pct": round(pt_upside_pct, 4) if pt_upside_pct is not None else None,
        "analyst_count": analyst_count,
        "details": f"{rec_key} ({analyst_count} analysts)" + (f", PT upside {pt_upside_pct:.1%}" if pt_upside_pct else ""),
    }
