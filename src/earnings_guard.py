"""Earnings awareness guard — flags stocks with upcoming earnings and penalizes signals."""

import logging
import time
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple

import yfinance as yf

logger = logging.getLogger(__name__)

_earnings_cache = {}  # type: Dict[str, Tuple[float, dict]]
CACHE_TTL = 3600  # 1 hour
WARN_DAYS = 7  # warn if earnings within this many days

SIGNAL_TIERS = ["STRONG_BUY", "BUY", "HOLD", "WAIT"]


def get_earnings_guard(ticker):
    # type: (str) -> dict
    """Check if a stock has earnings within WARN_DAYS.

    Returns dict with:
        earnings_date: str or None (YYYY-MM-DD)
        earnings_warning: bool (True if within WARN_DAYS)
        days_until_earnings: int or None
    """
    now = time.time()
    if ticker in _earnings_cache:
        ts, cached = _earnings_cache[ticker]
        if now - ts < CACHE_TTL:
            return cached

    result = {
        "earnings_date": None,
        "earnings_warning": False,
        "days_until_earnings": None,
    }

    try:
        t = yf.Ticker(ticker)
        cal = None
        try:
            cal = t.calendar
        except Exception:
            pass

        if cal is not None:
            ed = None
            if isinstance(cal, dict):
                ed = cal.get("Earnings Date")
                if isinstance(ed, list) and ed:
                    ed = ed[0]
            if ed is not None:
                try:
                    if hasattr(ed, "strftime"):
                        ed_str = ed.strftime("%Y-%m-%d")
                        ed_dt = ed
                    else:
                        ed_str = str(ed)[:10]
                        ed_dt = datetime.strptime(ed_str, "%Y-%m-%d")

                    result["earnings_date"] = ed_str

                    if hasattr(ed_dt, "tzinfo") and ed_dt.tzinfo is not None:
                        ed_dt = ed_dt.replace(tzinfo=None)
                    days_until = (ed_dt - datetime.now()).days
                    result["days_until_earnings"] = days_until
                    result["earnings_warning"] = 0 <= days_until <= WARN_DAYS
                except Exception:
                    pass

    except Exception:
        logger.warning("Failed to get earnings guard for %s", ticker, exc_info=True)

    _earnings_cache[ticker] = (now, result)
    return result


def downgrade_signal(signal):
    # type: (str) -> str
    """Downgrade a signal by one tier (e.g. BUY -> HOLD)."""
    try:
        idx = SIGNAL_TIERS.index(signal)
        if idx < len(SIGNAL_TIERS) - 1:
            return SIGNAL_TIERS[idx + 1]
        return signal
    except ValueError:
        return signal


def apply_earnings_guard(stocks):
    # type: (List[dict]) -> List[dict]
    """For each stock dict, add earnings fields and downgrade signal if warning."""
    for stock in stocks:
        ticker = stock.get("ticker", "")
        try:
            guard = get_earnings_guard(ticker)
        except Exception:
            guard = {"earnings_date": None, "earnings_warning": False, "days_until_earnings": None}

        stock["earnings_date"] = guard["earnings_date"]
        stock["earnings_warning"] = guard["earnings_warning"]
        stock["days_until_earnings"] = guard["days_until_earnings"]

        if guard["earnings_warning"] and stock.get("entry_signal"):
            original = stock["entry_signal"]
            stock["entry_signal"] = downgrade_signal(original)
            if original != stock["entry_signal"]:
                stock["earnings_downgrade"] = True
    return stocks
