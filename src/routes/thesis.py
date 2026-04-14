"""Investment thesis tracking endpoints."""

from typing import List, Optional

from pydantic import BaseModel
from fastapi import APIRouter, Depends, HTTPException

from ..thesis_tracker import record_thesis, get_thesis, check_all_theses
from .deps import verify_api_key

router = APIRouter(tags=["thesis"])


class ThesisCreate(BaseModel):
    thesis: str
    entry_price: Optional[float] = None
    target_price: Optional[float] = None
    stop_loss: Optional[float] = None
    conditions: Optional[List[str]] = None
    time_horizon: Optional[str] = None


@router.post("/thesis/{ticker}")
def create_thesis(ticker: str, body: ThesisCreate, _: None = Depends(verify_api_key)):
    """Record an investment thesis."""
    try:
        return record_thesis(
            ticker.upper(),
            thesis=body.thesis,
            entry_price=body.entry_price,
            target_price=body.target_price,
            stop_loss=body.stop_loss,
            conditions=body.conditions,
            time_horizon=body.time_horizon,
        )
    except Exception as e:
        raise HTTPException(500, f"Failed to record thesis: {e}")


@router.get("/thesis/check")
def thesis_check():
    """Check all active investment theses."""
    try:
        return {"results": check_all_theses()}
    except Exception as e:
        raise HTTPException(500, f"Thesis check failed: {e}")


@router.get("/thesis/{ticker}")
def thesis_get(ticker: str):
    """Get current thesis and status for a ticker."""
    result = get_thesis(ticker.upper())
    if not result:
        raise HTTPException(404, f"No thesis found for {ticker.upper()}")
    return result


@router.get("/thesis/{ticker}/gemini")
async def thesis_gemini(ticker: str):
    """Gemini-powered bull thesis for a stock."""
    import asyncio

    from ..thesis import generate_gemini_thesis

    result = await asyncio.to_thread(generate_gemini_thesis, ticker.upper())
    if result is None:
        return {"ticker": ticker.upper(), "thesis": None, "source": "unavailable"}
    return result
