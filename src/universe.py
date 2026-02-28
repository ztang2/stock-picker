"""Fetch stock universe: S&P 500 + optional S&P 400 MidCap growth stocks."""

import logging
import json
import time
from pathlib import Path
from typing import List

import pandas as pd
import yaml

logger = logging.getLogger(__name__)

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
CACHE_FILE = DATA_DIR / "sp500_tickers.json"
MIDCAP_CACHE_FILE = DATA_DIR / "sp400_tickers.json"
CONFIG_FILE = Path(__file__).resolve().parent.parent / "config.yaml"


def _load_config():
    if CONFIG_FILE.exists():
        return yaml.safe_load(CONFIG_FILE.read_text()) or {}
    return {}


def get_sp500_tickers(cache_hours: float = 24) -> List[str]:
    """Return list of S&P 500 tickers, cached to disk."""
    DATA_DIR.mkdir(exist_ok=True)

    if CACHE_FILE.exists():
        age_h = (time.time() - CACHE_FILE.stat().st_mtime) / 3600
        if age_h < cache_hours:
            tickers = json.loads(CACHE_FILE.read_text())
            logger.info("Loaded %d S&P 500 tickers from cache", len(tickers))
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
        logger.info("Fetched %d S&P 500 tickers", len(tickers))
        return tickers
    except Exception:
        logger.exception("Failed to fetch S&P 500 tickers")
        if CACHE_FILE.exists():
            return json.loads(CACHE_FILE.read_text())
        raise


def get_sp400_tickers(cache_hours: float = 24) -> List[str]:
    """Return list of S&P 400 MidCap tickers from Wikipedia, cached to disk."""
    DATA_DIR.mkdir(exist_ok=True)

    if MIDCAP_CACHE_FILE.exists():
        age_h = (time.time() - MIDCAP_CACHE_FILE.stat().st_mtime) / 3600
        if age_h < cache_hours:
            tickers = json.loads(MIDCAP_CACHE_FILE.read_text())
            logger.info("Loaded %d S&P 400 MidCap tickers from cache", len(tickers))
            return tickers

    logger.info("Fetching S&P 400 MidCap tickers from Wikipedia...")
    try:
        import requests
        from io import StringIO
        resp = requests.get(
            "https://en.wikipedia.org/wiki/List_of_S%26P_400_companies",
            headers={"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)"},
            timeout=15,
        )
        resp.raise_for_status()
        tables = pd.read_html(StringIO(resp.text), match="Symbol")
        df = tables[0]
        tickers = sorted(df["Symbol"].str.replace(".", "-", regex=False).tolist())
        MIDCAP_CACHE_FILE.write_text(json.dumps(tickers))
        logger.info("Fetched %d S&P 400 MidCap tickers", len(tickers))
        return tickers
    except Exception:
        logger.exception("Failed to fetch S&P 400 MidCap tickers")
        if MIDCAP_CACHE_FILE.exists():
            return json.loads(MIDCAP_CACHE_FILE.read_text())
        return []


def get_universe_tickers(cache_hours: float = 24) -> List[str]:
    """Return combined universe based on config.

    If config.yaml has `include_midcap: true`, combines S&P 500 + S&P 400 MidCap.
    Otherwise returns S&P 500 only.
    """
    config = _load_config()
    include_midcap = config.get("include_midcap", False)

    sp500 = get_sp500_tickers(cache_hours)

    if not include_midcap:
        return sp500

    sp400 = get_sp400_tickers(cache_hours)
    combined = sorted(set(sp500 + sp400))
    logger.info("Combined universe: %d tickers (S&P 500: %d, MidCap 400: %d, overlap removed)",
                len(combined), len(sp500), len(sp400))
    return combined
