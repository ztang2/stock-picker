"""Risk management endpoints."""

import json
from pathlib import Path

from fastapi import APIRouter, HTTPException, Query

from ..risk_manager import (
    check_oil_price_alert,
    check_ceasefire_signals,
    check_trailing_stops,
    get_portfolio_summary,
    check_stop_losses,
    check_position_limits,
)
from ..profit_taker import check_profit_status, get_profit_summary, get_profit_status_single
from ..fred_data import get_economic_summary, fetch_fred_data
from ..rebalance import load_holdings
from .deps import DATA_DIR

router = APIRouter(tags=["risk"])


@router.get("/risk/oil")
def oil_monitor():
    """Check oil price vs recent peak for pullback alert."""
    result = check_oil_price_alert()
    return result or {"status": "unavailable"}


@router.get("/risk/ceasefire")
def ceasefire_monitor():
    """Check for early ceasefire / war de-escalation signals."""
    result = check_ceasefire_signals()
    return result or {"status": "unavailable"}


@router.get("/risk/trailing-stops")
def trailing_stops():
    """Check trailing stop alerts for all holdings."""
    holdings_file = DATA_DIR / "holdings.json"
    if not holdings_file.exists():
        return {"alerts": []}
    data = json.loads(holdings_file.read_text())
    holdings = (
        data.get("holdings", data)
        if isinstance(data, dict)
        else {x["ticker"]: x for x in data}
    )
    return {"alerts": check_trailing_stops(holdings)}


@router.get("/risk/summary")
def risk_summary():
    """Full portfolio risk summary: stop-losses, position limits, P&L."""
    holdings = load_holdings()
    return get_portfolio_summary(holdings)


@router.get("/risk/stop-losses")
def risk_stop_losses():
    """Check stop-loss status for all positions."""
    holdings = load_holdings()
    return {"alerts": check_stop_losses(holdings)}


@router.get("/risk/positions")
def risk_positions():
    """Check position size limits."""
    holdings = load_holdings()
    return {"positions": check_position_limits(holdings)}


@router.get("/profit/status")
def profit_status():
    """Check profit-taking status for all holdings."""
    holdings = load_holdings()
    alerts = check_profit_status(holdings)
    summary = get_profit_summary(alerts)

    return {
        "summary": summary,
        "alerts": alerts,
    }


@router.get("/profit/{ticker}")
def profit_ticker(ticker: str):
    """Get profit-taking status for a single ticker."""
    holdings = load_holdings()
    result = get_profit_status_single(ticker.upper(), holdings)

    if result is None:
        raise HTTPException(
            status_code=404, detail=f"Ticker {ticker.upper()} not found in holdings"
        )

    return result


@router.get("/economic/summary")
def economic_summary():
    """Get FRED economic data summary with composite score."""
    return get_economic_summary()


@router.get("/economic/data")
def economic_data(refresh: bool = Query(False)):
    """Get raw FRED economic data."""
    return fetch_fred_data(force_refresh=refresh)
