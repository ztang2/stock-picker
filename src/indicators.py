"""Shared technical indicators to avoid duplication."""

from typing import Optional

import pandas as pd


def _rsi(series: pd.Series, period: int = 14) -> Optional[float]:
    """Calculate Relative Strength Index (RSI).
    
    Args:
        series: Price series (typically Close prices)
        period: RSI period (default 14)
        
    Returns:
        RSI value (0-100) or None if insufficient data
    """
    delta = series.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.rolling(period).mean()
    avg_loss = loss.rolling(period).mean()
    rs = avg_gain / avg_loss
    rsi = 100 - (100 / (1 + rs))
    val = rsi.iloc[-1]
    return None if pd.isna(val) else float(val)
