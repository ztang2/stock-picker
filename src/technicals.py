"""Technical analysis: RSI, MACD, moving averages, volume trend."""

import logging
from typing import Optional

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)


def _rsi(series: pd.Series, period: int = 14) -> Optional[float]:
    delta = series.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.rolling(period).mean()
    avg_loss = loss.rolling(period).mean()
    rs = avg_gain / avg_loss
    rsi = 100 - (100 / (1 + rs))
    val = rsi.iloc[-1]
    return None if pd.isna(val) else float(val)


def _macd_signal(series: pd.Series) -> Optional[float]:
    """Return MACD - Signal line value."""
    ema12 = series.ewm(span=12).mean()
    ema26 = series.ewm(span=26).mean()
    macd = ema12 - ema26
    signal = macd.ewm(span=9).mean()
    val = (macd - signal).iloc[-1]
    return None if pd.isna(val) else float(val)


def score_technicals(hist: pd.DataFrame) -> dict:
    """Compute technical metrics from price history DataFrame.

    Expects hist with columns: Open, High, Low, Close, Volume (standard yfinance).
    Returns dict with metrics and 'score' (0-100).
    """
    metrics: dict = {}

    if hist is None or len(hist) < 50:
        return {"score": None}

    close = hist["Close"]
    volume = hist["Volume"]

    # RSI
    rsi = _rsi(close)
    metrics["rsi"] = rsi

    # MACD histogram
    macd_hist = _macd_signal(close)
    metrics["macd_histogram"] = macd_hist

    # Price vs moving averages
    ma50 = close.rolling(50).mean().iloc[-1]
    ma200 = close.rolling(200).mean().iloc[-1] if len(close) >= 200 else None
    current = close.iloc[-1]

    metrics["price"] = float(current)
    metrics["ma50"] = float(ma50) if not pd.isna(ma50) else None
    metrics["ma200"] = float(ma200) if ma200 is not None and not pd.isna(ma200) else None
    metrics["above_ma50"] = bool(current > ma50) if not pd.isna(ma50) else None
    metrics["above_ma200"] = bool(current > ma200) if ma200 is not None and not pd.isna(ma200) else None

    # Volume trend (20d avg vs 50d avg)
    vol_20 = volume.tail(20).mean()
    vol_50 = volume.tail(50).mean()
    vol_trend = float(vol_20 / vol_50) if vol_50 > 0 else None
    metrics["volume_trend"] = vol_trend

    # Score components (each out of 25, total 100)
    components = []

    # RSI: 30-50 is best (oversold-to-neutral = buying opportunity), 70+ bad
    if rsi is not None:
        if rsi < 30:
            components.append(22)  # oversold, good entry
        elif rsi < 50:
            components.append(25)  # ideal range
        elif rsi < 70:
            components.append(25 - (rsi - 50) * 0.75)
        else:
            components.append(max(0, 10 - (rsi - 70) * 0.33))
    else:
        components.append(None)

    # MACD: positive histogram = bullish
    if macd_hist is not None:
        price = float(current)
        norm = (macd_hist / price * 100) if price > 0 else 0
        components.append(np.clip(12.5 + norm * 25, 0, 25))
    else:
        components.append(None)

    # Moving average position
    ma_score = 0
    ma_count = 0
    if metrics["above_ma50"] is not None:
        ma_score += 12.5 if metrics["above_ma50"] else 0
        ma_count += 1
    if metrics["above_ma200"] is not None:
        ma_score += 12.5 if metrics["above_ma200"] else 0
        ma_count += 1
    if ma_count > 0:
        components.append(ma_score / ma_count * 2)
    else:
        components.append(None)

    # Volume trend: >1.0 means increasing volume (bullish confirmation)
    if vol_trend is not None:
        components.append(np.clip(vol_trend * 12.5, 0, 25))
    else:
        components.append(None)

    valid = [c for c in components if c is not None]
    if valid:
        metrics["score"] = sum(valid) / len(valid) * 4
    else:
        metrics["score"] = None

    return metrics
