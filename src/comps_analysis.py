"""Comparable company (comps) analysis.

Finds same-sector S&P 500 peers and compares valuation/profitability metrics.
"""

import logging
import time
from typing import Dict, List, Optional

import numpy as np
import yfinance as yf

from .universe import get_sp500_tickers

logger = logging.getLogger(__name__)

# Cache peer data to avoid repeated yfinance calls
_peer_cache: Dict[str, tuple] = {}  # ticker -> (timestamp, data)
_CACHE_TTL = 3600 * 4  # 4 hours


COMP_METRICS = [
    "pe_ratio",
    "ps_ratio",
    "ev_ebitda",
    "revenue_growth",
    "profit_margin",
    "roe",
]


def _get_stock_metrics(ticker: str, info: Optional[dict] = None) -> Optional[dict]:
    """Extract comparison metrics for a single stock."""
    now = time.time()
    if ticker in _peer_cache:
        ts, cached = _peer_cache[ticker]
        if now - ts < _CACHE_TTL:
            return cached

    if info is None:
        try:
            t = yf.Ticker(ticker)
            info = t.info or {}
        except Exception:
            return None

    if not info.get("regularMarketPrice") and not info.get("currentPrice"):
        return None

    market_cap = info.get("marketCap", 0) or 0
    enterprise_value = info.get("enterpriseValue", 0) or 0

    metrics = {
        "ticker": ticker,
        "name": info.get("shortName", ticker),
        "sector": info.get("sector", "Unknown"),
        "industry": info.get("industry", "Unknown"),
        "market_cap": market_cap,
        "pe_ratio": info.get("forwardPE") or info.get("trailingPE"),
        "ps_ratio": info.get("priceToSalesTrailing12Months"),
        "ev_ebitda": info.get("enterpriseToEbitda"),
        "revenue_growth": info.get("revenueGrowth"),
        "profit_margin": info.get("profitMargins"),
        "roe": info.get("returnOnEquity"),
        "dividend_yield": info.get("dividendYield", 0) or 0,
        "current_price": info.get("currentPrice") or info.get("regularMarketPrice"),
    }

    _peer_cache[ticker] = (now, metrics)
    return metrics


def _percentile(values: List[float], target: float) -> float:
    """Calculate percentile rank of target in values."""
    if not values:
        return 50.0
    below = sum(1 for v in values if v < target)
    equal = sum(1 for v in values if v == target)
    return round((below + equal * 0.5) / len(values) * 100, 1)


def _safe_median(values: List[float]) -> Optional[float]:
    if not values:
        return None
    return round(float(np.median(values)), 4)


def _safe_mean(values: List[float]) -> Optional[float]:
    if not values:
        return None
    return round(float(np.mean(values)), 4)


def find_peers(ticker: str, max_peers: int = 15) -> List[dict]:
    """Find same-sector peers in S&P 500."""
    ticker = ticker.upper()

    try:
        t = yf.Ticker(ticker)
        info = t.info or {}
    except Exception:
        return []

    target_sector = info.get("sector", "")
    target_industry = info.get("industry", "")
    target_cap = info.get("marketCap", 0) or 0

    if not target_sector:
        return []

    # Load cached stock data if available
    from pathlib import Path
    import json
    data_dir = Path(__file__).resolve().parent.parent / "data"
    cache_file = data_dir / "stock_data_cache.json"

    peers = []
    if cache_file.exists():
        try:
            cached = json.loads(cache_file.read_text())
            for sym, data in cached.items():
                if sym == ticker or sym == "SPY":
                    continue
                peer_info = data.get("info", {})
                if peer_info.get("sector") == target_sector:
                    metrics = _get_stock_metrics(sym, peer_info)
                    if metrics:
                        # Prioritize same industry
                        metrics["_same_industry"] = peer_info.get("industry") == target_industry
                        peers.append(metrics)
        except Exception:
            pass

    # If no cached data, fetch sector peers from yfinance
    if not peers:
        sp500 = get_sp500_tickers(cache_hours=48)
        # Batch fetch - just get info for sector matching
        for sym in sp500[:100]:  # Limit to avoid too many API calls
            if sym == ticker:
                continue
            try:
                peer_t = yf.Ticker(sym)
                peer_info = peer_t.info or {}
                if peer_info.get("sector") == target_sector:
                    metrics = _get_stock_metrics(sym, peer_info)
                    if metrics:
                        metrics["_same_industry"] = peer_info.get("industry") == target_industry
                        peers.append(metrics)
            except Exception:
                continue

    # Sort: same industry first, then by market cap proximity
    peers.sort(key=lambda p: (not p.get("_same_industry", False), abs((p.get("market_cap", 0) or 0) - target_cap)))
    
    # Clean up internal fields
    for p in peers:
        p.pop("_same_industry", None)

    return peers[:max_peers]


def run_comps(ticker: str, max_peers: int = 15) -> dict:
    """Run full comparable company analysis.

    Returns peer group stats, target's percentile rank, and valuation assessment.
    """
    ticker = ticker.upper()

    # Get target metrics
    target = _get_stock_metrics(ticker)
    if not target:
        return {"ticker": ticker, "error": "Could not fetch data for target stock"}

    # Find peers
    peers = find_peers(ticker, max_peers=max_peers)
    if not peers:
        return {"ticker": ticker, "error": "No peers found in same sector", "target": target}

    # Compute peer group stats and target percentile
    metric_analysis = {}
    overall_signals = []

    for metric in COMP_METRICS:
        peer_values = [p[metric] for p in peers if p.get(metric) is not None]
        target_value = target.get(metric)

        analysis = {
            "target_value": round(target_value, 4) if target_value is not None else None,
            "peer_median": _safe_median(peer_values),
            "peer_mean": _safe_mean(peer_values),
            "peer_min": round(min(peer_values), 4) if peer_values else None,
            "peer_max": round(max(peer_values), 4) if peer_values else None,
            "peer_count": len(peer_values),
            "percentile": None,
            "signal": "N/A",
        }

        if target_value is not None and peer_values:
            pct = _percentile(peer_values, target_value)
            analysis["percentile"] = pct

            # Interpret: for valuation metrics (lower = cheaper = better)
            if metric in ("pe_ratio", "ps_ratio", "ev_ebitda"):
                if pct < 25:
                    analysis["signal"] = "CHEAP"
                    overall_signals.append(1)
                elif pct < 50:
                    analysis["signal"] = "BELOW_AVG"
                    overall_signals.append(0.5)
                elif pct > 75:
                    analysis["signal"] = "EXPENSIVE"
                    overall_signals.append(-1)
                else:
                    analysis["signal"] = "ABOVE_AVG"
                    overall_signals.append(-0.5)
            else:
                # For profitability metrics (higher = better)
                if pct > 75:
                    analysis["signal"] = "STRONG"
                    overall_signals.append(1)
                elif pct > 50:
                    analysis["signal"] = "ABOVE_AVG"
                    overall_signals.append(0.5)
                elif pct < 25:
                    analysis["signal"] = "WEAK"
                    overall_signals.append(-1)
                else:
                    analysis["signal"] = "BELOW_AVG"
                    overall_signals.append(-0.5)

        metric_analysis[metric] = analysis

    # Overall assessment
    if overall_signals:
        avg_signal = sum(overall_signals) / len(overall_signals)
        if avg_signal > 0.5:
            verdict = "UNDERVALUED"
        elif avg_signal > 0:
            verdict = "SLIGHTLY_UNDERVALUED"
        elif avg_signal > -0.5:
            verdict = "FAIRLY_VALUED"
        else:
            verdict = "OVERVALUED"
        comps_score = round((avg_signal + 1) / 2 * 100, 1)  # Normalize to 0-100
    else:
        verdict = "INSUFFICIENT_DATA"
        comps_score = 50.0

    # Peer summary
    peer_summary = [{
        "ticker": p["ticker"],
        "name": p.get("name", p["ticker"]),
        "industry": p.get("industry"),
        "market_cap": p.get("market_cap"),
        "pe_ratio": p.get("pe_ratio"),
        "ps_ratio": p.get("ps_ratio"),
        "ev_ebitda": p.get("ev_ebitda"),
        "revenue_growth": p.get("revenue_growth"),
        "profit_margin": p.get("profit_margin"),
        "roe": p.get("roe"),
    } for p in peers]

    return {
        "ticker": ticker,
        "company_name": target.get("name"),
        "sector": target.get("sector"),
        "industry": target.get("industry"),
        "target": target,
        "peers": peer_summary,
        "peer_count": len(peers),
        "metrics": metric_analysis,
        "comps_score": comps_score,
        "verdict": verdict,
    }
