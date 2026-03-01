"""SEC EDGAR filings data extraction.

Fetches 10-K and 10-Q filings from SEC EDGAR (free, no API key needed).
Extracts key financial data: revenue, net income, EPS, total assets, total debt, cash, FCF.
"""

import json
import logging
import time
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import requests

logger = logging.getLogger(__name__)

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
CACHE_DIR = DATA_DIR / "sec_cache"

# SEC requires a User-Agent header with contact info
SEC_HEADERS = {
    "User-Agent": "StockPicker/1.0 (stockpicker@example.com)",
    "Accept": "application/json",
}

# Common ticker → CIK mappings cache
_cik_cache: Dict[str, str] = {}
_CACHE_TTL = 86400 * 7  # 7 days (filings don't change)


def _get_cik(ticker: str) -> Optional[str]:
    """Look up CIK number for a ticker from SEC's company tickers JSON."""
    ticker = ticker.upper()
    if ticker in _cik_cache:
        return _cik_cache[ticker]

    try:
        # SEC provides a ticker→CIK mapping file
        resp = requests.get(
            "https://www.sec.gov/files/company_tickers.json",
            headers=SEC_HEADERS,
            timeout=10,
        )
        resp.raise_for_status()
        data = resp.json()

        for entry in data.values():
            t = entry.get("ticker", "").upper()
            cik = str(entry.get("cik_str", ""))
            _cik_cache[t] = cik.zfill(10)

        return _cik_cache.get(ticker)
    except Exception as e:
        logger.warning("Failed to fetch CIK mapping: %s", e)
        return None


def _load_filing_cache(ticker: str) -> Optional[dict]:
    """Load cached filing data."""
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    cache_file = CACHE_DIR / f"{ticker.upper()}.json"
    if cache_file.exists():
        age = time.time() - cache_file.stat().st_mtime
        if age < _CACHE_TTL:
            try:
                return json.loads(cache_file.read_text())
            except Exception:
                pass
    return None


def _save_filing_cache(ticker: str, data: dict):
    """Save filing data to cache."""
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    cache_file = CACHE_DIR / f"{ticker.upper()}.json"
    cache_file.write_text(json.dumps(data, indent=2, default=str))


def get_company_filings(ticker: str) -> Optional[dict]:
    """Fetch filing metadata from SEC EDGAR submissions API."""
    cik = _get_cik(ticker)
    if not cik:
        logger.warning("Could not find CIK for %s", ticker)
        return None

    try:
        url = f"https://data.sec.gov/submissions/CIK{cik}.json"
        resp = requests.get(url, headers=SEC_HEADERS, timeout=15)
        resp.raise_for_status()
        return resp.json()
    except Exception as e:
        logger.warning("Failed to fetch filings for %s: %s", ticker, e)
        return None


def get_company_facts(ticker: str) -> Optional[dict]:
    """Fetch XBRL company facts (structured financial data) from SEC EDGAR."""
    cik = _get_cik(ticker)
    if not cik:
        return None

    try:
        url = f"https://data.sec.gov/api/xbrl/companyfacts/CIK{cik}.json"
        resp = requests.get(url, headers=SEC_HEADERS, timeout=15)
        resp.raise_for_status()
        return resp.json()
    except Exception as e:
        logger.warning("Failed to fetch company facts for %s: %s", ticker, e)
        return None


def _extract_fact(facts: dict, taxonomy: str, concept: str, units: str = "USD") -> List[dict]:
    """Extract a specific fact from company facts data."""
    try:
        return facts.get("facts", {}).get(taxonomy, {}).get(concept, {}).get("units", {}).get(units, [])
    except Exception:
        return []


def _get_latest_annual(entries: List[dict]) -> Optional[dict]:
    """Get the most recent 10-K entry from a list of fact entries."""
    annual = [e for e in entries if e.get("form") == "10-K"]
    if not annual:
        return None
    annual.sort(key=lambda x: x.get("end", ""), reverse=True)
    return annual[0]


def _get_latest_quarterly(entries: List[dict]) -> Optional[dict]:
    """Get the most recent 10-Q entry from a list of fact entries."""
    quarterly = [e for e in entries if e.get("form") == "10-Q"]
    if not quarterly:
        return None
    quarterly.sort(key=lambda x: x.get("end", ""), reverse=True)
    return quarterly[0]


def _get_recent_values(entries: List[dict], form: str = "10-K", n: int = 5) -> List[dict]:
    """Get N most recent entries of a given form type."""
    filtered = [e for e in entries if e.get("form") == form]
    filtered.sort(key=lambda x: x.get("end", ""), reverse=True)
    return filtered[:n]


def get_sec_financials(ticker: str) -> dict:
    """Extract structured financial data from SEC EDGAR for a ticker.

    Returns dict with revenue, net_income, eps, total_assets, total_debt, cash, fcf,
    plus historical values for trend analysis.
    """
    ticker = ticker.upper()

    # Check cache first
    cached = _load_filing_cache(ticker)
    if cached:
        return cached

    facts = get_company_facts(ticker)
    if not facts:
        return {"ticker": ticker, "error": "Could not fetch SEC data", "source": "sec_edgar"}

    result = {
        "ticker": ticker,
        "source": "sec_edgar",
        "company_name": facts.get("entityName", ticker),
    }

    # Revenue — try multiple concepts, pick the one with the most recent data
    def _best_revenue_entries(facts):
        candidates = []
        for concept in [
            "Revenues",
            "RevenueFromContractWithCustomerExcludingAssessedTax",
            "RevenueFromContractWithCustomerIncludingAssessedTax",
            "SalesRevenueNet",
        ]:
            entries = _extract_fact(facts, "us-gaap", concept)
            if entries:
                annual = [e for e in entries if e.get("form") == "10-K"]
                if annual:
                    latest_date = max(e.get("end", "") for e in annual)
                    candidates.append((latest_date, entries))
        if not candidates:
            return []
        # Return the concept with the most recent annual filing
        candidates.sort(key=lambda x: x[0], reverse=True)
        return candidates[0][1]

    revenue_entries = _best_revenue_entries(facts)

    if revenue_entries:
        latest = _get_latest_annual(revenue_entries)
        if latest:
            result["revenue_annual"] = latest.get("val")
            result["revenue_period"] = latest.get("end")
        quarterly = _get_latest_quarterly(revenue_entries)
        if quarterly:
            result["revenue_quarterly"] = quarterly.get("val")
            result["revenue_quarterly_period"] = quarterly.get("end")
        # Historical
        result["revenue_history"] = [
            {"period": e.get("end"), "value": e.get("val"), "form": e.get("form")}
            for e in _get_recent_values(revenue_entries, "10-K", 5)
        ]

    # Net Income
    ni_entries = (_extract_fact(facts, "us-gaap", "NetIncomeLoss") or
                  _extract_fact(facts, "us-gaap", "ProfitLoss"))
    if ni_entries:
        latest = _get_latest_annual(ni_entries)
        if latest:
            result["net_income_annual"] = latest.get("val")
            result["net_income_period"] = latest.get("end")
        result["net_income_history"] = [
            {"period": e.get("end"), "value": e.get("val")}
            for e in _get_recent_values(ni_entries, "10-K", 5)
        ]

    # EPS
    eps_entries = _extract_fact(facts, "us-gaap", "EarningsPerShareDiluted", "USD/shares")
    if eps_entries:
        latest = _get_latest_annual(eps_entries)
        if latest:
            result["eps_annual"] = latest.get("val")
        result["eps_history"] = [
            {"period": e.get("end"), "value": e.get("val")}
            for e in _get_recent_values(eps_entries, "10-K", 5)
        ]

    # Total Assets
    assets_entries = _extract_fact(facts, "us-gaap", "Assets")
    if assets_entries:
        latest = _get_latest_annual(assets_entries)
        if latest:
            result["total_assets"] = latest.get("val")

    # Total Debt (LongTermDebt + ShortTermBorrowings, or just LongTermDebt)
    ltd_entries = _extract_fact(facts, "us-gaap", "LongTermDebt")
    std_entries = _extract_fact(facts, "us-gaap", "ShortTermBorrowings")
    total_debt = 0
    if ltd_entries:
        latest = _get_latest_annual(ltd_entries)
        if latest:
            total_debt += latest.get("val", 0)
    if std_entries:
        latest = _get_latest_annual(std_entries)
        if latest:
            total_debt += latest.get("val", 0)
    if total_debt > 0:
        result["total_debt"] = total_debt

    # Cash and Cash Equivalents
    cash_entries = (_extract_fact(facts, "us-gaap", "CashAndCashEquivalentsAtCarryingValue") or
                    _extract_fact(facts, "us-gaap", "Cash"))
    if cash_entries:
        latest = _get_latest_annual(cash_entries)
        if latest:
            result["cash"] = latest.get("val")

    # Free Cash Flow (Operating CF - CapEx)
    ocf_entries = (_extract_fact(facts, "us-gaap", "NetCashProvidedByOperatingActivities") or
                   _extract_fact(facts, "us-gaap", "NetCashProvidedByUsedInOperatingActivities"))
    capex_entries = (_extract_fact(facts, "us-gaap", "PaymentsToAcquirePropertyPlantAndEquipment") or
                     _extract_fact(facts, "us-gaap", "PaymentsForCapitalImprovements"))
    if ocf_entries:
        ocf_latest = _get_latest_annual(ocf_entries)
        capex_latest = _get_latest_annual(capex_entries) if capex_entries else None
        if ocf_latest:
            ocf_val = ocf_latest.get("val", 0)
            capex_val = capex_latest.get("val", 0) if capex_latest else 0
            result["operating_cash_flow"] = ocf_val
            result["capital_expenditures"] = capex_val
            result["free_cash_flow"] = ocf_val - capex_val

        # FCF history
        ocf_hist = _get_recent_values(ocf_entries, "10-K", 5)
        capex_hist = _get_recent_values(capex_entries, "10-K", 5) if capex_entries else []
        capex_by_period = {e.get("end"): e.get("val", 0) for e in capex_hist}
        result["fcf_history"] = [
            {
                "period": e.get("end"),
                "ocf": e.get("val", 0),
                "capex": capex_by_period.get(e.get("end"), 0),
                "fcf": e.get("val", 0) - capex_by_period.get(e.get("end"), 0),
            }
            for e in ocf_hist
        ]

    # Filing info
    filings_data = get_company_filings(ticker)
    if filings_data:
        recent = filings_data.get("filings", {}).get("recent", {})
        forms = recent.get("form", [])
        dates = recent.get("filingDate", [])
        # Find latest 10-K and 10-Q
        for i, form in enumerate(forms):
            if form == "10-K" and "latest_10k_date" not in result:
                result["latest_10k_date"] = dates[i] if i < len(dates) else None
            if form == "10-Q" and "latest_10q_date" not in result:
                result["latest_10q_date"] = dates[i] if i < len(dates) else None
            if "latest_10k_date" in result and "latest_10q_date" in result:
                break

    # Cache result
    _save_filing_cache(ticker, result)
    return result
