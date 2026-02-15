"""Portfolio builder: diversified allocation from top scored stocks."""

import logging
from typing import Dict, List, Optional

import numpy as np

logger = logging.getLogger(__name__)


def build_portfolio(ranked_stocks: List[dict], target_size: int = 10) -> dict:
    """Build a diversified portfolio from ranked stock list.

    Rules:
    - Max 3 stocks per sector
    - Min 4 sectors represented
    - Position sizing by inverse volatility
    - Returns allocation percentages and metrics

    Each stock dict should have: ticker, name, sector, risk (with volatility, beta).
    """
    if not ranked_stocks:
        return {"stocks": [], "metrics": {}}

    # Select stocks with sector diversification
    selected: List[dict] = []
    sector_counts: Dict[str, int] = {}
    sectors_seen: set = set()

    for s in ranked_stocks:
        if len(selected) >= target_size:
            break
        sector = s.get("sector", "Unknown")
        if sector_counts.get(sector, 0) >= 3:
            continue
        selected.append(s)
        sector_counts[sector] = sector_counts.get(sector, 0) + 1
        sectors_seen.add(sector)

    # If we don't have enough sectors, try to swap in stocks from new sectors
    if len(sectors_seen) < 4 and len(selected) < target_size:
        for s in ranked_stocks:
            if s in selected:
                continue
            sector = s.get("sector", "Unknown")
            if sector not in sectors_seen:
                if len(selected) < target_size:
                    selected.append(s)
                    sector_counts[sector] = sector_counts.get(sector, 0) + 1
                    sectors_seen.add(sector)
            if len(selected) >= target_size:
                break

    if not selected:
        return {"stocks": [], "metrics": {}}

    # Position sizing: inverse volatility
    vols = []
    for s in selected:
        risk = s.get("risk") or {}
        vol = risk.get("volatility")
        if vol and vol > 0:
            vols.append(vol)
        else:
            vols.append(0.3)  # default moderate volatility

    inv_vols = [1.0 / v for v in vols]
    total_inv = sum(inv_vols)
    weights = [iv / total_inv * 100 for iv in inv_vols]

    # Build output
    portfolio_stocks = []
    betas = []
    for s, w, vol in zip(selected, weights, vols):
        risk = s.get("risk") or {}
        beta = risk.get("beta", 1.0)
        if beta is None:
            beta = 1.0
        betas.append(beta * w / 100)

        portfolio_stocks.append({
            "ticker": s["ticker"],
            "name": s.get("name", s["ticker"]),
            "sector": s.get("sector", "Unknown"),
            "allocation_pct": round(w, 2),
            "volatility": round(vol, 4),
            "beta": round(beta, 3),
            "composite_score": s.get("composite_score"),
        })

    # Metrics
    portfolio_beta = round(sum(betas), 3)
    n_sectors = len(sectors_seen)
    # Diversification score: based on sector count and evenness of allocation
    alloc_array = np.array(weights) / 100
    herfindahl = float(np.sum(alloc_array ** 2))
    diversification = round((1 - herfindahl) * 100, 1)  # 0-100, higher = more diversified

    return {
        "stocks": portfolio_stocks,
        "metrics": {
            "portfolio_beta": portfolio_beta,
            "num_sectors": n_sectors,
            "num_stocks": len(selected),
            "diversification_score": diversification,
            "max_allocation_pct": round(max(weights), 2),
            "min_allocation_pct": round(min(weights), 2),
        }
    }
