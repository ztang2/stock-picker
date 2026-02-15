"""Earnings calendar and surprise data using yfinance."""

import logging
import time
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple

import yfinance as yf

logger = logging.getLogger(__name__)

_earnings_cache: Dict[str, Tuple[float, dict]] = {}
CACHE_TTL = 3600


def get_earnings_info(ticker: str) -> dict:
    """Get earnings date, surprise history for a ticker.

    Returns dict with next_earnings_date, earnings_soon (bool), surprises list.
    """
    now = time.time()
    if ticker in _earnings_cache:
        ts, cached = _earnings_cache[ticker]
        if now - ts < CACHE_TTL:
            return cached

    result = {
        "next_earnings_date": None,
        "earnings_soon": False,
        "surprises": [],
    }

    try:
        t = yf.Ticker(ticker)
        cal = None
        try:
            cal = t.calendar
        except Exception:
            pass

        # Try to get next earnings date
        if cal is not None:
            ed = None
            if isinstance(cal, dict):
                ed = cal.get("Earnings Date")
                if isinstance(ed, list) and ed:
                    ed = ed[0]
            if ed is not None:
                try:
                    if hasattr(ed, 'strftime'):
                        ed_str = ed.strftime("%Y-%m-%d")
                        ed_dt = ed
                    else:
                        ed_str = str(ed)[:10]
                        ed_dt = datetime.strptime(ed_str, "%Y-%m-%d")
                    result["next_earnings_date"] = ed_str
                    days_until = (ed_dt - datetime.now()).days if not hasattr(ed_dt, 'tzinfo') or ed_dt.tzinfo is None else (ed_dt.replace(tzinfo=None) - datetime.now()).days
                    result["earnings_soon"] = 0 <= days_until <= 14
                except Exception:
                    pass

        # Get earnings surprises from earnings_history or quarterly_earnings
        try:
            earnings = t.quarterly_earnings
            if earnings is not None and not earnings.empty:
                surprises = []
                for idx, row in earnings.tail(4).iterrows():
                    entry = {"quarter": str(idx)}
                    if "Surprise(%)" in row:
                        entry["surprise_pct"] = round(float(row["Surprise(%)"]), 2)
                    elif "Revenue" in row and "Earnings" in row:
                        entry["revenue"] = float(row["Revenue"])
                        entry["earnings"] = float(row["Earnings"])
                    surprises.append(entry)
                result["surprises"] = surprises
        except Exception:
            pass

    except Exception:
        logger.warning("Failed to get earnings for %s", ticker, exc_info=True)

    _earnings_cache[ticker] = (now, result)
    return result


def check_earnings_soon(tickers: List[str]) -> Dict[str, bool]:
    """Check which tickers have earnings in next 14 days. Returns {ticker: bool}."""
    out: Dict[str, bool] = {}
    for t in tickers:
        try:
            info = get_earnings_info(t)
            out[t] = info.get("earnings_soon", False)
        except Exception:
            out[t] = False
    return out
