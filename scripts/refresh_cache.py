#!/usr/bin/env python3
"""Refresh stock data cache and run scan. Called by cron/LaunchAgent after market close."""

import json
import logging
import sys
import time
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.pipeline import fetch_stock_data, load_config, run_scan
from src.cache_health import heal_cache

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

DATA_DIR = Path(__file__).parent.parent / "data"
CACHE_FILE = DATA_DIR / "stock_data_cache.json"
BATCH_SIZE = 50
BATCH_DELAY = 1.0  # seconds between batches


def refresh_full_cache():
    """Re-fetch all tickers in the cache from yfinance."""
    if not CACHE_FILE.exists():
        logger.error("Cache file not found: %s", CACHE_FILE)
        return

    data = json.loads(CACHE_FILE.read_text())
    tickers = [t for t in data.keys() if t != "SPY"]
    logger.info("Refreshing %d tickers...", len(tickers))

    refreshed = 0
    errors = 0
    for i in range(0, len(tickers), BATCH_SIZE):
        batch = tickers[i : i + BATCH_SIZE]
        for ticker in batch:
            try:
                fresh = fetch_stock_data(ticker, period="1y")
                if fresh:
                    data[ticker] = fresh
                    refreshed += 1
                else:
                    errors += 1
            except Exception as e:
                logger.warning("Failed to refresh %s: %s", ticker, e)
                errors += 1

        logger.info("Progress: %d/%d refreshed, %d errors", refreshed, len(tickers), errors)
        if i + BATCH_SIZE < len(tickers):
            time.sleep(BATCH_DELAY)

    # Also refresh SPY
    try:
        spy = fetch_stock_data("SPY", period="1y")
        if spy:
            data["SPY"] = spy
    except Exception:
        pass

    CACHE_FILE.write_text(json.dumps(data))
    logger.info("Cache refresh complete: %d/%d tickers updated", refreshed, len(tickers))
    return refreshed, errors


def main():
    logger.info("=== Starting scheduled cache refresh ===")

    # Step 1: Refresh full cache
    refresh_full_cache()

    # Step 2: Heal any NaN rows
    report = heal_cache()
    logger.info("Heal report: %s", report)

    # Step 3: Run scan
    logger.info("Running post-refresh scan...")
    config = load_config()
    run_scan(config)
    logger.info("=== Scheduled refresh complete ===")


if __name__ == "__main__":
    main()
