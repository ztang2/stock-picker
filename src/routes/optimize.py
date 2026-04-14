"""Optimization and factor report endpoints."""

import json

from fastapi import APIRouter, Depends, HTTPException, Query

from ..optimizer import (
    run_optimization,
    get_optimization_status,
    load_optimization_results,
    apply_optimization,
)
from ..auto_optimize import run_monthly_optimization, get_optimization_history
from ..model_report import generate_factor_report, format_report_discord
from .deps import verify_api_key, RESULTS_FILE

router = APIRouter(tags=["optimize"])


@router.get("/optimize/run")
def optimize_run(strategy: str = Query("balanced")):
    """Run weight optimization."""
    try:
        result = run_optimization(strategy=strategy)
        return result
    except Exception as e:
        raise HTTPException(500, "Optimization failed: %s" % str(e))


@router.get("/optimize/status")
def optimize_status():
    """Check optimization progress."""
    return get_optimization_status()


@router.get("/optimize/results")
def optimize_results():
    """Get cached optimization results."""
    results = load_optimization_results()
    if not results:
        raise HTTPException(404, "No optimization results. Run /optimize/run first.")
    return results


@router.get("/optimize/apply")
def optimize_apply(dry_run: bool = Query(True), _: None = Depends(verify_api_key)):
    """Apply optimization results to config."""
    try:
        return apply_optimization(dry_run=dry_run)
    except Exception as e:
        raise HTTPException(500, "Apply failed: %s" % str(e))


@router.get("/optimize/monthly")
def optimize_monthly(
    strategy: str = Query("balanced", description="Strategy to optimize"),
    months_back: int = Query(6, ge=1, le=12),
):
    """Run monthly weight optimization."""
    try:
        result = run_monthly_optimization(strategy=strategy, months_back=months_back)
        return result
    except Exception as e:
        raise HTTPException(500, "Optimization failed: %s" % str(e))


@router.get("/optimize/history")
def optimize_history():
    """Return optimization changelog."""
    return {"history": get_optimization_history()}


@router.get("/report/factors")
def report_factors(months: int = Query(3, ge=1, le=12), format: str = Query("json")):
    """Get factor attribution report."""
    try:
        report = generate_factor_report(months=months)
        if format == "discord":
            return {"text": format_report_discord(report)}
        return report
    except Exception as e:
        raise HTTPException(500, "Report failed: %s" % str(e))
