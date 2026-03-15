"""Entry Timing Module — determines optimal entry points for stocks.

Combines multiple technical signals to score entry quality (0-100):
1. RSI oversold detection
2. Support level proximity
3. Distance from moving averages
4. Volume confirmation

High score = good time to buy
Low score = wait for pullback
"""

import logging
from typing import Dict, List, Optional, Tuple
from datetime import datetime, timedelta

import yfinance as yf
import pandas as pd
import numpy as np

from .indicators import _rsi

logger = logging.getLogger(__name__)


def analyze_entry_timing(ticker: str) -> dict:
    """Analyze entry timing for a stock.
    
    Returns comprehensive entry analysis with signals, support levels,
    and composite entry_score (0-100).
    
    Args:
        ticker: Stock ticker symbol
        
    Returns:
        dict with entry_score, rsi, support_levels, ma_distance, volume_signal, recommendation
    """
    try:
        # Fetch 6 months of daily data for analysis
        tk = yf.Ticker(ticker)
        hist = tk.history(period="6mo", interval="1d")
        
        if hist is None or hist.empty or len(hist) < 60:
            return {
                "ticker": ticker,
                "error": "Insufficient data (need 60+ days)",
                "entry_score": 0,
                "recommendation": "INSUFFICIENT_DATA",
            }
        
        current_price = float(hist["Close"].iloc[-1])
        
        # Individual signal scores
        rsi_signal = _analyze_rsi(hist)
        support_signal = _analyze_support_levels(hist, current_price)
        ma_signal = _analyze_ma_distance(hist, current_price)
        volume_signal = _analyze_volume(hist)
        
        # Composite score (weighted average)
        # RSI: 30%, Support: 25%, MA: 25%, Volume: 20%
        entry_score = (
            rsi_signal["score"] * 0.30 +
            support_signal["score"] * 0.25 +
            ma_signal["score"] * 0.25 +
            volume_signal["score"] * 0.20
        )
        
        # Determine recommendation
        if entry_score >= 80:
            recommendation = "EXCELLENT — Buy now"
        elif entry_score >= 60:
            recommendation = "GOOD — Favorable entry"
        elif entry_score >= 40:
            recommendation = "FAIR — Consider waiting"
        else:
            recommendation = "POOR — Wait for pullback"
        
        return {
            "ticker": ticker,
            "current_price": round(current_price, 2),
            "entry_score": round(entry_score, 1),
            "recommendation": recommendation,
            "signals": {
                "rsi": rsi_signal,
                "support": support_signal,
                "ma_distance": ma_signal,
                "volume": volume_signal,
            },
            "timestamp": datetime.now().isoformat(),
        }
        
    except Exception as e:
        logger.error(f"Entry timing analysis failed for {ticker}: {e}")
        return {
            "ticker": ticker,
            "error": str(e),
            "entry_score": 0,
            "recommendation": "ERROR",
        }


def _analyze_rsi(hist: pd.DataFrame) -> dict:
    """Analyze RSI for oversold/overbought conditions.
    
    Score:
    - RSI < 30: 100 (STRONG_BUY zone — oversold)
    - RSI 30-40: 75 (GOOD entry)
    - RSI 40-60: 50 (OK entry)
    - RSI 60-70: 25 (caution)
    - RSI > 70: 0 (WAIT — overbought)
    """
    rsi = _rsi(hist["Close"], period=14)
    
    if rsi is None:
        return {"score": 50, "rsi": None, "signal": "UNKNOWN"}
    
    rsi = round(rsi, 1)
    
    if rsi < 30:
        score = 100
        signal = "STRONG_BUY — oversold, likely bounce"
    elif rsi < 40:
        score = 75
        signal = "GOOD — approaching oversold"
    elif rsi < 60:
        score = 50
        signal = "OK — neutral zone"
    elif rsi < 70:
        score = 25
        signal = "CAUTION — overbought territory"
    else:
        score = 0
        signal = "WAIT — overbought, pullback likely"
    
    return {
        "score": score,
        "rsi": rsi,
        "signal": signal,
    }


def _analyze_support_levels(hist: pd.DataFrame, current_price: float) -> dict:
    """Identify support levels and proximity to current price.
    
    Support levels calculated from:
    - MA20 (20-day moving average)
    - MA50 (50-day moving average)
    - Recent swing lows (local minima in last 60 days)
    - Round number support (e.g., $90, $100, $110)
    
    Score: Higher when price is near support (better entry)
    """
    close = hist["Close"]
    
    # Calculate moving averages
    ma20 = close.rolling(20).mean().iloc[-1]
    ma50 = close.rolling(50).mean().iloc[-1]
    
    support_levels = []
    
    # Add MA supports
    if pd.notna(ma20):
        support_levels.append({
            "level": round(float(ma20), 2),
            "type": "MA20",
            "distance_pct": round(((current_price - ma20) / ma20) * 100, 2),
        })
    
    if pd.notna(ma50):
        support_levels.append({
            "level": round(float(ma50), 2),
            "type": "MA50",
            "distance_pct": round(((current_price - ma50) / ma50) * 100, 2),
        })
    
    # Find swing lows (local minima in last 60 days)
    recent = close.tail(60)
    swing_lows = _find_swing_lows(recent)
    for low in swing_lows[:3]:  # Top 3 swing lows
        support_levels.append({
            "level": round(float(low), 2),
            "type": "SWING_LOW",
            "distance_pct": round(((current_price - low) / low) * 100, 2),
        })
    
    # Round number support
    round_support = _find_round_number_support(current_price)
    if round_support:
        support_levels.append({
            "level": round_support,
            "type": "ROUND_NUMBER",
            "distance_pct": round(((current_price - round_support) / round_support) * 100, 2),
        })
    
    # Score based on proximity to nearest support
    # Best entry when price is 0-2% above support
    if support_levels:
        distances = [abs(s["distance_pct"]) for s in support_levels]
        nearest_distance = min(distances)
        
        if nearest_distance <= 2:
            score = 100  # Right at support
        elif nearest_distance <= 5:
            score = 75   # Near support
        elif nearest_distance <= 10:
            score = 50   # Moderate distance
        else:
            score = 25   # Far from support
    else:
        score = 50
        nearest_distance = None
    
    return {
        "score": score,
        "support_levels": support_levels,
        "nearest_support_distance_pct": nearest_distance,
    }


def _find_swing_lows(series: pd.Series, window: int = 5) -> List[float]:
    """Find local minima (swing lows) in price series.
    
    A swing low is a point where price is lower than surrounding points.
    """
    lows = []
    values = series.values
    
    for i in range(window, len(values) - window):
        is_low = True
        center = values[i]
        
        # Check if center is lower than surrounding points
        for j in range(i - window, i + window + 1):
            if j != i and values[j] < center:
                is_low = False
                break
        
        if is_low:
            lows.append(center)
    
    # Return unique lows, sorted
    return sorted(set(lows))


def _find_round_number_support(price: float) -> Optional[float]:
    """Find nearest round number support level.
    
    Round numbers ($50, $100, $200) often act as psychological support.
    """
    # Determine increment based on price range
    if price < 20:
        increment = 5
    elif price < 100:
        increment = 10
    elif price < 500:
        increment = 50
    else:
        increment = 100
    
    # Find nearest round number below current price
    round_below = (price // increment) * increment
    
    # Only return if it's within 10% of current price
    if round_below > 0 and (price - round_below) / round_below <= 0.10:
        return round_below
    
    return None


def _analyze_ma_distance(hist: pd.DataFrame, current_price: float) -> dict:
    """Analyze distance from moving averages.
    
    Score:
    - Near or below MA20: 100 (good entry)
    - 0-2% above MA20: 75
    - 2-5% above MA20: 50
    - >5% above MA20: 25 (wait for pullback)
    - >10% above MA20: 0 (extended, high risk)
    """
    close = hist["Close"]
    
    ma20 = close.rolling(20).mean().iloc[-1]
    ma50 = close.rolling(50).mean().iloc[-1]
    
    if pd.isna(ma20):
        return {"score": 50, "error": "Insufficient MA data"}
    
    ma20_distance = ((current_price - ma20) / ma20) * 100
    ma50_distance = ((current_price - ma50) / ma50) * 100 if pd.notna(ma50) else None
    
    # Score based on MA20 distance
    if ma20_distance <= 0:
        score = 100  # At or below MA20 — excellent entry
    elif ma20_distance <= 2:
        score = 75   # Slightly above MA20
    elif ma20_distance <= 5:
        score = 50   # Moderate extension
    elif ma20_distance <= 10:
        score = 25   # Extended
    else:
        score = 0    # Very extended, wait for pullback
    
    return {
        "score": score,
        "ma20": round(float(ma20), 2),
        "ma50": round(float(ma50), 2) if pd.notna(ma50) else None,
        "distance_from_ma20_pct": round(ma20_distance, 2),
        "distance_from_ma50_pct": round(ma50_distance, 2) if ma50_distance else None,
    }


def _analyze_volume(hist: pd.DataFrame) -> dict:
    """Analyze volume patterns for entry confirmation.
    
    Signals:
    - High volume + price drop = capitulation (good entry)
    - Low volume + price rise = weak rally (wait)
    - High volume + price rise = strong momentum (good)
    - Low volume + price drop = weak selling (neutral)
    
    Score: Higher for volume patterns that confirm good entry
    """
    volume = hist["Volume"]
    close = hist["Close"]
    
    if len(volume) < 20:
        return {"score": 50, "error": "Insufficient volume data"}
    
    # Current vs average volume
    current_vol = volume.iloc[-1]
    avg_vol_20 = volume.tail(20).mean()
    vol_ratio = current_vol / avg_vol_20 if avg_vol_20 > 0 else 1
    
    # Recent price change (last 5 days)
    price_change = ((close.iloc[-1] - close.iloc[-5]) / close.iloc[-5]) * 100
    
    # Volume signal classification
    high_vol = vol_ratio >= 1.5
    low_vol = vol_ratio < 0.8
    price_up = price_change > 2
    price_down = price_change < -2
    
    if high_vol and price_down:
        score = 100
        signal = "CAPITULATION — high volume selling, possible bottom"
    elif high_vol and price_up:
        score = 75
        signal = "STRONG_MOMENTUM — high volume buying"
    elif low_vol and price_up:
        score = 25
        signal = "WEAK_RALLY — low volume rise, likely to fade"
    elif low_vol and price_down:
        score = 50
        signal = "WEAK_SELLING — low volume drop"
    else:
        score = 50
        signal = "NEUTRAL — average volume"
    
    return {
        "score": score,
        "signal": signal,
        "volume_ratio": round(vol_ratio, 2),
        "avg_volume_20d": int(avg_vol_20),
        "current_volume": int(current_vol),
        "price_change_5d_pct": round(price_change, 2),
    }


def batch_analyze_entries(tickers: List[str]) -> List[dict]:
    """Analyze entry timing for multiple tickers.
    
    Returns list sorted by entry_score (best first).
    """
    results = []
    
    for ticker in tickers:
        try:
            result = analyze_entry_timing(ticker)
            if result.get("entry_score", 0) > 0:
                results.append(result)
        except Exception as e:
            logger.warning(f"Failed to analyze {ticker}: {e}")
    
    # Sort by entry score
    results.sort(key=lambda x: x.get("entry_score", 0), reverse=True)
    
    return results


def format_entry_report(result: dict) -> str:
    """Format entry timing analysis as readable text."""
    ticker = result.get("ticker", "???")
    score = result.get("entry_score", 0)
    rec = result.get("recommendation", "N/A")
    price = result.get("current_price", 0)
    
    if result.get("error"):
        return f"**{ticker}** — Error: {result['error']}"
    
    lines = [
        f"**{ticker}** — ${price:.2f}",
        f"Entry Score: {score:.0f}/100 — {rec}",
        "",
    ]
    
    signals = result.get("signals", {})
    
    # RSI
    rsi = signals.get("rsi", {})
    if rsi.get("rsi"):
        lines.append(f"📊 RSI: {rsi['rsi']:.1f} — {rsi['signal']}")
    
    # MA Distance
    ma = signals.get("ma_distance", {})
    if ma.get("distance_from_ma20_pct") is not None:
        dist = ma["distance_from_ma20_pct"]
        lines.append(f"📈 MA20: ${ma.get('ma20', 0):.2f} ({dist:+.1f}% from current)")
    
    # Support
    support = signals.get("support", {})
    if support.get("support_levels"):
        nearest = support.get("nearest_support_distance_pct")
        if nearest is not None:
            lines.append(f"🛡️ Nearest support: {nearest:.1f}% away")
    
    # Volume
    vol = signals.get("volume", {})
    if vol.get("signal"):
        lines.append(f"📊 Volume: {vol['signal']}")
    
    return "\n".join(lines)
