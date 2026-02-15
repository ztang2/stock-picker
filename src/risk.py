"""Risk metrics: beta, max drawdown, Sharpe ratio, volatility."""

import logging
from typing import Optional

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)

RISK_FREE_RATE = 0.045  # 4.5% annualized


def _compute_beta(stock_returns: pd.Series, benchmark_returns: pd.Series) -> Optional[float]:
    """Compute beta vs benchmark."""
    aligned = pd.concat([stock_returns, benchmark_returns], axis=1).dropna()
    if len(aligned) < 30:
        return None
    cov = np.cov(aligned.iloc[:, 0], aligned.iloc[:, 1])
    var_bench = cov[1, 1]
    if var_bench == 0:
        return None
    return float(cov[0, 1] / var_bench)


def _max_drawdown(prices: pd.Series) -> Optional[float]:
    """Compute maximum drawdown from price series."""
    if len(prices) < 2:
        return None
    cummax = prices.cummax()
    drawdown = (prices - cummax) / cummax
    return float(drawdown.min())


def _sharpe_ratio(returns: pd.Series, risk_free_rate: float = RISK_FREE_RATE) -> Optional[float]:
    """Annualized Sharpe ratio."""
    if len(returns) < 30:
        return None
    daily_rf = (1 + risk_free_rate) ** (1 / 252) - 1
    excess = returns - daily_rf
    std = excess.std()
    if std == 0 or np.isnan(std):
        return None
    return float(excess.mean() / std * np.sqrt(252))


def _volatility(returns: pd.Series) -> Optional[float]:
    """Annualized volatility (std dev of returns)."""
    if len(returns) < 30:
        return None
    return float(returns.std() * np.sqrt(252))


def score_risk(hist: pd.DataFrame, spy_hist: Optional[pd.DataFrame] = None) -> dict:
    """Compute risk metrics and a raw score (0-100).

    Args:
        hist: Stock price history DataFrame (Close column required).
        spy_hist: SPY price history for beta calculation.
    """
    metrics: dict = {}

    if hist is None or len(hist) < 50:
        return {"score": None}

    close = hist["Close"]
    returns = close.pct_change().dropna()

    # Beta
    beta = None
    if spy_hist is not None and len(spy_hist) >= 50:
        spy_close = spy_hist["Close"]
        spy_returns = spy_close.pct_change().dropna()
        beta = _compute_beta(returns, spy_returns)
    metrics["beta"] = beta

    # Max drawdown
    mdd = _max_drawdown(close)
    metrics["max_drawdown"] = round(mdd, 4) if mdd is not None else None

    # Sharpe ratio
    sharpe = _sharpe_ratio(returns)
    metrics["sharpe_ratio"] = round(sharpe, 4) if sharpe is not None else None

    # Volatility
    vol = _volatility(returns)
    metrics["volatility"] = round(vol, 4) if vol is not None else None

    # Score: lower risk = higher score
    components = []

    # Beta: 1.0 is neutral. <0.8 → 25, 1.0 → 18, >1.5 → 5
    if beta is not None:
        components.append(np.clip(25 - (beta - 0.8) * 28.6, 0, 25))

    # Max drawdown: 0 → 25, -0.2 → 15, -0.5 → 0
    if mdd is not None:
        components.append(np.clip(25 + mdd * 50, 0, 25))

    # Sharpe: >2 → 25, 1 → 18, 0 → 8, <0 → 0
    if sharpe is not None:
        components.append(np.clip(sharpe * 12.5, 0, 25))

    # Volatility: <0.15 → 25, 0.3 → 15, >0.6 → 0
    if vol is not None:
        components.append(np.clip(25 - (vol - 0.15) * 55.6, 0, 25))

    if components:
        metrics["score"] = sum(components) / len(components) * 4
    else:
        metrics["score"] = None

    return metrics
