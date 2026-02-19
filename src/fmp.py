"""Fundamental data fetching — now uses yfinance (was FMP API).

Migrated 2026-02-17: FMP free tier stopped working (402 errors).
yfinance provides the same data without API keys or rate limits.
Module kept as fmp.py for backward compatibility.
"""

import json
import logging
import math
import time
from datetime import datetime, date
from pathlib import Path
from typing import Optional, List, Dict, Any

import yfinance as yf

logger = logging.getLogger(__name__)

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
FMP_CACHE_DIR = DATA_DIR / "fmp_cache"
FMP_STATUS_FILE = DATA_DIR / "fmp_status.json"


def _load_status() -> Dict[str, Any]:
    if FMP_STATUS_FILE.exists():
        try:
            return json.loads(FMP_STATUS_FILE.read_text())
        except Exception:
            pass
    return {"cached_tickers": [], "calls_today": 0, "last_call_date": "", "errors": {}}


def _save_status(status: Dict[str, Any]) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    FMP_STATUS_FILE.write_text(json.dumps(status, indent=2))


def _safe_float(v) -> Optional[float]:
    """Convert to float, returning None for NaN/inf/non-numeric."""
    if v is None:
        return None
    try:
        f = float(v)
        if math.isnan(f) or math.isinf(f):
            return None
        return f
    except (ValueError, TypeError):
        return None


def _yf_income_to_fmp(df) -> List[Dict[str, Any]]:
    """Convert yfinance financials DataFrame to FMP-like income statement records."""
    records = []
    if df is None or df.empty:
        return records
    for col in df.columns:
        year = col.year if hasattr(col, 'year') else int(str(col)[:4])
        d = df[col]
        rec = {
            "date": str(col.date()) if hasattr(col, 'date') else str(col)[:10],
            "calendarYear": str(year),
            "revenue": _safe_float(d.get("Total Revenue", d.get("Operating Revenue"))),
            "grossProfit": _safe_float(d.get("Gross Profit")),
            "operatingIncome": _safe_float(d.get("Operating Income")),
            "netIncome": _safe_float(d.get("Net Income", d.get("Net Income Common Stockholders"))),
            "eps": _safe_float(d.get("Basic EPS", d.get("Diluted EPS"))),
            "epsdiluted": _safe_float(d.get("Diluted EPS")),
            "ebitda": _safe_float(d.get("EBITDA")),
            "operatingExpenses": _safe_float(d.get("Operating Expense", d.get("Total Operating Expenses"))),
            "costOfRevenue": _safe_float(d.get("Cost Of Revenue")),
        }
        records.append(rec)
    return records


def _yf_balance_to_fmp(df) -> List[Dict[str, Any]]:
    """Convert yfinance balance_sheet DataFrame to FMP-like records."""
    records = []
    if df is None or df.empty:
        return records
    for col in df.columns:
        year = col.year if hasattr(col, 'year') else int(str(col)[:4])
        d = df[col]
        rec = {
            "date": str(col.date()) if hasattr(col, 'date') else str(col)[:10],
            "calendarYear": str(year),
            "totalAssets": _safe_float(d.get("Total Assets")),
            "totalLiabilities": _safe_float(d.get("Total Liabilities Net Minority Interest", d.get("Total Liabilities"))),
            "totalStockholdersEquity": _safe_float(d.get("Stockholders Equity", d.get("Total Equity Gross Minority Interest"))),
            "totalDebt": _safe_float(d.get("Total Debt")),
            "totalCurrentAssets": _safe_float(d.get("Current Assets")),
            "totalCurrentLiabilities": _safe_float(d.get("Current Liabilities")),
            "cashAndCashEquivalents": _safe_float(d.get("Cash And Cash Equivalents")),
            "longTermDebt": _safe_float(d.get("Long Term Debt")),
        }
        records.append(rec)
    return records


def _yf_cashflow_to_fmp(df) -> List[Dict[str, Any]]:
    """Convert yfinance cashflow DataFrame to FMP-like records."""
    records = []
    if df is None or df.empty:
        return records
    for col in df.columns:
        year = col.year if hasattr(col, 'year') else int(str(col)[:4])
        d = df[col]
        operating_cf = _safe_float(d.get("Operating Cash Flow", d.get("Total Cash From Operating Activities")))
        capex = _safe_float(d.get("Capital Expenditure"))
        fcf = None
        if operating_cf is not None and capex is not None:
            fcf = operating_cf + capex  # capex is typically negative in yfinance
        rec = {
            "date": str(col.date()) if hasattr(col, 'date') else str(col)[:10],
            "calendarYear": str(year),
            "operatingCashFlow": operating_cf,
            "capitalExpenditure": capex,
            "freeCashFlow": fcf,
            "dividendsPaid": _safe_float(d.get("Common Stock Dividend Paid", d.get("Cash Dividends Paid"))),
        }
        records.append(rec)
    return records


def _compute_ratios(income_recs, balance_recs, cashflow_recs, info) -> List[Dict[str, Any]]:
    """Compute FMP-like ratio records from statements + yfinance info."""
    ratios = []
    # Build lookup by year
    inc_by_year = {r["calendarYear"]: r for r in income_recs}
    bal_by_year = {r["calendarYear"]: r for r in balance_recs}
    cf_by_year = {r["calendarYear"]: r for r in cashflow_recs}

    for year_str in inc_by_year:
        inc = inc_by_year.get(year_str, {})
        bal = bal_by_year.get(year_str, {})
        cf = cf_by_year.get(year_str, {})
        rev = inc.get("revenue")
        ni = inc.get("netIncome")
        gp = inc.get("grossProfit")
        oi = inc.get("operatingIncome")
        equity = bal.get("totalStockholdersEquity")
        debt = bal.get("totalDebt")

        rec = {
            "date": inc.get("date", ""),
            "calendarYear": year_str,
            "netProfitMargin": (ni / rev) if (ni is not None and rev and rev != 0) else None,
            "grossProfitMargin": (gp / rev) if (gp is not None and rev and rev != 0) else None,
            "operatingProfitMargin": (oi / rev) if (oi is not None and rev and rev != 0) else None,
            "debtToEquityRatio": (debt / equity) if (debt is not None and equity and equity != 0) else None,
            "dividendYield": None,
            "priceToEarningsRatio": None,
            "priceToSalesRatio": None,
            "priceToEarningsGrowthRatio": None,
        }

        ratios.append(rec)

    # Enrich latest year with yfinance info data
    if ratios and info:
        latest = ratios[0]  # yfinance returns most recent first
        if info.get("dividendYield") is not None:
            latest["dividendYield"] = _safe_float(info.get("dividendYield"))
        if info.get("trailingPE") is not None:
            latest["priceToEarningsRatio"] = _safe_float(info.get("trailingPE"))
        if info.get("priceToSalesTrailing12Months") is not None:
            latest["priceToSalesRatio"] = _safe_float(info.get("priceToSalesTrailing12Months"))
        if info.get("pegRatio") is not None:
            latest["priceToEarningsGrowthRatio"] = _safe_float(info.get("pegRatio"))

    return ratios


def fetch_fundamentals(ticker: str) -> Optional[Dict[str, Any]]:
    """Fetch income statement, balance sheet, cash flow, and ratios for one ticker.

    Uses yfinance. Caches result as JSON.
    Returns the cached data dict or None on failure.
    """
    FMP_CACHE_DIR.mkdir(parents=True, exist_ok=True)
    ticker = ticker.upper()

    # Check cache first
    cache_file = FMP_CACHE_DIR / ("%s.json" % ticker)
    if cache_file.exists():
        try:
            return json.loads(cache_file.read_text())
        except Exception:
            pass

    status = _load_status()
    unavailable = set(status.get("unavailable_tickers", []))
    if ticker in unavailable:
        return None

    try:
        t = yf.Ticker(ticker)
        financials = t.financials
        balance = t.balance_sheet
        cashflow = t.cashflow
        info = t.info or {}
    except Exception as e:
        logger.warning("yfinance fetch failed for %s: %s", ticker, e)
        status["errors"][ticker] = str(e)
        _save_status(status)
        return None

    income_recs = _yf_income_to_fmp(financials)
    balance_recs = _yf_balance_to_fmp(balance)
    cashflow_recs = _yf_cashflow_to_fmp(cashflow)

    if not income_recs and not balance_recs:
        if "unavailable_tickers" not in status:
            status["unavailable_tickers"] = []
        if ticker not in status["unavailable_tickers"]:
            status["unavailable_tickers"].append(ticker)
        status["errors"][ticker] = "No financial data available"
        _save_status(status)
        return None

    ratio_recs = _compute_ratios(income_recs, balance_recs, cashflow_recs, info)

    result = {
        "ticker": ticker,
        "fetched_at": datetime.now().isoformat(),
        "income_statement": income_recs,
        "balance_sheet": balance_recs,
        "cash_flow": cashflow_recs,
        "ratios": ratio_recs,
    }

    cache_file.write_text(json.dumps(result, indent=2, default=str))

    if ticker not in status.get("cached_tickers", []):
        if "cached_tickers" not in status:
            status["cached_tickers"] = []
        status["cached_tickers"].append(ticker)
    status["errors"].pop(ticker, None)
    status["calls_today"] = status.get("calls_today", 0) + 1
    status["last_call_date"] = date.today().isoformat()
    _save_status(status)

    logger.info("Cached yfinance data for %s", ticker)
    return result


def get_cached_fundamentals(ticker: str, year: Optional[int] = None) -> Optional[Dict[str, Any]]:
    """Get cached data for a ticker, optionally filtered to a specific fiscal year."""
    cache_file = FMP_CACHE_DIR / ("%s.json" % ticker.upper())
    if not cache_file.exists():
        return None
    try:
        data = json.loads(cache_file.read_text())
    except Exception:
        return None

    if year is None:
        return data

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
    """Extract fiscal year from a record."""
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
    """Reconstruct a yfinance-like info dict from cached data closest to as_of_date.

    Maps fields to the keys expected by score_fundamentals, score_valuation, score_growth.
    """
    data = get_cached_fundamentals(ticker)
    if data is None:
        return None

    as_of_year = int(as_of_date[:4])
    target_year = as_of_year - 1

    income = _find_nearest_year(data.get("income_statement", []), target_year)
    balance = _find_nearest_year(data.get("balance_sheet", []), target_year)
    cashflow = _find_nearest_year(data.get("cash_flow", []), target_year)
    ratios = _find_nearest_year(data.get("ratios", []), target_year)
    prev_income = _find_nearest_year(data.get("income_statement", []), target_year - 1)

    if not income and not ratios:
        return None

    info = {}  # type: Dict[str, Any]

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
            info["debtToEquity"] = dte * 100

    if income and prev_income:
        rev = income.get("revenue")
        prev_rev = prev_income.get("revenue")
        if rev and prev_rev and prev_rev != 0:
            info["revenueGrowth"] = (rev - prev_rev) / abs(prev_rev)

    if income and balance:
        ni = income.get("netIncome")
        equity = balance.get("totalStockholdersEquity")
        if ni is not None and equity and equity != 0:
            info["returnOnEquity"] = ni / abs(equity)

    if cashflow:
        fcf = cashflow.get("freeCashFlow")
        if fcf is not None:
            info["freeCashflow"] = fcf

    if income and prev_income:
        ni = income.get("netIncome")
        prev_ni = prev_income.get("netIncome")
        if ni is not None and prev_ni is not None and prev_ni != 0:
            info["earningsQuarterlyGrowth"] = (ni - prev_ni) / abs(prev_ni)

    return info if info else None


def _find_nearest_year(items: List[Dict[str, Any]], target_year: int) -> Optional[Dict[str, Any]]:
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
    if best_diff <= 1:
        return best
    return None


def fetch_all_fundamentals(tickers: List[str], limit: Optional[int] = None) -> Dict[str, Any]:
    """Batch fetch fundamentals for multiple tickers.

    No rate limits with yfinance — fetches all requested tickers.
    Resumable: skips already-cached tickers.
    """
    status = _load_status()
    cached = set(status.get("cached_tickers", []))
    unavailable = set(status.get("unavailable_tickers", []))
    to_fetch = [t for t in tickers if t.upper() not in cached and t.upper() not in unavailable]

    if limit is not None:
        to_fetch = to_fetch[:limit]

    fetched = 0
    errors = 0

    for ticker in to_fetch:
        result = fetch_fundamentals(ticker)
        if result is not None:
            fetched += 1
        else:
            errors += 1
        time.sleep(0.5)  # be nice

    status = _load_status()
    remaining = len([t for t in tickers if t.upper() not in set(status.get("cached_tickers", []))])

    return {
        "fetched": fetched,
        "errors": errors,
        "already_cached": len(status.get("cached_tickers", [])),
        "remaining": remaining,
        "calls_today": status.get("calls_today", 0),
        "calls_remaining_today": 999,  # no limit with yfinance
    }


def get_fetch_status() -> Dict[str, Any]:
    """Get current fetch status."""
    status = _load_status()
    return {
        "cached_tickers": len(status.get("cached_tickers", [])),
        "cached_list": status.get("cached_tickers", []),
        "unavailable_tickers": len(status.get("unavailable_tickers", [])),
        "calls_today": status.get("calls_today", 0),
        "calls_remaining_today": 999,  # no limit with yfinance
        "last_call_date": status.get("last_call_date", ""),
        "errors": status.get("errors", {}),
    }
