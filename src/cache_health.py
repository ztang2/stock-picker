"""Cache health: detect and fix NaN/stale prices in stock_data_cache.json."""

import json
import logging
import math
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

import pandas as pd

logger = logging.getLogger(__name__)

DATA_DIR = Path(__file__).parent.parent / "data"
CACHE_FILE = DATA_DIR / "stock_data_cache.json"


def _is_nan(val) -> bool:
    """Check if a value is NaN (handles float, None, string 'nan')."""
    if val is None:
        return True
    try:
        return math.isnan(float(val))
    except (TypeError, ValueError):
        return False


def _last_trading_date() -> datetime:
    """Approximate last trading date (skip weekends)."""
    now = datetime.now(timezone.utc)
    if now.weekday() == 5:  # Saturday
        return now - timedelta(days=1)
    if now.weekday() == 6:  # Sunday
        return now - timedelta(days=2)
    return now


def diagnose_cache(cache_path: Optional[str] = None) -> dict:
    """Read-only diagnosis of cache health.

    Returns: {total, nan_count, stale_count, nan_tickers, stale_tickers, last_modified}
    """
    path = Path(cache_path) if cache_path else CACHE_FILE
    if not path.exists():
        return {"total": 0, "nan_count": 0, "stale_count": 0, "nan_tickers": [], "stale_tickers": [], "last_modified": None}

    data = json.loads(path.read_text())
    cutoff = _last_trading_date() - timedelta(days=3)
    nan_tickers = []
    stale_tickers = []

    for ticker, tdata in data.items():
        if ticker == "SPY":
            continue
        close_list = tdata.get("history", {}).get("Close", [])
        index_list = tdata.get("history_index", [])

        if not close_list or _is_nan(close_list[-1]):
            nan_tickers.append(ticker)
            continue

        if index_list:
            try:
                last_date = pd.to_datetime(index_list[-1], utc=True)
                if last_date < pd.Timestamp(cutoff, tz="UTC"):
                    stale_tickers.append(ticker)
            except Exception:
                stale_tickers.append(ticker)

    return {
        "total": len(data) - (1 if "SPY" in data else 0),
        "nan_count": len(nan_tickers),
        "stale_count": len(stale_tickers),
        "nan_tickers": nan_tickers[:50],
        "stale_tickers": stale_tickers[:50],
        "last_modified": datetime.fromtimestamp(path.stat().st_mtime).isoformat() if path.exists() else None,
    }


def heal_cache(cache_path: Optional[str] = None, max_refetch: int = 50) -> dict:
    """Detect and fix NaN/stale data in cache.

    1. Drop trailing NaN Close rows from all tickers
    2. Re-fetch up to max_refetch stale tickers from yfinance
    3. Save updated cache

    Returns: {healed_nan, refetched, dropped, total, errors}
    """
    from .pipeline import fetch_stock_data

    path = Path(cache_path) if cache_path else CACHE_FILE
    if not path.exists():
        return {"healed_nan": 0, "refetched": 0, "dropped": 0, "total": 0, "errors": []}

    data = json.loads(path.read_text())
    cutoff = _last_trading_date() - timedelta(days=3)
    healed_nan = 0
    refetched = 0
    dropped = 0
    errors = []

    # Pass 1: Drop trailing NaN Close rows
    for ticker, tdata in list(data.items()):
        if ticker == "SPY":
            continue
        close_list = tdata.get("history", {}).get("Close", [])
        if not close_list:
            continue

        # Count trailing NaNs
        trim = 0
        for val in reversed(close_list):
            if _is_nan(val):
                trim += 1
            else:
                break

        if trim > 0:
            for col in tdata["history"]:
                tdata["history"][col] = tdata["history"][col][:-trim]
            tdata["history_index"] = tdata["history_index"][:-trim]
            healed_nan += 1

            # If all data was NaN, drop ticker
            if not tdata["history"].get("Close"):
                del data[ticker]
                dropped += 1

    # Pass 2: Re-fetch stale tickers
    stale = []
    for ticker, tdata in data.items():
        if ticker == "SPY":
            continue
        index_list = tdata.get("history_index", [])
        if not index_list:
            stale.append(ticker)
            continue
        try:
            last_date = pd.to_datetime(index_list[-1], utc=True)
            if last_date < pd.Timestamp(cutoff, tz="UTC"):
                stale.append(ticker)
        except Exception:
            stale.append(ticker)

    refetch_batch = stale[:max_refetch]
    if refetch_batch:
        logger.info("Re-fetching %d stale tickers: %s...", len(refetch_batch), refetch_batch[:5])
        for ticker in refetch_batch:
            try:
                fresh = fetch_stock_data(ticker, period="1y")
                if fresh:
                    data[ticker] = fresh
                    refetched += 1
                else:
                    errors.append(f"{ticker}: fetch returned None")
            except Exception as e:
                errors.append(f"{ticker}: {e}")
            time.sleep(0.2)

    # Save
    path.write_text(json.dumps(data))
    logger.info("Cache healed: %d NaN fixed, %d refetched, %d dropped", healed_nan, refetched, dropped)

    return {
        "healed_nan": healed_nan,
        "refetched": refetched,
        "dropped": dropped,
        "total": len(data) - (1 if "SPY" in data else 0),
        "errors": errors[:20],
    }
