"""Alpaca paper trading endpoints."""

from fastapi import APIRouter, Depends, HTTPException, Query

from ..alpaca_trader import (
    get_account as alpaca_get_account,
    get_positions as alpaca_get_positions,
    get_orders as alpaca_get_orders,
    sync_with_holdings as alpaca_sync,
    get_performance as alpaca_performance,
)
from .deps import verify_api_key

router = APIRouter(tags=["alpaca"])


@router.get("/alpaca/account")
def alpaca_account():
    """Paper trading account info."""
    try:
        return alpaca_get_account()
    except Exception as e:
        raise HTTPException(500, f"Alpaca error: {e}")


@router.get("/alpaca/positions")
def alpaca_positions():
    """Paper trading positions."""
    try:
        return alpaca_get_positions()
    except Exception as e:
        raise HTTPException(500, f"Alpaca error: {e}")


@router.get("/alpaca/orders")
def alpaca_orders(status: str = "all", limit: int = 50):
    """Paper trading orders."""
    try:
        return alpaca_get_orders(status, limit)
    except Exception as e:
        raise HTTPException(500, f"Alpaca error: {e}")


@router.post("/alpaca/sync")
def alpaca_sync_holdings(_ = Depends(verify_api_key)):
    """Sync paper portfolio with holdings.json."""
    try:
        return alpaca_sync()
    except Exception as e:
        raise HTTPException(500, f"Alpaca sync error: {e}")


@router.get("/alpaca/performance")
def alpaca_perf():
    """Paper trading performance."""
    try:
        return alpaca_performance()
    except Exception as e:
        raise HTTPException(500, f"Alpaca error: {e}")
