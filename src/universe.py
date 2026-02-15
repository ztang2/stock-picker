"""Fetch S&P 500 ticker list from Wikipedia."""

import logging
import json
import time
from pathlib import Path

from typing import List

import pandas as pd

logger = logging.getLogger(__name__)

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
CACHE_FILE = DATA_DIR / "sp500_tickers.json"


def get_sp500_tickers(cache_hours: float = 24) -> List[str]:
    """Return list of S&P 500 tickers, cached to disk."""
    DATA_DIR.mkdir(exist_ok=True)

    if CACHE_FILE.exists():
        age_h = (time.time() - CACHE_FILE.stat().st_mtime) / 3600
        if age_h < cache_hours:
            tickers = json.loads(CACHE_FILE.read_text())
            logger.info("Loaded %d tickers from cache", len(tickers))
            return tickers

    logger.info("Fetching S&P 500 tickers from Wikipedia...")
    try:
        import requests
        from io import StringIO
        resp = requests.get(
            "https://en.wikipedia.org/wiki/List_of_S%26P_500_companies",
            headers={"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)"},
            timeout=15,
        )
        resp.raise_for_status()
        tables = pd.read_html(StringIO(resp.text), match="Symbol")
        df = tables[0]
        tickers = sorted(df["Symbol"].str.replace(".", "-", regex=False).tolist())
        CACHE_FILE.write_text(json.dumps(tickers))
        logger.info("Fetched %d tickers", len(tickers))
        return tickers
    except Exception:
        logger.exception("Failed to fetch tickers")
        if CACHE_FILE.exists():
            return json.loads(CACHE_FILE.read_text())
        raise
