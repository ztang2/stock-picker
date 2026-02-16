"""Sell signal logic: exit triggers for existing positions."""

import logging
from typing import Optional, List, Dict

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)


def _rsi(series: pd.Series, period: int = 14) -> Optional[float]:
    """RSI calculation (duplicated for modularity)."""
    if series is None or len(series) < period + 1:
        return None
    delta = series.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.rolling(period).mean()
    avg_loss = loss.rolling(period).mean()
    rs = avg_gain / avg_loss
    rsi = 100 - (100 / (1 + rs))
    val = rsi.iloc[-1]
    return None if pd.isna(val) else float(val)


def _macd_crossover(close: pd.Series) -> Optional[Dict[str, float]]:
    """Detect MACD bearish crossover (MACD crossing below signal)."""
    if close is None or len(close) < 35:
        return None
    try:
        ema12 = close.ewm(span=12).mean()
        ema26 = close.ewm(span=26).mean()
        macd = ema12 - ema26
        signal = macd.ewm(span=9).mean()
        
        # Current and previous values
        macd_curr = float(macd.iloc[-1])
        macd_prev = float(macd.iloc[-2])
        signal_curr = float(signal.iloc[-1])
        signal_prev = float(signal.iloc[-2])
        
        # Bearish crossover: MACD was above signal, now below
        bearish_crossover = (macd_prev > signal_prev) and (macd_curr < signal_curr)
        
        return {
            "macd": round(macd_curr, 4),
            "signal": round(signal_curr, 4),
            "histogram": round(macd_curr - signal_curr, 4),
            "bearish_crossover": bool(bearish_crossover),
        }
    except Exception:
        return None


def _check_ma_breakdown(hist: pd.DataFrame) -> Dict[str, bool]:
    """Check if price dropped below key moving averages."""
    if hist is None or len(hist) < 50:
        return {"below_ma50": False, "below_ma200": False}
    
    try:
        close = hist["Close"]
        current = float(close.iloc[-1])
        
        ma50 = close.rolling(50).mean().iloc[-1]
        ma50_prev = close.rolling(50).mean().iloc[-2]
        
        below_ma50 = False
        if not pd.isna(ma50) and not pd.isna(ma50_prev):
            # Price crossed below MA50
            prev_price = float(close.iloc[-2])
            below_ma50 = (prev_price >= ma50_prev) and (current < ma50)
        
        below_ma200 = False
        if len(close) >= 200:
            ma200 = close.rolling(200).mean().iloc[-1]
            ma200_prev = close.rolling(200).mean().iloc[-2]
            if not pd.isna(ma200) and not pd.isna(ma200_prev):
                prev_price = float(close.iloc[-2])
                below_ma200 = (prev_price >= ma200_prev) and (current < ma200)
        
        return {
            "below_ma50": bool(below_ma50),
            "below_ma200": bool(below_ma200),
            "current_price": round(current, 2),
            "ma50": round(float(ma50), 2) if not pd.isna(ma50) else None,
            "ma200": round(float(ma200), 2) if len(close) >= 200 and not pd.isna(ma200) else None,
        }
    except Exception:
        return {"below_ma50": False, "below_ma200": False}


def _check_stop_loss(
    current_price: float,
    entry_price: Optional[float] = None,
    stop_loss_pct: float = -15.0
) -> Dict[str, Optional[float]]:
    """Check if stop-loss threshold is triggered.
    
    Args:
        current_price: Current stock price
        entry_price: Entry price (if None, no stop-loss check)
        stop_loss_pct: Stop-loss percentage (default -15%)
    
    Returns:
        Dict with stop_loss_triggered, loss_pct, entry_price
    """
    if entry_price is None or entry_price <= 0:
        return {
            "stop_loss_triggered": False,
            "loss_pct": None,
            "entry_price": None,
            "threshold_pct": stop_loss_pct,
        }
    
    loss_pct = ((current_price - entry_price) / entry_price) * 100
    triggered = loss_pct <= stop_loss_pct
    
    return {
        "stop_loss_triggered": bool(triggered),
        "loss_pct": round(float(loss_pct), 2),
        "entry_price": round(float(entry_price), 2),
        "threshold_pct": stop_loss_pct,
    }


def compute_sell_signals(
    hist: pd.DataFrame,
    fundamentals_score: Optional[float] = None,
    prev_fundamentals_score: Optional[float] = None,
    current_signal: Optional[str] = None,
    prev_signal: Optional[str] = None,
    resistance: Optional[float] = None,
    valuation_score: Optional[float] = None,
    risk_score: Optional[float] = None,
    entry_price: Optional[float] = None,
    stop_loss_pct: float = -15.0,
    adx: Optional[float] = None,
    regime: Optional[str] = None,
) -> dict:
    """Compute sell/exit signals for a stock.
    
    Args:
        hist: DataFrame with OHLCV data (standard yfinance format)
        fundamentals_score: Current fundamentals score (0-100)
        prev_fundamentals_score: Previous fundamentals score
        current_signal: Current entry signal (STRONG_BUY, BUY, HOLD, WAIT)
        prev_signal: Previous entry signal
        resistance: Resistance level from momentum analysis
        valuation_score: Valuation score (0-100)
        risk_score: Risk score (0-100)
        entry_price: Entry price for stop-loss calculation
        stop_loss_pct: Stop-loss threshold (default -15%)
        adx: ADX value for trend strength detection
        regime: Market regime ("bull", "bear", "sideways") for threshold adjustments
    
    Returns:
        dict with sell_signal, sell_reasons, urgency, and detailed metrics
    """
    result = {
        "sell_signal": "N/A",
        "sell_reasons": [],
        "urgency": "none",
        "rsi_overbought": False,
        "near_resistance": False,
        "signal_downgrade": False,
        "fundamental_deterioration": False,
        "stop_loss_triggered": False,
        "macd_bearish": False,
        "ma_breakdown": False,
    }
    
    if hist is None or len(hist) < 50:
        result["sell_reasons"] = ["Insufficient data"]
        return result
    
    close = hist["Close"]
    current_price = float(close.iloc[-1])
    
    reasons = []  # type: List[str]
    sell_score = 0  # Accumulate negative signals (higher = stronger sell)
    
    # 1. RSI overbought (>70 = warning, >80 = strong sell)
    # Strong trends can sustain high RSI longer — adjust thresholds when ADX > 40
    # Market regime also adjusts thresholds: bull +5, bear -5, sideways 0
    rsi = _rsi(close)
    if rsi is not None:
        # Calculate MA50 for trend context
        ma50 = None
        if len(close) >= 50:
            ma50 = close.rolling(50).mean().iloc[-1]
        
        # Determine if we're in a strong uptrend
        strong_trend = adx is not None and adx > 40
        above_ma50_pct = None
        if ma50 is not None and not pd.isna(ma50):
            above_ma50_pct = ((current_price - ma50) / ma50) * 100
        
        # Base thresholds
        rsi_threshold_warning = 80 if strong_trend else 70
        rsi_threshold_strong = 85 if strong_trend else 80
        
        # Adjust thresholds based on market regime
        regime_offset = 0
        if regime == "bull":
            regime_offset = 5  # More lenient in bull markets
        elif regime == "bear":
            regime_offset = -5  # More strict in bear markets
        
        rsi_threshold_warning += regime_offset
        rsi_threshold_strong += regime_offset
        
        rsi_sell_score = 0
        if rsi > rsi_threshold_strong:
            rsi_sell_score = 25
            reasons.append(f"RSI extremely overbought ({rsi:.1f})")
            result["rsi_overbought"] = True
        elif rsi > rsi_threshold_warning:
            rsi_sell_score = 15
            reasons.append(f"RSI overbought ({rsi:.1f})")
            result["rsi_overbought"] = True
        
        # In strong uptrend (ADX > 40) with price >10% above MA50, discount RSI sell score by 50%
        if strong_trend and above_ma50_pct is not None and above_ma50_pct > 10:
            rsi_sell_score = rsi_sell_score * 0.5
            if rsi_sell_score > 0:
                reasons.append("(RSI discounted: strong uptrend)")
        
        sell_score += rsi_sell_score
    
    # 2. Price at/near resistance
    if resistance is not None and resistance > 0:
        distance_pct = ((resistance - current_price) / current_price) * 100
        if distance_pct <= 2.0 and distance_pct >= -2.0:
            sell_score += 12
            reasons.append(f"Price near resistance (${resistance:.2f}, {distance_pct:+.1f}%)")
            result["near_resistance"] = True
    
    # 3. Signal downgrade (BUY → WAIT or STRONG_BUY → HOLD/WAIT)
    if current_signal and prev_signal:
        signal_order = {"STRONG_BUY": 3, "BUY": 2, "HOLD": 1, "WAIT": 0}
        curr_level = signal_order.get(current_signal, 1)
        prev_level = signal_order.get(prev_signal, 1)
        
        if prev_level > curr_level:
            downgrade_magnitude = prev_level - curr_level
            sell_score += 10 * downgrade_magnitude
            reasons.append(f"Signal downgraded from {prev_signal} to {current_signal}")
            result["signal_downgrade"] = True
    
    # 4a. Fundamental deterioration (score drop > 15 points)
    if fundamentals_score is not None and prev_fundamentals_score is not None:
        score_drop = prev_fundamentals_score - fundamentals_score
        if score_drop > 15:
            sell_score += 18
            reasons.append(f"Fundamentals deteriorated ({score_drop:.1f} point drop)")
            result["fundamental_deterioration"] = True
        elif score_drop > 10:
            sell_score += 10
            reasons.append(f"Fundamentals weakening ({score_drop:.1f} point drop)")
            result["fundamental_deterioration"] = True

    # 4b. Fundamentals too weak (absolute floor check)
    if fundamentals_score is not None and fundamentals_score < 40:
        sell_score += 15
        reasons.append(f"Weak fundamentals (score {fundamentals_score:.1f})")
        result["fundamental_deterioration"] = True

    # 4c. Valuation score at zero (unprofitable / extremely overvalued)
    if valuation_score is not None and valuation_score <= 0:
        sell_score += 12
        reasons.append("Valuation score 0 (negative earnings or extreme overvaluation)")

    # 4d. Risk score at zero (extreme volatility / drawdown)
    if risk_score is not None and risk_score <= 0:
        sell_score += 12
        reasons.append("Risk score 0 (extreme volatility/drawdown)")
    
    # 5. Stop-loss threshold
    stop_loss_info = _check_stop_loss(current_price, entry_price, stop_loss_pct)
    result["stop_loss_info"] = stop_loss_info
    if stop_loss_info["stop_loss_triggered"]:
        sell_score += 30
        reasons.append(f"Stop-loss triggered ({stop_loss_info['loss_pct']:.1f}% loss)")
        result["stop_loss_triggered"] = True
    
    # 6. MACD bearish crossover
    macd_data = _macd_crossover(close)
    result["macd"] = macd_data
    if macd_data and macd_data["bearish_crossover"]:
        sell_score += 15
        reasons.append("MACD bearish crossover")
        result["macd_bearish"] = True
    
    # 7. Price drops below key moving averages
    ma_breakdown = _check_ma_breakdown(hist)
    result["ma_breakdown_info"] = ma_breakdown
    if ma_breakdown.get("below_ma200"):
        sell_score += 20
        reasons.append(f"Price dropped below MA200 (${ma_breakdown.get('ma200', 0):.2f})")
        result["ma_breakdown"] = True
    elif ma_breakdown.get("below_ma50"):
        sell_score += 12
        reasons.append(f"Price dropped below MA50 (${ma_breakdown.get('ma50', 0):.2f})")
        result["ma_breakdown"] = True
    
    # Apply regime-based sell score multiplier
    regime_multiplier = 1.0
    if regime == "bull":
        regime_multiplier = 0.80  # Reduce sell score by 20% in bull markets
    elif regime == "bear":
        regime_multiplier = 1.30  # Increase sell score by 30% in bear markets
    
    sell_score = sell_score * regime_multiplier
    
    # Determine sell signal based on score
    # STRONG_SELL: 40+, SELL: 25+, HOLD: 15+, N/A: <15
    if sell_score >= 40:
        result["sell_signal"] = "STRONG_SELL"
        result["urgency"] = "high"
    elif sell_score >= 25:
        result["sell_signal"] = "SELL"
        result["urgency"] = "medium"
    elif sell_score >= 15:
        result["sell_signal"] = "HOLD"
        result["urgency"] = "low"
    else:
        result["sell_signal"] = "N/A"
        result["urgency"] = "none"
    
    result["sell_score"] = sell_score
    result["sell_reasons"] = reasons if reasons else ["No significant sell signals"]
    result["current_price"] = round(current_price, 2)
    result["rsi"] = round(rsi, 2) if rsi is not None else None
    
    return result
