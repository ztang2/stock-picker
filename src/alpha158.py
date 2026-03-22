# Alpha158 Feature Engineering
# Adapted from Microsoft Qlib's Alpha158 feature set
# Reference: https://github.com/microsoft/qlib/blob/main/qlib/contrib/data/loader.py
#
# Computes 158 technical features from OHLCV data using multiple rolling windows.
# All features are normalized by current close price to remove unit dependency.

import numpy as np
import pandas as pd
from typing import Dict, Optional
import logging

logger = logging.getLogger(__name__)

ROLLING_WINDOWS = [5, 10, 20, 30, 60]


def compute_alpha158(df: pd.DataFrame) -> pd.DataFrame:
    """
    Compute Alpha158 features from OHLCV DataFrame.
    
    Args:
        df: DataFrame with columns ['Open', 'High', 'Low', 'Close', 'Volume']
            and DatetimeIndex, sorted ascending by date.
    
    Returns:
        DataFrame with 158 features, same index as input.
        Rows with insufficient history will have NaN values.
    """
    if df.empty or len(df) < 60:
        return pd.DataFrame(index=df.index)
    
    close = df['Close'].astype(float)
    open_ = df['Open'].astype(float)
    high = df['High'].astype(float)
    low = df['Low'].astype(float)
    volume = df['Volume'].astype(float) + 1e-12  # avoid div by zero
    
    features = {}
    
    # ============================================================
    # 1. K-Bar Features (9 features)
    # ============================================================
    hl_spread = high - low + 1e-12
    features['KMID'] = (close - open_) / open_
    features['KLEN'] = hl_spread / open_
    features['KMID2'] = (close - open_) / hl_spread
    features['KUP'] = (high - np.maximum(open_, close)) / open_
    features['KUP2'] = (high - np.maximum(open_, close)) / hl_spread
    features['KLOW'] = (np.minimum(open_, close) - low) / open_
    features['KLOW2'] = (np.minimum(open_, close) - low) / hl_spread
    features['KSFT'] = (2 * close - high - low) / open_
    features['KSFT2'] = (2 * close - high - low) / hl_spread
    
    # ============================================================
    # 2. Price Features (4 features - current day ratios)
    # ============================================================
    features['OPEN0'] = open_ / close
    features['HIGH0'] = high / close
    features['LOW0'] = low / close
    features['VWAP0'] = (open_ + high + low + close) / (4 * close)  # approximate VWAP
    
    # ============================================================
    # 3. Rolling Features (across 5 windows: 5, 10, 20, 30, 60 days)
    # ============================================================
    for d in ROLLING_WINDOWS:
        # ROC - Rate of Change
        features[f'ROC{d}'] = close.shift(d) / close
        
        # MA - Simple Moving Average ratio
        features[f'MA{d}'] = close.rolling(d).mean() / close
        
        # STD - Standard Deviation ratio
        features[f'STD{d}'] = close.rolling(d).std() / close
        
        # BETA - Slope of linear regression
        def _slope(series, window):
            result = series.copy() * np.nan
            x = np.arange(window, dtype=float)
            x_mean = x.mean()
            x_var = ((x - x_mean) ** 2).sum()
            for i in range(window - 1, len(series)):
                y = series.iloc[i - window + 1:i + 1].values
                if len(y) == window and not np.any(np.isnan(y)):
                    y_mean = y.mean()
                    result.iloc[i] = ((x - x_mean) * (y - y_mean)).sum() / (x_var + 1e-12)
            return result
        
        features[f'BETA{d}'] = _slope(close, d) / close
        
        # RSQR - R-squared of linear regression
        def _rsquare(series, window):
            result = series.copy() * np.nan
            x = np.arange(window, dtype=float)
            x_mean = x.mean()
            x_var = ((x - x_mean) ** 2).sum()
            for i in range(window - 1, len(series)):
                y = series.iloc[i - window + 1:i + 1].values
                if len(y) == window and not np.any(np.isnan(y)):
                    y_mean = y.mean()
                    cov = ((x - x_mean) * (y - y_mean)).sum()
                    y_var = ((y - y_mean) ** 2).sum()
                    if y_var > 1e-12:
                        result.iloc[i] = (cov ** 2) / (x_var * y_var)
                    else:
                        result.iloc[i] = 0.0
            return result
        
        features[f'RSQR{d}'] = _rsquare(close, d)
        
        # RESI - Residual of linear regression
        def _resi(series, window):
            result = series.copy() * np.nan
            x = np.arange(window, dtype=float)
            x_mean = x.mean()
            x_var = ((x - x_mean) ** 2).sum()
            for i in range(window - 1, len(series)):
                y = series.iloc[i - window + 1:i + 1].values
                if len(y) == window and not np.any(np.isnan(y)):
                    y_mean = y.mean()
                    slope = ((x - x_mean) * (y - y_mean)).sum() / (x_var + 1e-12)
                    intercept = y_mean - slope * x_mean
                    predicted = slope * x[-1] + intercept
                    result.iloc[i] = y[-1] - predicted
            return result
        
        features[f'RESI{d}'] = _resi(close, d) / close
        
        # MAX - Max high price ratio
        features[f'MAX{d}'] = high.rolling(d).max() / close
        
        # MIN - Min low price ratio
        features[f'MIN{d}'] = low.rolling(d).min() / close
        
        # QTLU - 80th percentile
        features[f'QTLU{d}'] = close.rolling(d).quantile(0.8) / close
        
        # QTLD - 20th percentile
        features[f'QTLD{d}'] = close.rolling(d).quantile(0.2) / close
        
        # RANK - Current price percentile in window
        def _rank(series, window):
            result = series.copy() * np.nan
            for i in range(window - 1, len(series)):
                window_data = series.iloc[i - window + 1:i + 1].values
                if not np.any(np.isnan(window_data)):
                    result.iloc[i] = (window_data < window_data[-1]).sum() / window
            return result
        
        features[f'RANK{d}'] = _rank(close, d)
        
        # RSV - Price position between high and low
        min_low = low.rolling(d).min()
        max_high = high.rolling(d).max()
        features[f'RSV{d}'] = (close - min_low) / (max_high - min_low + 1e-12)
        
        # IMAX - Days since max high (normalized)
        features[f'IMAX{d}'] = high.rolling(d).apply(lambda x: (d - 1 - x.argmax()) / d, raw=True)
        
        # IMIN - Days since min low (normalized)
        features[f'IMIN{d}'] = low.rolling(d).apply(lambda x: (d - 1 - x.argmin()) / d, raw=True)
        
        # IMXD - IMAX - IMIN
        features[f'IMXD{d}'] = features[f'IMAX{d}'] - features[f'IMIN{d}']
        
        # CORR - Correlation between close and log(volume)
        log_vol = np.log(volume)
        features[f'CORR{d}'] = close.rolling(d).corr(log_vol)
        
        # CORD - Correlation between returns and volume changes
        ret = close / close.shift(1)
        vol_ret = volume / volume.shift(1)
        features[f'CORD{d}'] = ret.rolling(d).corr(np.log(vol_ret + 1e-12))
        
        # CNTP - Percentage of up days
        up = (close > close.shift(1)).astype(float)
        features[f'CNTP{d}'] = up.rolling(d).mean()
        
        # CNTN - Percentage of down days
        down = (close < close.shift(1)).astype(float)
        features[f'CNTN{d}'] = down.rolling(d).mean()
        
        # CNTD - Up days minus down days percentage
        features[f'CNTD{d}'] = features[f'CNTP{d}'] - features[f'CNTN{d}']
        
        # SUMP - RSI-like: sum of gains / sum of absolute changes
        price_change = close - close.shift(1)
        gains = price_change.clip(lower=0)
        abs_changes = price_change.abs()
        features[f'SUMP{d}'] = gains.rolling(d).sum() / (abs_changes.rolling(d).sum() + 1e-12)
        
        # SUMN - Sum of losses / sum of absolute changes
        losses = (-price_change).clip(lower=0)
        features[f'SUMN{d}'] = losses.rolling(d).sum() / (abs_changes.rolling(d).sum() + 1e-12)
        
        # SUMD - SUMP - SUMN
        features[f'SUMD{d}'] = features[f'SUMP{d}'] - features[f'SUMN{d}']
        
        # VMA - Volume moving average ratio
        features[f'VMA{d}'] = volume.rolling(d).mean() / volume
        
        # VSTD - Volume standard deviation ratio
        features[f'VSTD{d}'] = volume.rolling(d).std() / (volume + 1e-12)
    
    result = pd.DataFrame(features, index=df.index)
    
    # Replace inf with NaN
    result = result.replace([np.inf, -np.inf], np.nan)
    
    logger.info(f"Computed {len(result.columns)} Alpha158 features for {len(result)} rows")
    return result


def compute_alpha158_fast(df: pd.DataFrame) -> pd.DataFrame:
    """
    Fast version: skip BETA/RSQR/RESI (expensive loop-based computations).
    Uses ~120 features instead of 158. Good for batch processing 800+ stocks.
    """
    if df.empty or len(df) < 60:
        return pd.DataFrame(index=df.index)
    
    close = df['Close'].astype(float)
    open_ = df['Open'].astype(float)
    high = df['High'].astype(float)
    low = df['Low'].astype(float)
    volume = df['Volume'].astype(float) + 1e-12
    
    features = {}
    
    # K-Bar (9)
    hl_spread = high - low + 1e-12
    features['KMID'] = (close - open_) / open_
    features['KLEN'] = hl_spread / open_
    features['KMID2'] = (close - open_) / hl_spread
    features['KUP'] = (high - np.maximum(open_, close)) / open_
    features['KUP2'] = (high - np.maximum(open_, close)) / hl_spread
    features['KLOW'] = (np.minimum(open_, close) - low) / open_
    features['KLOW2'] = (np.minimum(open_, close) - low) / hl_spread
    features['KSFT'] = (2 * close - high - low) / open_
    features['KSFT2'] = (2 * close - high - low) / hl_spread
    
    # Price (4)
    features['OPEN0'] = open_ / close
    features['HIGH0'] = high / close
    features['LOW0'] = low / close
    features['VWAP0'] = (open_ + high + low + close) / (4 * close)
    
    # Rolling features
    ret = close / close.shift(1)
    price_change = close - close.shift(1)
    log_vol = np.log(volume)
    vol_ret = volume / volume.shift(1)
    up = (close > close.shift(1)).astype(float)
    down = (close < close.shift(1)).astype(float)
    gains = price_change.clip(lower=0)
    losses = (-price_change).clip(lower=0)
    abs_changes = price_change.abs()
    
    for d in ROLLING_WINDOWS:
        features[f'ROC{d}'] = close.shift(d) / close
        features[f'MA{d}'] = close.rolling(d).mean() / close
        features[f'STD{d}'] = close.rolling(d).std() / close
        features[f'MAX{d}'] = high.rolling(d).max() / close
        features[f'MIN{d}'] = low.rolling(d).min() / close
        features[f'QTLU{d}'] = close.rolling(d).quantile(0.8) / close
        features[f'QTLD{d}'] = close.rolling(d).quantile(0.2) / close
        
        min_low = low.rolling(d).min()
        max_high = high.rolling(d).max()
        features[f'RSV{d}'] = (close - min_low) / (max_high - min_low + 1e-12)
        
        features[f'IMAX{d}'] = high.rolling(d).apply(lambda x: (d - 1 - x.argmax()) / d, raw=True)
        features[f'IMIN{d}'] = low.rolling(d).apply(lambda x: (d - 1 - x.argmin()) / d, raw=True)
        features[f'IMXD{d}'] = features[f'IMAX{d}'] - features[f'IMIN{d}']
        
        features[f'CORR{d}'] = close.rolling(d).corr(log_vol)
        features[f'CORD{d}'] = ret.rolling(d).corr(np.log(vol_ret + 1e-12))
        
        features[f'CNTP{d}'] = up.rolling(d).mean()
        features[f'CNTN{d}'] = down.rolling(d).mean()
        features[f'CNTD{d}'] = features[f'CNTP{d}'] - features[f'CNTN{d}']
        
        features[f'SUMP{d}'] = gains.rolling(d).sum() / (abs_changes.rolling(d).sum() + 1e-12)
        features[f'SUMN{d}'] = losses.rolling(d).sum() / (abs_changes.rolling(d).sum() + 1e-12)
        features[f'SUMD{d}'] = features[f'SUMP{d}'] - features[f'SUMN{d}']
        
        features[f'VMA{d}'] = volume.rolling(d).mean() / volume
        features[f'VSTD{d}'] = volume.rolling(d).std() / (volume + 1e-12)
    
    result = pd.DataFrame(features, index=df.index)
    result = result.replace([np.inf, -np.inf], np.nan)
    return result


def compute_for_ticker(ticker: str, hist: pd.DataFrame) -> Optional[pd.DataFrame]:
    """Compute Alpha158 features for a single ticker's history."""
    try:
        if hist is None or hist.empty or len(hist) < 60:
            return None
        
        # Ensure required columns
        required = ['Open', 'High', 'Low', 'Close', 'Volume']
        if not all(c in hist.columns for c in required):
            return None
        
        features = compute_alpha158_fast(hist)
        features['ticker'] = ticker
        return features
    except Exception as e:
        logger.warning(f"Failed to compute Alpha158 for {ticker}: {e}")
        return None
