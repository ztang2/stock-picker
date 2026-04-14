"""Rebalance and position sizing endpoints."""

import json

from fastapi import APIRouter, Depends, HTTPException, Query

from ..rebalance import (
    load_holdings,
    load_rebalance_state,
    save_rebalance_state,
    update_signal_streaks,
    evaluate_swaps,
    format_rebalance_report,
)
from ..position_sizing import (
    get_single_ticker_sizing,
    get_portfolio_sizing,
    get_rebalance_suggestions,
)
from ..validation import validate_predictions, format_validation_report
from .deps import verify_api_key, RESULTS_FILE, logger

router = APIRouter(tags=["rebalance"])


@router.get("/rebalance/status")
def rebalance_status(_: None = Depends(verify_api_key)):
    """Get current rebalance state and holdings."""
    return {
        "holdings": load_holdings(),
        "state": load_rebalance_state(),
    }


@router.get("/rebalance/check")
def rebalance_check(_: None = Depends(verify_api_key)):
    """Run rebalance evaluation against latest scan results."""

    from ..scan_results_service import ScanResultsService
    scan_data = ScanResultsService.get_latest()
    if not scan_data:
        raise HTTPException(400, "No scan results. Run /scan first.")

    top = {s["ticker"]: s for s in scan_data.get("top", scan_data.get("stocks", []))}
    holdings = load_holdings()
    state = load_rebalance_state()

    held_signals = {t: top[t] for t in holdings if t in top}
    candidate_signals = {t: s for t, s in top.items() if t not in holdings}

    state = update_signal_streaks(state, held_signals, candidate_signals)
    save_rebalance_state(state)

    suggestions = evaluate_swaps(holdings, state, held_signals, candidate_signals)
    report = format_rebalance_report(suggestions, holdings)

    return {
        "suggestions": suggestions,
        "report": report,
        "holdings_count": len(holdings),
    }


@router.get("/validation/run")
def validation_run():
    """Run prediction validation (compare yesterday's predictions with today's reality)."""
    report = validate_predictions()
    return {
        "report": report,
        "formatted": format_validation_report(report),
    }


@router.get("/validation/summary")
def validation_summary(days: int = Query(7, ge=1, le=90)):
    """Get validation summary over recent days."""
    from ..validation import get_validation_summary

    return get_validation_summary(days=days)


@router.get("/sizing/{ticker}")
def sizing_ticker(
    ticker: str,
    portfolio_value: float = Query(default=10000, description="Total portfolio value"),
    num_positions: int = Query(default=8, description="Number of positions in portfolio"),
):
    """Get conviction score and recommended allocation for a single stock.

    Example: GET /sizing/AAPL?portfolio_value=50000&num_positions=10
    """
    result = get_single_ticker_sizing(ticker.upper(), portfolio_value, num_positions)

    if "error" in result:
        raise HTTPException(status_code=404, detail=result["error"])

    return result


@router.get("/sizing/portfolio")
def sizing_portfolio(
    portfolio_value: float = Query(default=10000, description="Total portfolio value"),
    rebalance: bool = Query(default=False, description="Include rebalance suggestions"),
):
    """Full portfolio sizing analysis with optional rebalance suggestions.

    Uses current holdings from holdings.json.

    Examples:
    - GET /sizing/portfolio?portfolio_value=50000
    - GET /sizing/portfolio?portfolio_value=50000&rebalance=true
    """
    if rebalance:
        result = get_rebalance_suggestions(portfolio_value)
    else:
        result = get_portfolio_sizing(portfolio_value)

    if "error" in result:
        raise HTTPException(status_code=400, detail=result["error"])

    return result
