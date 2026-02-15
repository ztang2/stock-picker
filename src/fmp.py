"""Financial Modeling Prep (FMP) API integration for historical fundamentals."""

import json
import logging
import os
import time
from datetime import datetime, date
from pathlib import Path
from typing import Optional, List, Dict, Any, Tuple

import requests

logger = logging.getLogger(__name__)

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
FMP_CACHE_DIR = DATA_DIR / "fmp_cache"
FMP_STATUS_FILE = DATA_DIR / "fmp_status.json"
BASE_URL = "https://financialmodelingprep.com/stable"
DAILY_LIMIT = 240  # leave 10 buffer from 250


def _get_api_key() -> str:
    """Load FMP API key from environment or .env file."""
    key = os.environ.get("FMP_API_KEY")
    if key:
        return key
    env_path = Path(__file__).resolve().parent.parent / ".env"
    if env_path.exists():
        for line in env_path.read_text().splitlines():
            line = line.strip()
            if line.startswith("FMP_API_KEY="):
                return line.split("=", 1)[1].strip()
    raise RuntimeError("FMP_API_KEY not found in environment or .env file")


def _load_status() -> Dict[str, Any]:
    """Load fetch status tracking file."""
    if FMP_STATUS_FILE.exists():
        try:
            return json.loads(FMP_STATUS_FILE.read_text())
        except Exception:
            pass
    return {"cached_tickers": [], "calls_today": 0, "last_call_date": "", "errors": {}}


def _save_status(status: Dict[str, Any]) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    FMP_STATUS_FILE.write_text(json.dumps(status, indent=2))


def _reset_daily_count_if_needed(status: Dict[str, Any]) -> Dict[str, Any]:
    today = date.today().isoformat()
    if status.get("last_call_date") != today:
        status["calls_today"] = 0
        status["last_call_date"] = today
    return status


def _api_get(endpoint: str, params: Dict[str, str]) -> Tuple[Optional[Any], bool]:
    """Make an API call. Returns (data, success). Increments call count."""
    try:
        api_key = _get_api_key()
    except RuntimeError as e:
        logger.error(str(e))
        return None, False

    params["apikey"] = api_key
    url = "%s/%s" % (BASE_URL, endpoint)
    try:
        r = requests.get(url, params=params, timeout=30)
        if r.status_code == 429:
            logger.warning("FMP rate limit hit")
            return {"Error": "RateLimit"}, False
        if r.status_code != 200:
            logger.warning("FMP API error %d for %s", r.status_code, endpoint)
            return None, False
        # Check for premium restriction (returns plain text, not JSON)
        text = r.text.strip()
        if "Premium" in text or "subscription" in text or "not available" in text:
            return {"Error": "Premium required"}, False
        data = r.json()
        return data, True
    except Exception as e:
        logger.warning("FMP request failed: %s", str(e))
        return None, False


def fetch_fundamentals(ticker: str) -> Optional[Dict[str, Any]]:
    """Fetch income statement, balance sheet, cash flow, and ratios for one ticker.

    Makes 4 API calls. Caches result as JSON.
    Returns the cached data dict or None on failure.
    """
    FMP_CACHE_DIR.mkdir(parents=True, exist_ok=True)
    status = _load_status()
    status = _reset_daily_count_if_needed(status)

    # Check if already cached
    cache_file = FMP_CACHE_DIR / ("%s.json" % ticker.upper())
    if cache_file.exists():
        try:
            return json.loads(cache_file.read_text())
        except Exception:
            pass

    # Need 4 calls
    if status["calls_today"] + 4 > DAILY_LIMIT:
        logger.info("FMP daily limit would be exceeded (%d used), skipping %s", status["calls_today"], ticker)
        return None

    # Check if this ticker is known to be unavailable (premium-only)
    unavailable = set(status.get("unavailable_tickers", []))
    if ticker.upper() in unavailable:
        return None

    result = {}  # type: Dict[str, Any]
    endpoints = [
        ("income_statement", "income-statement", {"symbol": ticker, "period": "annual"}),
        ("balance_sheet", "balance-sheet-statement", {"symbol": ticker, "period": "annual"}),
        ("cash_flow", "cash-flow-statement", {"symbol": ticker, "period": "annual"}),
        ("ratios", "ratios", {"symbol": ticker, "period": "annual"}),
    ]

    for key, endpoint, params in endpoints:
        data, ok = _api_get(endpoint, params)
        status["calls_today"] += 1
        if not ok or data is None or (isinstance(data, dict) and "Error" in str(data)):
            # Rate limit — do NOT blacklist, just bail for now
            if isinstance(data, dict) and data.get("Error") == "RateLimit":
                logger.info("Rate limited fetching %s for %s, will retry tomorrow", key, ticker)
                status["errors"][ticker] = "RateLimit on %s" % key
                _save_status(status)
                return None
            # Mark as unavailable only for premium/real failures
            if isinstance(data, dict) and data.get("Error") == "Premium required":
                if "unavailable_tickers" not in status:
                    status["unavailable_tickers"] = []
                if ticker.upper() not in status["unavailable_tickers"]:
                    status["unavailable_tickers"].append(ticker.upper())
            status["errors"][ticker] = "Failed on %s" % key
            _save_status(status)
            return None
        # Check for empty list (no data for this ticker)
        if isinstance(data, list) and len(data) == 0:
            if "unavailable_tickers" not in status:
                status["unavailable_tickers"] = []
            if ticker.upper() not in status["unavailable_tickers"]:
                status["unavailable_tickers"].append(ticker.upper())
            status["errors"][ticker] = "No data for %s" % key
            _save_status(status)
            return None
        result[key] = data
        time.sleep(0.3)  # be nice to the API

    result["fetched_at"] = datetime.now().isoformat()
    result["ticker"] = ticker.upper()

    cache_file.write_text(json.dumps(result, indent=2, default=str))

    if ticker.upper() not in status["cached_tickers"]:
        status["cached_tickers"].append(ticker.upper())
    status["errors"].pop(ticker, None)
    _save_status(status)

    logger.info("Cached FMP data for %s (%d calls today)", ticker, status["calls_today"])
    return result


def get_cached_fundamentals(ticker: str, year: Optional[int] = None) -> Optional[Dict[str, Any]]:
    """Get cached FMP data for a ticker, optionally filtered to a specific fiscal year."""
    cache_file = FMP_CACHE_DIR / ("%s.json" % ticker.upper())
    if not cache_file.exists():
        return None
    try:
        data = json.loads(cache_file.read_text())
    except Exception:
        return None

    if year is None:
        return data

    # Filter each statement to the matching year
    filtered = {"ticker": data.get("ticker"), "fetched_at": data.get("fetched_at")}
    for key in ["income_statement", "balance_sheet", "cash_flow", "ratios"]:
        items = data.get(key, [])
        if not isinstance(items, list):
            filtered[key] = items
            continue
        matched = [i for i in items if _extract_year(i) == year]
        filtered[key] = matched
    return filtered


def _extract_year(item: Dict[str, Any]) -> Optional[int]:
    """Extract fiscal year from an FMP record."""
    # Try calendarYear first, then parse date
    cy = item.get("calendarYear")
    if cy is not None:
        try:
            return int(cy)
        except (ValueError, TypeError):
            pass
    d = item.get("date", "")
    if d and len(d) >= 4:
        try:
            return int(d[:4])
        except ValueError:
            pass
    return None


def get_historical_info(ticker: str, as_of_date: str) -> Optional[Dict[str, Any]]:
    """Reconstruct a yfinance-like info dict using FMP data closest to as_of_date.

    Maps FMP fields to the keys expected by score_fundamentals, score_valuation, score_growth.
    """
    data = get_cached_fundamentals(ticker)
    if data is None:
        return None

    as_of_year = int(as_of_date[:4])
    # Find the most recent fiscal year that ended before as_of_date
    # Annual statements usually cover the prior calendar year
    target_year = as_of_year - 1  # fiscal year before as_of

    income = _find_nearest_year(data.get("income_statement", []), target_year)
    balance = _find_nearest_year(data.get("balance_sheet", []), target_year)
    cashflow = _find_nearest_year(data.get("cash_flow", []), target_year)
    ratios = _find_nearest_year(data.get("ratios", []), target_year)

    # Also get prior year for growth calculations
    prev_income = _find_nearest_year(data.get("income_statement", []), target_year - 1)

    if not income and not ratios:
        return None

    info = {}  # type: Dict[str, Any]

    # From ratios
    if ratios:
        info["profitMargins"] = ratios.get("netProfitMargin")
        info["grossMargins"] = ratios.get("grossProfitMargin")
        info["operatingMargins"] = ratios.get("operatingProfitMargin")
        info["dividendYield"] = ratios.get("dividendYield")

        pe = ratios.get("priceToEarningsRatio")
        if pe is not None:
            info["forwardPE"] = pe
            info["trailingPE"] = pe

        info["priceToSalesTrailing12Months"] = ratios.get("priceToSalesRatio")
        info["pegRatio"] = ratios.get("priceToEarningsGrowthRatio")

        dte = ratios.get("debtToEquityRatio")
        if dte is not None:
            info["debtToEquity"] = dte * 100  # yfinance format (percentage)

    # Revenue growth from consecutive years
    if income and prev_income:
        rev = income.get("revenue")
        prev_rev = prev_income.get("revenue")
        if rev and prev_rev and prev_rev != 0:
            info["revenueGrowth"] = (rev - prev_rev) / abs(prev_rev)

    # ROE from netIncome / stockholdersEquity
    if income and balance:
        ni = income.get("netIncome")
        equity = balance.get("totalStockholdersEquity")
        if ni is not None and equity and equity != 0:
            info["returnOnEquity"] = ni / abs(equity)

    # Free cash flow
    if cashflow:
        fcf = cashflow.get("freeCashFlow")
        if fcf is not None:
            info["freeCashflow"] = fcf

    # Earnings quarterly growth proxy: compute from income statements
    if income and prev_income:
        ni = income.get("netIncome")
        prev_ni = prev_income.get("netIncome")
        if ni is not None and prev_ni is not None and prev_ni != 0:
            info["earningsQuarterlyGrowth"] = (ni - prev_ni) / abs(prev_ni)

    return info if info else None


def _find_nearest_year(items: List[Dict[str, Any]], target_year: int) -> Optional[Dict[str, Any]]:
    """Find the record closest to target_year."""
    if not items or not isinstance(items, list):
        return None
    best = None
    best_diff = 999
    for item in items:
        y = _extract_year(item)
        if y is None:
            continue
        diff = abs(y - target_year)
        if diff < best_diff:
            best_diff = diff
            best = item
    # Only return if within 1 year
    if best_diff <= 1:
        return best
    return None


def fetch_all_fundamentals(tickers: List[str], limit: Optional[int] = None) -> Dict[str, Any]:
    """Batch fetch fundamentals for multiple tickers, respecting rate limits.

    Resumable: skips already-cached tickers.
    Returns summary of what was fetched.
    """
    status = _load_status()
    status = _reset_daily_count_if_needed(status)

    cached = set(status.get("cached_tickers", []))
    unavailable = set(status.get("unavailable_tickers", []))
    to_fetch = [t for t in tickers if t.upper() not in cached and t.upper() not in unavailable]

    if limit is not None:
        to_fetch = to_fetch[:limit]

    # Check how many we can do (4 calls per ticker)
    max_tickers = (DAILY_LIMIT - status["calls_today"]) // 4
    if max_tickers <= 0:
        return {
            "fetched": 0,
            "already_cached": len(cached),
            "remaining": len(to_fetch),
            "calls_today": status["calls_today"],
            "message": "Daily API limit reached. Try again tomorrow.",
        }

    to_fetch = to_fetch[:max_tickers]
    fetched = 0
    errors = 0

    for ticker in to_fetch:
        result = fetch_fundamentals(ticker)
        if result is not None:
            fetched += 1
        else:
            errors += 1
            # Check if we hit rate limit
            status = _load_status()
            if status["calls_today"] >= DAILY_LIMIT:
                break

    status = _load_status()
    remaining = len([t for t in tickers if t.upper() not in set(status.get("cached_tickers", []))])

    return {
        "fetched": fetched,
        "errors": errors,
        "already_cached": len(status.get("cached_tickers", [])),
        "remaining": remaining,
        "calls_today": status["calls_today"],
        "calls_remaining_today": max(0, DAILY_LIMIT - status["calls_today"]),
    }


def get_fetch_status() -> Dict[str, Any]:
    """Get current FMP fetch status."""
    status = _load_status()
    status = _reset_daily_count_if_needed(status)
    _save_status(status)
    return {
        "cached_tickers": len(status.get("cached_tickers", [])),
        "cached_list": status.get("cached_tickers", []),
        "unavailable_tickers": len(status.get("unavailable_tickers", [])),
        "calls_today": status["calls_today"],
        "calls_remaining_today": max(0, DAILY_LIMIT - status["calls_today"]),
        "last_call_date": status.get("last_call_date", ""),
        "errors": status.get("errors", {}),
    }
