"""Investment thesis tracker.

Records why a stock was bought and checks if the thesis conditions still hold.
"""

import json
import logging
import time
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

import yfinance as yf

logger = logging.getLogger(__name__)

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
THESIS_FILE = DATA_DIR / "thesis_tracker.json"


def _load_theses() -> Dict[str, dict]:
    """Load all theses from disk."""
    if THESIS_FILE.exists():
        try:
            return json.loads(THESIS_FILE.read_text())
        except Exception:
            return {}
    return {}


def _save_theses(theses: Dict[str, dict]):
    """Save theses to disk."""
    DATA_DIR.mkdir(exist_ok=True)
    THESIS_FILE.write_text(json.dumps(theses, indent=2, default=str))


def record_thesis(
    ticker: str,
    thesis: str,
    entry_price: Optional[float] = None,
    target_price: Optional[float] = None,
    stop_loss: Optional[float] = None,
    conditions: Optional[List[str]] = None,
    time_horizon: Optional[str] = None,
) -> dict:
    """Record an investment thesis for a ticker.

    Args:
        ticker: Stock ticker
        thesis: Free-text description of why we bought
        entry_price: Price at entry
        target_price: Price target
        stop_loss: Stop loss price
        conditions: List of conditions that must remain true for thesis to hold
        time_horizon: Expected holding period (e.g., "6 months", "1 year")
    """
    ticker = ticker.upper()
    theses = _load_theses()

    entry = {
        "ticker": ticker,
        "thesis": thesis,
        "entry_price": entry_price,
        "target_price": target_price,
        "stop_loss": stop_loss,
        "conditions": conditions or [],
        "time_horizon": time_horizon,
        "created_at": datetime.now().isoformat(),
        "status": "active",
        "checks": [],
    }

    # If updating existing, preserve history
    if ticker in theses and theses[ticker].get("status") == "active":
        old = theses[ticker]
        entry["previous_thesis"] = {
            "thesis": old.get("thesis"),
            "created_at": old.get("created_at"),
        }

    theses[ticker] = entry
    _save_theses(theses)
    return entry


def get_thesis(ticker: str) -> Optional[dict]:
    """Get current thesis and status for a ticker."""
    ticker = ticker.upper()
    theses = _load_theses()
    thesis = theses.get(ticker)
    if not thesis:
        return None

    # Enrich with current price data
    try:
        t = yf.Ticker(ticker)
        info = t.info or {}
        current_price = info.get("currentPrice") or info.get("regularMarketPrice")
        if current_price and thesis.get("entry_price"):
            thesis["current_price"] = round(current_price, 2)
            thesis["return_pct"] = round(
                (current_price - thesis["entry_price"]) / thesis["entry_price"] * 100, 2
            )
            if thesis.get("target_price"):
                thesis["target_progress_pct"] = round(
                    (current_price - thesis["entry_price"])
                    / (thesis["target_price"] - thesis["entry_price"])
                    * 100,
                    2,
                )
            if thesis.get("stop_loss") and current_price <= thesis["stop_loss"]:
                thesis["stop_loss_triggered"] = True
    except Exception as e:
        logger.warning("Failed to enrich thesis for %s: %s", ticker, e)

    return thesis


def check_thesis(ticker: str) -> dict:
    """Check if a single thesis is still valid."""
    ticker = ticker.upper()
    theses = _load_theses()
    thesis = theses.get(ticker)

    if not thesis:
        return {"ticker": ticker, "error": "No thesis found"}

    if thesis.get("status") != "active":
        return {"ticker": ticker, "status": thesis["status"], "message": "Thesis is no longer active"}

    warnings = []
    status = "VALID"

    try:
        t = yf.Ticker(ticker)
        info = t.info or {}
        current_price = info.get("currentPrice") or info.get("regularMarketPrice", 0)

        # Check stop loss
        if thesis.get("stop_loss") and current_price and current_price <= thesis["stop_loss"]:
            warnings.append(f"STOP LOSS triggered: ${current_price:.2f} <= ${thesis['stop_loss']:.2f}")
            status = "BREACHED"

        # Check target reached
        if thesis.get("target_price") and current_price and current_price >= thesis["target_price"]:
            warnings.append(f"TARGET reached: ${current_price:.2f} >= ${thesis['target_price']:.2f}")
            status = "TARGET_HIT"

        # Check large drawdown from entry
        if thesis.get("entry_price") and current_price:
            drawdown = (current_price - thesis["entry_price"]) / thesis["entry_price"] * 100
            if drawdown < -20:
                warnings.append(f"Large drawdown: {drawdown:.1f}% from entry")
                if status == "VALID":
                    status = "WARNING"

        # Check fundamental conditions
        conditions = thesis.get("conditions", [])
        for cond in conditions:
            cond_lower = cond.lower()
            # Auto-check common conditions
            if "revenue growth" in cond_lower:
                rg = info.get("revenueGrowth")
                if rg is not None and rg < 0:
                    warnings.append(f"Condition may be failing: '{cond}' — revenue growth is {rg:.1%}")
                    if status == "VALID":
                        status = "WARNING"
            elif "profit" in cond_lower and "margin" in cond_lower:
                pm = info.get("profitMargins")
                if pm is not None and pm < 0:
                    warnings.append(f"Condition may be failing: '{cond}' — profit margin is {pm:.1%}")
                    if status == "VALID":
                        status = "WARNING"

    except Exception as e:
        warnings.append(f"Could not check current data: {e}")

    # Record check
    check_entry = {
        "checked_at": datetime.now().isoformat(),
        "status": status,
        "warnings": warnings,
    }
    thesis.setdefault("checks", []).append(check_entry)
    thesis["last_check"] = check_entry
    _save_theses(theses)

    return {
        "ticker": ticker,
        "status": status,
        "thesis": thesis.get("thesis"),
        "warnings": warnings,
        "entry_price": thesis.get("entry_price"),
        "current_price": current_price if 'current_price' in dir() else None,
    }


def check_all_theses() -> List[dict]:
    """Check all active theses and return results."""
    theses = _load_theses()
    results = []

    for ticker, thesis in theses.items():
        if thesis.get("status") != "active":
            continue
        result = check_thesis(ticker)
        results.append(result)

    return results


def close_thesis(ticker: str, reason: str = "manual") -> dict:
    """Mark a thesis as closed."""
    ticker = ticker.upper()
    theses = _load_theses()

    if ticker not in theses:
        return {"error": f"No thesis found for {ticker}"}

    theses[ticker]["status"] = "closed"
    theses[ticker]["closed_at"] = datetime.now().isoformat()
    theses[ticker]["close_reason"] = reason
    _save_theses(theses)

    return {"ticker": ticker, "status": "closed", "reason": reason}
