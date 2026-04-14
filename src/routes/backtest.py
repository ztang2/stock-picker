"""Backtesting endpoints."""

from fastapi import APIRouter, HTTPException, Query

from ..backtest import (
    run_backtest,
    load_backtest_history,
    run_rolling_backtest,
    get_rolling_backtest_status,
)
from .deps import DATA_DIR

router = APIRouter(tags=["backtest"])


@router.get("/backtest")
def backtest(
    months_back: int = Query(6, ge=1, le=24, description="How many months back to test"),
    top_n: int = Query(20, ge=5, le=50),
):
    """Run a backtest from N months ago."""
    try:
        result = run_backtest(months_back=months_back, top_n=top_n)
        return result
    except Exception as e:
        raise HTTPException(500, "Backtest failed: %s" % str(e))


@router.get("/backtest/rolling")
def rolling_backtest(
    years: int = Query(5, ge=1, le=10, description="Years of rolling backtest"),
    force: bool = Query(False, description="Force re-run ignoring cache"),
):
    """Run rolling monthly backtest across all strategies."""
    try:
        if force:
            cache_file = DATA_DIR / "rolling_backtest.json"
            if cache_file.exists():
                cache_file.unlink()
        result = run_rolling_backtest(years=years)
        return result
    except Exception as e:
        raise HTTPException(500, "Rolling backtest failed: %s" % str(e))


@router.get("/backtest/rolling/status")
def rolling_backtest_status():
    """Check if rolling backtest is in progress."""
    return get_rolling_backtest_status()


@router.get("/backtest/history")
def backtest_history():
    """Return all past backtest results."""
    return {"results": load_backtest_history()}
