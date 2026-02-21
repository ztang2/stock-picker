"""Market regime detection based on S&P 500 (SPY) indicators."""

import logging
from typing import Optional, Dict

import numpy as np
import pandas as pd

from .indicators import _rsi

logger = logging.getLogger(__name__)


def _ma_slope(series: pd.Series, period: int, lookback: int = 20) -> Optional[float]:
    """Calculate the slope of a moving average over lookback periods.
    
    Returns slope as percentage change per period.
    """
    if series is None or len(series) < period + lookback:
        return None
    
    ma = series.rolling(period).mean()
    if len(ma) < lookback:
        return None
    
    # Get MA values from lookback periods ago and current
    ma_prev = ma.iloc[-(lookback + 1)]
    ma_curr = ma.iloc[-1]
    
    if pd.isna(ma_prev) or pd.isna(ma_curr) or ma_prev == 0:
        return None
    
    # Calculate percentage change per period
    pct_change = ((ma_curr - ma_prev) / ma_prev) * 100
    slope = pct_change / lookback
    
    return float(slope)


def detect_market_regime(spy_hist: pd.DataFrame) -> Dict:
    """Detect current market regime based on SPY indicators.
    
    Regime Logic:
    - Bull: SPY > 200MA AND 200MA slope positive
    - Bear: SPY < 200MA AND 200MA slope negative
    - Sideways: SPY near 200MA (within 3%) OR 200MA slope flat
    
    Args:
        spy_hist: DataFrame with SPY OHLCV data
    
    Returns:
        Dict with regime, spy_price, spy_ma200, spy_ma50, spy_rsi, 
        confidence (0-1), description
    """
    result = {
        "regime": "sideways",
        "spy_price": None,
        "spy_ma200": None,
        "spy_ma50": None,
        "spy_rsi": None,
        "ma200_slope": None,
        "ma50_slope": None,
        "confidence": 0.5,
        "description": "Insufficient data for regime detection",
        "signals": {},
    }
    
    if spy_hist is None or len(spy_hist) < 200:
        logger.warning("Insufficient SPY data for regime detection")
        return result
    
    try:
        close = spy_hist["Close"]
        current_price = float(close.iloc[-1])
        
        # Calculate moving averages
        ma50 = close.rolling(50).mean().iloc[-1]
        ma200 = close.rolling(200).mean().iloc[-1]
        
        if pd.isna(ma50) or pd.isna(ma200):
            logger.warning("Unable to calculate SPY moving averages")
            return result
        
        ma50 = float(ma50)
        ma200 = float(ma200)
        
        # Calculate RSI
        rsi = _rsi(close)
        
        # Calculate MA slopes (20-day lookback for smoothing)
        ma200_slope = _ma_slope(close, 200, lookback=20)
        ma50_slope = _ma_slope(close, 50, lookback=20)
        
        # Distance from 200MA (percentage)
        distance_200ma_pct = ((current_price - ma200) / ma200) * 100
        distance_50ma_pct = ((current_price - ma50) / ma50) * 100
        
        # Initialize signals dict for confidence calculation
        signals = {
            "above_ma200": current_price > ma200,
            "above_ma50": current_price > ma50,
            "ma200_slope_positive": ma200_slope is not None and ma200_slope > 0.01,
            "ma200_slope_negative": ma200_slope is not None and ma200_slope < -0.01,
            "ma200_slope_flat": ma200_slope is not None and abs(ma200_slope) <= 0.01,
            "near_ma200": abs(distance_200ma_pct) <= 3.0,
            "rsi_bullish": rsi is not None and rsi > 50,
            "rsi_bearish": rsi is not None and rsi < 50,
        }
        
        # Determine regime
        regime = "sideways"  # default
        confidence = 0.5
        bullish_signals = 0
        bearish_signals = 0
        
        # Bull market criteria: Above 200MA AND 200MA trending up
        if signals["above_ma200"] and signals["ma200_slope_positive"]:
            regime = "bull"
            bullish_signals += 2  # Primary criteria
            
            # Additional confirmatory signals
            if signals["above_ma50"]:
                bullish_signals += 1
            if signals["rsi_bullish"]:
                bullish_signals += 1
            if distance_200ma_pct > 5:  # Significantly above 200MA
                bullish_signals += 1
            
            confidence = min(0.95, 0.6 + (bullish_signals * 0.1))
        
        # Bear market criteria: Below 200MA AND 200MA trending down
        elif not signals["above_ma200"] and signals["ma200_slope_negative"]:
            regime = "bear"
            bearish_signals += 2  # Primary criteria
            
            # Additional confirmatory signals
            if not signals["above_ma50"]:
                bearish_signals += 1
            if signals["rsi_bearish"]:
                bearish_signals += 1
            if distance_200ma_pct < -5:  # Significantly below 200MA
                bearish_signals += 1
            
            confidence = min(0.95, 0.6 + (bearish_signals * 0.1))
        
        # Sideways: Near 200MA OR 200MA slope flat
        else:
            regime = "sideways"
            
            # Higher confidence if clearly in sideways range
            if signals["near_ma200"] or signals["ma200_slope_flat"]:
                confidence = 0.7
            else:
                # Mixed signals, lower confidence
                confidence = 0.5
        
        # Generate description
        description = f"SPY ${current_price:.2f} "
        if regime == "bull":
            description += f"is {distance_200ma_pct:.1f}% above 200MA (${ma200:.2f}), trending up. "
            description += f"Bull market detected."
        elif regime == "bear":
            description += f"is {abs(distance_200ma_pct):.1f}% below 200MA (${ma200:.2f}), trending down. "
            description += f"Bear market detected."
        else:
            if signals["near_ma200"]:
                description += f"is near 200MA (${ma200:.2f}, {distance_200ma_pct:+.1f}%). "
            else:
                description += f"200MA slope is flat. "
            description += f"Sideways market detected."
        
        result = {
            "regime": regime,
            "spy_price": round(current_price, 2),
            "spy_ma200": round(ma200, 2),
            "spy_ma50": round(ma50, 2),
            "spy_rsi": round(rsi, 2) if rsi is not None else None,
            "ma200_slope": round(ma200_slope, 4) if ma200_slope is not None else None,
            "ma50_slope": round(ma50_slope, 4) if ma50_slope is not None else None,
            "distance_200ma_pct": round(distance_200ma_pct, 2),
            "distance_50ma_pct": round(distance_50ma_pct, 2),
            "confidence": round(confidence, 2),
            "description": description,
            "signals": signals,
        }
        
        logger.info(f"Market regime: {regime.upper()} (confidence: {confidence:.0%}) - {description}")
        
    except Exception:
        logger.error("Failed to detect market regime", exc_info=True)
    
    return result


def get_regime_weight_adjustments(regime: str) -> Dict[str, float]:
    """Get weight adjustment multipliers for a given market regime.
    
    Returns multipliers to apply to base strategy weights.
    
    Args:
        regime: "bull", "bear", or "sideways"
    
    Returns:
        Dict with multipliers for each scoring category
    """
    if regime == "bull":
        return {
            "fundamentals": 1.0,
            "valuation": 0.95,  # -5%
            "technicals": 1.05,  # +5%
            "risk": 0.95,  # -5%
            "growth": 1.05,  # +5%
            "sentiment": 1.0,
            "sector_relative": 1.0,
        }
    elif regime == "bear":
        return {
            "fundamentals": 1.0,
            "valuation": 1.05,  # +5%
            "technicals": 0.95,  # -5%
            "risk": 1.10,  # +10%
            "growth": 0.90,  # -10%
            "sentiment": 1.0,
            "sector_relative": 1.0,
        }
    else:  # sideways
        return {
            "fundamentals": 1.0,
            "valuation": 1.0,
            "technicals": 1.0,
            "risk": 1.0,
            "growth": 1.0,
            "sentiment": 1.0,
            "sector_relative": 1.0,
        }


def get_regime_sell_adjustments(regime: str) -> Dict:
    """Get sell signal threshold adjustments for a given market regime.
    
    Args:
        regime: "bull", "bear", or "sideways"
    
    Returns:
        Dict with rsi_threshold_offset, sell_score_multiplier
    """
    if regime == "bull":
        return {
            "rsi_threshold_offset": 5,  # 70→75, 80→85
            "sell_score_multiplier": 0.80,  # Reduce sell score by 20%
        }
    elif regime == "bear":
        return {
            "rsi_threshold_offset": -5,  # 70→65, 80→75
            "sell_score_multiplier": 1.30,  # Increase sell score by 30%
        }
    else:  # sideways
        return {
            "rsi_threshold_offset": 0,
            "sell_score_multiplier": 1.0,
        }
