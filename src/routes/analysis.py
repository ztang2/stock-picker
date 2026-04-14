"""Fundamental and technical analysis endpoints."""

import asyncio

from fastapi import APIRouter, HTTPException, Query

from ..yfinance_client import get_ticker_object

from ..insider import get_combined_smart_money_score
from ..sec_edgar import get_sec_financials
from ..dcf_valuation import run_dcf, get_dcf_summary
from ..comps_analysis import run_comps
from ..earnings_analysis import analyze_earnings
from ..early_momentum import scan_top_momentum, format_momentum_report, compute_early_momentum
from ..entry_timing import analyze_entry_timing
from ..company_intel import get_company_intel, get_top_intel, format_intel_summary
from ..quality_scores import compute_quality_scores
from .deps import logger

router = APIRouter(tags=["analysis"])


@router.get("/insider/{ticker}")
def insider_analysis(ticker: str):
    """Get analyst revision + insider trading analysis for a ticker."""
    try:
        t = get_ticker_object(ticker.upper())
        return get_combined_smart_money_score(t)
    except Exception as e:
        raise HTTPException(500, f"Analysis failed: {e}")


@router.get("/sec/{ticker}")
def sec_data(ticker: str):
    """Get structured financial data from SEC EDGAR filings."""
    try:
        return get_sec_financials(ticker.upper())
    except Exception as e:
        raise HTTPException(500, f"SEC data fetch failed: {e}")


@router.get("/dcf/{ticker}")
def dcf_full(ticker: str):
    """Full DCF valuation analysis."""
    try:
        return run_dcf(ticker.upper())
    except Exception as e:
        raise HTTPException(500, f"DCF analysis failed: {e}")


@router.get("/dcf/{ticker}/summary")
def dcf_summary(ticker: str):
    """Quick DCF summary: intrinsic value + margin of safety."""
    try:
        return get_dcf_summary(ticker.upper())
    except Exception as e:
        raise HTTPException(500, f"DCF summary failed: {e}")


@router.get("/comps/{ticker}")
def comps(ticker: str, max_peers: int = Query(15, ge=3, le=30)):
    """Comparable company analysis vs sector peers."""
    try:
        return run_comps(ticker.upper(), max_peers=max_peers)
    except Exception as e:
        raise HTTPException(500, f"Comps analysis failed: {e}")


@router.get("/earnings/{ticker}/analysis")
def earnings_deep_analysis(ticker: str):
    """Deep earnings analysis: trends, beat/miss history, quality score."""
    try:
        return analyze_earnings(ticker.upper())
    except Exception as e:
        raise HTTPException(500, f"Earnings analysis failed: {e}")


@router.get("/quality/{ticker}")
def quality_scores(ticker: str):
    """Get Piotroski F-Score and Altman Z-Score for a stock."""
    return compute_quality_scores(ticker.upper())


@router.get("/momentum/scan/{n}")
def momentum_scan(n: int = 20):
    """Scan top stocks for early momentum signals."""
    results = scan_top_momentum(n)
    return {
        "count": len(results),
        "stocks": results,
        "report": format_momentum_report(results),
    }


@router.get("/momentum/{ticker}")
def early_momentum(ticker: str):
    """Get early momentum score for a single ticker."""
    return compute_early_momentum(ticker.upper())


@router.get("/entry/{ticker}")
def entry_timing(ticker: str):
    """Get entry timing analysis for a ticker (RSI, support levels, MA distance, volume)."""
    return analyze_entry_timing(ticker.upper())


@router.get("/intel/{ticker}")
def company_intel(ticker: str):
    """Get company intelligence (news, analysts, description) for a single ticker."""
    return get_company_intel(ticker.upper())


@router.get("/intel/top/{n}")
def top_intel(n: int = 20):
    """Get company intelligence for top N stocks from latest scan."""
    results = get_top_intel(n)
    return {
        "count": len(results),
        "stocks": results,
        "summaries": [format_intel_summary(r) for r in results],
    }
