"""Fundamental analysis: revenue growth, profit margin, ROE, debt-to-equity."""

import logging
import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)


def score_fundamentals(info: dict) -> dict:
    """Extract fundamental metrics and compute a raw score dict.

    Returns dict with individual metrics and 'score' (0-100 raw, before percentile).
    """
    metrics: dict = {}

    # Revenue growth (YoY)
    rev_growth = info.get("revenueGrowth")
    metrics["revenue_growth"] = rev_growth

    # Profit margin
    profit_margin = info.get("profitMargins")
    metrics["profit_margin"] = profit_margin

    # ROE
    roe = info.get("returnOnEquity")
    metrics["roe"] = roe

    # Debt-to-equity
    dte = info.get("debtToEquity")
    if dte is not None:
        dte = dte / 100.0  # yfinance returns as percentage
    metrics["debt_to_equity"] = dte

    # Compute raw score components (each 0-25, total 0-100)
    components = []

    # Revenue growth: >30% → 25, 0% → 12.5, <-10% → 0
    if rev_growth is not None:
        components.append(np.clip(rev_growth * 50 + 12.5, 0, 25))
    else:
        components.append(None)

    # Profit margin: >30% → 25, 0 → 0
    if profit_margin is not None:
        components.append(np.clip(profit_margin * 83.3, 0, 25))
    else:
        components.append(None)

    # ROE: >30% → 25, 0 → 0
    if roe is not None:
        components.append(np.clip(roe * 83.3, 0, 25))
    else:
        components.append(None)

    # Debt-to-equity: 0 → 25, >2 → 0 (inverse)
    if dte is not None and dte >= 0:
        components.append(np.clip(25 - dte * 12.5, 0, 25))
    else:
        components.append(None)

    # --- Earnings Quality Metrics ---

    # Free cash flow yield
    fcf = info.get("freeCashflow")
    market_cap = info.get("marketCap")
    if fcf is not None and market_cap and market_cap > 0:
        fcf_yield = fcf / market_cap
        metrics["fcf_yield"] = fcf_yield
        # FCF yield > 8% → 25, 4% → 12.5, 0% → 0
        components.append(np.clip(fcf_yield * 312.5, 0, 25))
    else:
        metrics["fcf_yield"] = None
        components.append(None)

    # FCF vs net income ratio (earnings quality)
    net_income = info.get("netIncomeToCommon")
    if fcf is not None and net_income is not None and net_income != 0:
        fcf_ni_ratio = fcf / net_income
        metrics["fcf_to_net_income"] = fcf_ni_ratio
        # Ratio > 1 means FCF exceeds net income (high quality). Score: >1.2 → 25, 1.0 → 18, <0.5 → 5
        components.append(np.clip(fcf_ni_ratio * 20.8, 0, 25))
    else:
        metrics["fcf_to_net_income"] = None
        components.append(None)

    # Earnings surprise (not always available in yfinance, best-effort)
    earnings_surprise = info.get("earningsQuarterlyGrowth")
    metrics["earnings_quarterly_growth"] = earnings_surprise
    if earnings_surprise is not None:
        # Positive surprise/growth is good. >20% → 25, 0% → 12.5, <-20% → 0
        components.append(np.clip(earnings_surprise * 62.5 + 12.5, 0, 25))
    else:
        components.append(None)

    # Fix scoring inflation: use TOTAL component count (7), not just available count
    # Missing metrics contribute 0, not skipped
    TOTAL_COMPONENTS = 7
    score_sum = sum(c for c in components if c is not None)
    metrics["score"] = (score_sum / TOTAL_COMPONENTS) * (100 / 25)

    return metrics
