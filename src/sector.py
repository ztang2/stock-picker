"""Sector-relative scoring: rank metrics within sector peers."""

import logging
from typing import Optional, Dict, List

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)


def group_by_sector(results: List[dict]) -> Dict[str, List[dict]]:
    """Group analysis results by sector."""
    sectors: Dict[str, List[dict]] = {}
    for r in results:
        sector = r.get("sector", "Unknown")
        sectors.setdefault(sector, []).append(r)
    return sectors


def _percentile_in_group(value: Optional[float], values: List[Optional[float]]) -> Optional[float]:
    """Return percentile rank of value within a list (0-100)."""
    if value is None:
        return None
    valid = [v for v in values if v is not None]
    if len(valid) < 2:
        return 50.0
    rank = sum(1 for v in valid if v < value)
    return rank / len(valid) * 100


def compute_sector_relative_scores(results: List[dict]) -> Dict[str, dict]:
    """Compute sector-relative percentile ranks for key metrics.

    Returns {ticker: {sector_pe_pct, sector_ps_pct, sector_growth_pct, sector_composite, sector, sector_rank}}.
    """
    sectors = group_by_sector(results)
    output: Dict[str, dict] = {}

    for sector, stocks in sectors.items():
        # Collect metrics per sector
        pe_vals = [s.get("valuation", {}).get("pe_ratio") for s in stocks]
        ps_vals = [s.get("valuation", {}).get("ps_ratio") for s in stocks]
        growth_vals = [s.get("fundamentals", {}).get("revenue_growth") for s in stocks]
        roe_vals = [s.get("fundamentals", {}).get("roe") for s in stocks]

        sector_scores = []
        for s in stocks:
            pe = s.get("valuation", {}).get("pe_ratio")
            ps = s.get("valuation", {}).get("ps_ratio")
            growth = s.get("fundamentals", {}).get("revenue_growth")
            roe = s.get("fundamentals", {}).get("roe")

            # For P/E and P/S, lower is better → invert percentile
            pe_pct = _percentile_in_group(pe, pe_vals)
            if pe_pct is not None:
                pe_pct = 100 - pe_pct
            ps_pct = _percentile_in_group(ps, ps_vals)
            if ps_pct is not None:
                ps_pct = 100 - ps_pct

            # For growth and ROE, higher is better
            growth_pct = _percentile_in_group(growth, growth_vals)
            roe_pct = _percentile_in_group(roe, roe_vals)

            parts = [p for p in [pe_pct, ps_pct, growth_pct, roe_pct] if p is not None]
            composite = np.mean(parts) if parts else None

            entry = {
                "sector": sector,
                "sector_pe_pct": round(pe_pct, 2) if pe_pct is not None else None,
                "sector_ps_pct": round(ps_pct, 2) if ps_pct is not None else None,
                "sector_growth_pct": round(growth_pct, 2) if growth_pct is not None else None,
                "sector_roe_pct": round(roe_pct, 2) if roe_pct is not None else None,
                "sector_composite": round(composite, 2) if composite is not None else None,
            }
            output[s["ticker"]] = entry
            sector_scores.append((s["ticker"], composite))

        # Rank within sector
        sector_scores.sort(key=lambda x: x[1] if x[1] is not None else -1, reverse=True)
        for rank, (ticker, _) in enumerate(sector_scores, 1):
            output[ticker]["sector_rank"] = rank
            output[ticker]["sector_size"] = len(sector_scores)

    return output
