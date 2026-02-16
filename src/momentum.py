"""Momentum scoring and entry timing signals."""

import logging
from typing import Optional, Dict, List, Tuple

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)


def _adx(hist: pd.DataFrame, period: int = 14) -> Optional[float]:
    """Compute Average Directional Index."""
    if hist is None or len(hist) < period * 2:
        return None
    try:
        high = hist["High"]
        low = hist["Low"]
        close = hist["Close"]
        plus_dm = high.diff()
        minus_dm = -low.diff()
        plus_dm = plus_dm.where((plus_dm > minus_dm) & (plus_dm > 0), 0.0)
        minus_dm = minus_dm.where((minus_dm > plus_dm) & (minus_dm > 0), 0.0)
        tr1 = high - low
        tr2 = (high - close.shift(1)).abs()
        tr3 = (low - close.shift(1)).abs()
        tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
        atr = tr.rolling(period).mean()
        plus_di = 100 * (plus_dm.rolling(period).mean() / atr)
        minus_di = 100 * (minus_dm.rolling(period).mean() / atr)
        dx = (plus_di - minus_di).abs() / (plus_di + minus_di) * 100
        adx_val = dx.rolling(period).mean().iloc[-1]
        return None if pd.isna(adx_val) else float(adx_val)
    except Exception:
        return None


def _bollinger_bands(close: pd.Series, period: int = 20, num_std: float = 2.0) -> Optional[Dict[str, float]]:
    """Compute Bollinger Bands and position."""
    if close is None or len(close) < period:
        return None
    try:
        sma = close.rolling(period).mean()
        std = close.rolling(period).std()
        upper = sma + num_std * std
        lower = sma - num_std * std
        current = float(close.iloc[-1])
        u = float(upper.iloc[-1])
        l = float(lower.iloc[-1])
        m = float(sma.iloc[-1])
        bandwidth = (u - l) / m if m > 0 else 0
        # Position: 0 = at lower band, 1 = at upper band
        position = (current - l) / (u - l) if (u - l) > 0 else 0.5
        # Squeeze: bandwidth in bottom 20% of recent history
        bw_series = (upper - lower) / sma
        bw_series = bw_series.dropna()
        squeeze = False
        if len(bw_series) >= 50:
            squeeze = float(bw_series.iloc[-1]) <= float(bw_series.tail(50).quantile(0.2))
        return {
            "upper": round(u, 2),
            "lower": round(l, 2),
            "middle": round(m, 2),
            "position": round(float(np.clip(position, 0, 1)), 3),
            "bandwidth": round(float(bandwidth), 4),
            "squeeze": bool(squeeze),
        }
    except Exception:
        return None


def _volume_breakout(volume: pd.Series, period: int = 20) -> Optional[Dict[str, float]]:
    """Detect volume breakouts."""
    if volume is None or len(volume) < period:
        return None
    try:
        avg = volume.tail(period).mean()
        current = float(volume.iloc[-1])
        ratio = current / avg if avg > 0 else 1.0
        return {
            "current_volume": int(current),
            "avg_volume_20d": int(avg),
            "volume_ratio": round(float(ratio), 2),
            "breakout": bool(ratio >= 2.0),
        }
    except Exception:
        return None


def _support_resistance(hist: pd.DataFrame, lookback: int = 60) -> Tuple[Optional[float], Optional[float]]:
    """Identify support and resistance from recent highs/lows."""
    if hist is None or len(hist) < 20:
        return None, None
    try:
        recent = hist.tail(lookback)
        high = recent["High"]
        low = recent["Low"]
        # Resistance: highest high, and second highest cluster
        resistance = float(high.max())
        # Support: lowest low
        support = float(low.min())
        return round(support, 2), round(resistance, 2)
    except Exception:
        return None, None


def _rsi(series: pd.Series, period: int = 14) -> Optional[float]:
    """RSI calculation."""
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


def compute_momentum(hist: pd.DataFrame) -> dict:
    """Compute momentum signals and entry timing for a stock.

    Args:
        hist: DataFrame with OHLCV data (standard yfinance format).

    Returns:
        dict with entry_score, entry_signal, support, resistance,
        adx, bollinger, volume_breakout, reasoning.
    """
    result = {
        "entry_score": None,
        "entry_signal": "HOLD",
        "support": None,
        "resistance": None,
        "adx": None,
        "bollinger": None,
        "volume_breakout": None,
        "reasoning": "Insufficient data",
    }

    if hist is None or len(hist) < 50:
        return result

    close = hist["Close"]
    volume = hist["Volume"]

    # Compute indicators
    adx = _adx(hist)
    result["adx"] = round(adx, 2) if adx is not None else None

    bb = _bollinger_bands(close)
    result["bollinger"] = bb

    vol_bo = _volume_breakout(volume)
    result["volume_breakout"] = vol_bo

    support, resistance = _support_resistance(hist)
    result["support"] = support
    result["resistance"] = resistance

    rsi = _rsi(close)

    # Entry scoring (0-100)
    score = 50  # neutral baseline
    reasons = []  # type: List[str]

    current_price = float(close.iloc[-1])

    # 1. RSI signals
    if rsi is not None:
        if rsi < 30:
            score += 15
            reasons.append("RSI oversold (%.1f)" % rsi)
        elif rsi < 35:
            score += 10
            reasons.append("RSI near oversold (%.1f)" % rsi)
        elif rsi > 70:
            score -= 20
            reasons.append("RSI overbought (%.1f)" % rsi)
        elif rsi > 65:
            score -= 10
            reasons.append("RSI elevated (%.1f)" % rsi)

    # 2. Support/resistance proximity
    if support is not None and resistance is not None and resistance > support:
        price_range = resistance - support
        dist_to_support = (current_price - support) / price_range if price_range > 0 else 0.5
        if dist_to_support < 0.15:
            score += 12
            reasons.append("Price near support ($%.2f)" % support)
        elif dist_to_support > 0.85:
            score -= 10
            reasons.append("Price near resistance ($%.2f)" % resistance)

    # 3. ADX trend strength
    if adx is not None:
        if adx > 30:
            score += 8
            reasons.append("Strong trend (ADX %.1f)" % adx)
        elif adx > 25:
            score += 5
            reasons.append("Moderate trend (ADX %.1f)" % adx)
        elif adx < 15:
            score -= 3
            reasons.append("Weak trend (ADX %.1f)" % adx)

    # 4. Bollinger Band signals
    if bb is not None:
        if bb["squeeze"]:
            score += 8
            reasons.append("Bollinger squeeze — breakout imminent")
            if adx is not None and adx > 20:
                score += 5
                reasons.append("Squeeze + rising ADX")
        if bb["position"] < 0.15:
            score += 8
            reasons.append("Price near lower Bollinger Band")
        elif bb["position"] > 0.90:
            score -= 5
            reasons.append("Price at upper Bollinger Band")

    # 5. Volume breakout
    if vol_bo is not None:
        if vol_bo["breakout"]:
            score += 10
            reasons.append("Volume breakout (%.1fx avg)" % vol_bo["volume_ratio"])
        elif vol_bo["volume_ratio"] > 1.5:
            score += 5
            reasons.append("Elevated volume (%.1fx avg)" % vol_bo["volume_ratio"])

    # Clamp score
    score = int(np.clip(score, 0, 100))
    result["entry_score"] = score
    result["rsi"] = round(rsi, 2) if rsi is not None else None

    # --- Tiered condition-counting signal logic (RELAXED) ---
    # 4 key conditions:
    #   1. RSI < 40 (was 35 — loosened)
    #   2. Near support (bottom 25% of range)
    #   3. Volume breakout or elevated (ratio >= 1.5)
    #   4. ADX > 20 (was 25 — loosened)
    conditions_met = 0

    # Condition 1: RSI favorable
    if rsi is not None and rsi < 40:
        conditions_met += 1

    # Condition 2: Near support
    if support is not None and resistance is not None and resistance > support:
        price_range = resistance - support
        dist_to_support = (current_price - support) / price_range if price_range > 0 else 0.5
        if dist_to_support < 0.25:
            conditions_met += 1

    # Condition 3: Volume breakout or elevated
    if vol_bo is not None and vol_bo["volume_ratio"] >= 1.5:
        conditions_met += 1

    # Condition 4: ADX trend
    if adx is not None and adx > 20:
        conditions_met += 1

    result["conditions_met"] = conditions_met

    # Determine signal from conditions + score (RELAXED THRESHOLDS)
    # STRONG_BUY: 3+ of 4 conditions
    # BUY: 2+ of 4 conditions (was 2), OR entry_score >= 50
    # HOLD: 1 condition OR score >= 40
    # WAIT: none met and score < 40
    if conditions_met >= 3:
        result["entry_signal"] = "STRONG_BUY"
    elif conditions_met >= 2 or score >= 50:
        result["entry_signal"] = "BUY"
    elif conditions_met >= 1 or score >= 40:
        result["entry_signal"] = "HOLD"
    else:
        result["entry_signal"] = "WAIT"

    result["reasoning"] = "; ".join(reasons) if reasons else "No strong signals detected"
    return result
