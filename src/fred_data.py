"""FRED economic data integration for macro regime analysis.

Key series tracked:
- CPIAUCSL: Consumer Price Index (inflation)
- UNRATE: Unemployment Rate
- GDP: Gross Domestic Product
- FEDFUNDS: Federal Funds Rate
- T10Y2Y: 10Y-2Y Treasury Spread (yield curve, recession indicator)
- ICSA: Initial Jobless Claims (weekly)

Requires FRED API key in .env (FRED_API_KEY).
Falls back to cached data if API unavailable.
"""

import json
import logging
import os
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, Optional

logger = logging.getLogger(__name__)

DATA_DIR = Path(__file__).parent.parent / "data"
FRED_CACHE_FILE = DATA_DIR / "fred_cache.json"

# Key economic series
FRED_SERIES = {
    "cpi": {
        "id": "CPIAUCSL",
        "name": "CPI (Inflation)",
        "frequency": "monthly",
        "impact": "Rising CPI → inflation → bad for growth stocks, good for commodities",
    },
    "unemployment": {
        "id": "UNRATE",
        "name": "Unemployment Rate",
        "frequency": "monthly",
        "impact": "Rising unemployment → economic slowdown → defensive stocks outperform",
    },
    "fed_rate": {
        "id": "FEDFUNDS",
        "name": "Federal Funds Rate",
        "frequency": "monthly",
        "impact": "Higher rates → pressure on valuations, good for financials/banks",
    },
    "yield_curve": {
        "id": "T10Y2Y",
        "name": "10Y-2Y Spread (Yield Curve)",
        "frequency": "daily",
        "impact": "Negative spread → recession signal, historically very reliable",
    },
    "jobless_claims": {
        "id": "ICSA",
        "name": "Initial Jobless Claims",
        "frequency": "weekly",
        "impact": "Rising claims → labor market weakening → bearish signal",
    },
    "gdp_growth": {
        "id": "A191RL1Q225SBEA",
        "name": "Real GDP Growth Rate",
        "frequency": "quarterly",
        "impact": "Negative GDP → recession, positive → expansion",
    },
}


def _load_cache() -> dict:
    if FRED_CACHE_FILE.exists():
        try:
            return json.loads(FRED_CACHE_FILE.read_text())
        except Exception:
            pass
    return {}


def _save_cache(data: dict):
    FRED_CACHE_FILE.write_text(json.dumps(data, indent=2, default=str))


def fetch_fred_data(force_refresh: bool = False) -> Dict:
    """Fetch economic data from FRED API.
    
    Returns dict with each series' latest value, trend, and signal.
    Caches results for 6 hours (most data is monthly/weekly anyway).
    """
    cache = _load_cache()
    
    # Check cache freshness (6 hours)
    cache_time = cache.get("_timestamp")
    if cache_time and not force_refresh:
        try:
            cached_at = datetime.fromisoformat(cache_time)
            if datetime.now() - cached_at < timedelta(hours=6):
                logger.info("Using cached FRED data (%.1f hours old)", 
                           (datetime.now() - cached_at).total_seconds() / 3600)
                return cache
        except Exception:
            pass
    
    api_key = os.getenv("FRED_API_KEY", "")
    if not api_key:
        # Try .env file
        env_file = Path(__file__).parent.parent / ".env"
        if env_file.exists():
            for line in env_file.read_text().splitlines():
                if line.startswith("FRED_API_KEY="):
                    api_key = line.split("=", 1)[1].strip().strip('"').strip("'")
                    break
    
    if not api_key:
        logger.warning("No FRED_API_KEY found. Using cached data if available.")
        if cache:
            return cache
        return {"error": "No FRED API key configured. Get one free at https://fred.stlouisfed.org/docs/api/api_key.html"}
    
    try:
        from fredapi import Fred
        fred = Fred(api_key=api_key)
    except ImportError:
        logger.error("fredapi not installed. Run: pip install fredapi")
        return cache or {"error": "fredapi not installed"}
    
    results = {"_timestamp": datetime.now().isoformat()}
    
    for key, series_info in FRED_SERIES.items():
        try:
            # Fetch last 2 years of data
            data = fred.get_series(
                series_info["id"],
                observation_start=(datetime.now() - timedelta(days=730)).strftime("%Y-%m-%d"),
            )
            
            if data is None or len(data) == 0:
                continue
            
            # Drop NaN
            data = data.dropna()
            if len(data) == 0:
                continue
            
            current = float(data.iloc[-1])
            
            # Calculate trends
            if len(data) >= 2:
                prev = float(data.iloc[-2])
                mom_change = current - prev
                mom_change_pct = (mom_change / abs(prev) * 100) if prev != 0 else 0
            else:
                mom_change = 0
                mom_change_pct = 0
            
            # Year-over-year change
            if len(data) >= 13 and series_info["frequency"] == "monthly":
                yoy_prev = float(data.iloc[-13])
                yoy_change_pct = ((current - yoy_prev) / abs(yoy_prev) * 100) if yoy_prev != 0 else 0
            elif len(data) >= 53 and series_info["frequency"] == "weekly":
                yoy_prev = float(data.iloc[-53])
                yoy_change_pct = ((current - yoy_prev) / abs(yoy_prev) * 100) if yoy_prev != 0 else 0
            else:
                yoy_change_pct = 0
            
            # Generate signal
            signal = _score_economic_signal(key, current, mom_change, mom_change_pct, yoy_change_pct)
            
            results[key] = {
                "name": series_info["name"],
                "series_id": series_info["id"],
                "current": round(current, 2),
                "previous": round(prev, 2) if len(data) >= 2 else None,
                "mom_change": round(mom_change, 2),
                "mom_change_pct": round(mom_change_pct, 2),
                "yoy_change_pct": round(yoy_change_pct, 2),
                "last_date": str(data.index[-1].date()),
                "signal": signal,
                "impact": series_info["impact"],
            }
            
        except Exception as e:
            logger.warning("Failed to fetch FRED series %s: %s", key, e)
    
    _save_cache(results)
    return results


def _score_economic_signal(key: str, current: float, mom_change: float,
                           mom_change_pct: float, yoy_change_pct: float) -> Dict:
    """Score an economic indicator and return signal dict."""
    
    if key == "cpi":
        # CPI: YoY > 4% = high inflation (bearish), < 2% = low (bullish)
        if yoy_change_pct > 4:
            return {"direction": "bearish", "score": -2, "note": f"CPI YoY +{yoy_change_pct:.1f}% — high inflation"}
        elif yoy_change_pct > 3:
            return {"direction": "bearish", "score": -1, "note": f"CPI YoY +{yoy_change_pct:.1f}% — above target"}
        elif yoy_change_pct < 2:
            return {"direction": "bullish", "score": 1, "note": f"CPI YoY +{yoy_change_pct:.1f}% — below target"}
        else:
            return {"direction": "neutral", "score": 0, "note": f"CPI YoY +{yoy_change_pct:.1f}% — near target"}
    
    elif key == "unemployment":
        # Unemployment: > 5% = weak economy, < 4% = strong
        if current > 6:
            return {"direction": "bearish", "score": -2, "note": f"Unemployment {current:.1f}% — recession territory"}
        elif current > 5:
            return {"direction": "bearish", "score": -1, "note": f"Unemployment {current:.1f}% — elevated"}
        elif current < 4:
            return {"direction": "bullish", "score": 1, "note": f"Unemployment {current:.1f}% — strong labor market"}
        else:
            return {"direction": "neutral", "score": 0, "note": f"Unemployment {current:.1f}% — moderate"}
    
    elif key == "fed_rate":
        # Fed rate: > 5% = restrictive, < 2% = accommodative
        if current > 5:
            return {"direction": "bearish", "score": -2, "note": f"Fed rate {current:.2f}% — restrictive"}
        elif current > 4:
            return {"direction": "bearish", "score": -1, "note": f"Fed rate {current:.2f}% — tight"}
        elif current < 2:
            return {"direction": "bullish", "score": 1, "note": f"Fed rate {current:.2f}% — accommodative"}
        else:
            return {"direction": "neutral", "score": 0, "note": f"Fed rate {current:.2f}% — moderate"}
    
    elif key == "yield_curve":
        # Yield curve: negative = recession signal (very reliable)
        if current < -0.5:
            return {"direction": "bearish", "score": -3, "note": f"Yield curve {current:+.2f}% — DEEPLY INVERTED, recession warning"}
        elif current < 0:
            return {"direction": "bearish", "score": -2, "note": f"Yield curve {current:+.2f}% — inverted, recession risk"}
        elif current < 0.5:
            return {"direction": "neutral", "score": 0, "note": f"Yield curve {current:+.2f}% — flat"}
        else:
            return {"direction": "bullish", "score": 1, "note": f"Yield curve {current:+.2f}% — normal, healthy"}
    
    elif key == "jobless_claims":
        # Weekly claims: > 300K = concerning, < 200K = very strong
        current_k = current / 1000
        if current > 350000:
            return {"direction": "bearish", "score": -2, "note": f"Jobless claims {current_k:.0f}K — alarming"}
        elif current > 250000:
            return {"direction": "bearish", "score": -1, "note": f"Jobless claims {current_k:.0f}K — rising"}
        elif current < 200000:
            return {"direction": "bullish", "score": 1, "note": f"Jobless claims {current_k:.0f}K — very strong"}
        else:
            return {"direction": "neutral", "score": 0, "note": f"Jobless claims {current_k:.0f}K — normal"}
    
    elif key == "gdp_growth":
        if current < 0:
            return {"direction": "bearish", "score": -2, "note": f"GDP {current:+.1f}% — contraction"}
        elif current < 1:
            return {"direction": "bearish", "score": -1, "note": f"GDP {current:+.1f}% — stagnation"}
        elif current > 3:
            return {"direction": "bullish", "score": 1, "note": f"GDP {current:+.1f}% — strong growth"}
        else:
            return {"direction": "neutral", "score": 0, "note": f"GDP {current:+.1f}% — moderate growth"}
    
    return {"direction": "neutral", "score": 0, "note": "Unknown indicator"}


def get_economic_summary() -> Dict:
    """Get a summary of economic conditions with composite score."""
    data = fetch_fred_data()
    
    if "error" in data:
        return data
    
    scores = {}
    total_score = 0
    notes = []
    
    for key in FRED_SERIES:
        if key in data and "signal" in data[key]:
            sig = data[key]["signal"]
            scores[key] = sig["score"]
            total_score += sig["score"]
            notes.append(sig["note"])
    
    # Economic regime
    if total_score >= 3:
        regime = "expansion"
    elif total_score <= -3:
        regime = "contraction"
    else:
        regime = "mixed"
    
    return {
        "regime": regime,
        "composite_score": total_score,
        "scores": scores,
        "notes": notes,
        "data": {k: v for k, v in data.items() if k != "_timestamp"},
        "timestamp": data.get("_timestamp"),
    }
