"""Data freshness checking for stock data."""

import json
import logging
import time
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict, Tuple

import yfinance as yf

logger = logging.getLogger(__name__)

DATA_DIR = Path(__file__).resolve().parent.parent / "data"


def check_freshness(ticker: str) -> Tuple[str, Optional[int]]:
    """Check data freshness for a ticker. Returns (label, age_days)."""
    age_days = None
    
    # Check yfinance cache file modification time
    if age_days is None:
        cache_file = DATA_DIR / "stock_data_cache.json"
        if cache_file.exists():
            try:
                cache_age_days = int((time.time() - cache_file.stat().st_mtime) / 86400)
                age_days = cache_age_days
            except Exception:
                pass
    
    # Also try to check most recent quarterly report date via cached info
    if age_days is None:
        try:
            cache_file = DATA_DIR / "stock_data_cache.json"
            if cache_file.exists():
                data = json.loads(cache_file.read_text())
                stock_data = data.get(ticker.upper(), {})
                info = stock_data.get("info", {})
                # Check mostRecentQuarter
                mrq = info.get("mostRecentQuarter")
                if mrq:
                    mrq_dt = datetime.fromtimestamp(mrq) if isinstance(mrq, (int, float)) else datetime.fromisoformat(str(mrq))
                    age_days = (datetime.now() - mrq_dt).days
        except Exception:
            pass
    
    if age_days is None:
        return ("unknown", None)
    
    if age_days < 1:
        return ("fresh", age_days)
    elif age_days < 7:
        return ("recent", age_days)
    elif age_days < 30:
        return ("stale", age_days)
    else:
        return ("very_stale", age_days)
