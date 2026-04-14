"""Retry/backoff wrapper for yfinance API calls.

Handles rate limiting and transient failures with:
- Exponential backoff: start at 1s, max 30s, max 3 retries
- Circuit breaker: if 5 consecutive failures within 5 minutes, stop trying for 60s
- Logging for retries and circuit breaker state
- Uses only stdlib (time.sleep, random for jitter)
"""

import logging
import random
import time
from datetime import datetime, timedelta
from typing import Optional, Any, Callable, List

import yfinance as yf

logger = logging.getLogger(__name__)

# Circuit breaker state
_circuit_breaker = {
    "failure_count": 0,
    "failure_timestamps": [],  # timestamps of failures in last 5 minutes
    "circuit_open": False,
    "circuit_open_time": None,
}

# Configuration
MAX_RETRIES = 3
INITIAL_BACKOFF_SECONDS = 1
MAX_BACKOFF_SECONDS = 30
CIRCUIT_BREAKER_FAILURE_THRESHOLD = 5
CIRCUIT_BREAKER_TIME_WINDOW_SECONDS = 300  # 5 minutes
CIRCUIT_BREAKER_OPEN_DURATION_SECONDS = 60  # 60 seconds


def _is_circuit_open() -> bool:
    """Check if circuit breaker is currently open."""
    if not _circuit_breaker["circuit_open"]:
        return False

    if _circuit_breaker["circuit_open_time"] is None:
        return True

    elapsed = time.time() - _circuit_breaker["circuit_open_time"]
    if elapsed >= CIRCUIT_BREAKER_OPEN_DURATION_SECONDS:
        _circuit_breaker["circuit_open"] = False
        _circuit_breaker["circuit_open_time"] = None
        _circuit_breaker["failure_count"] = 0
        _circuit_breaker["failure_timestamps"] = []
        logger.info("Circuit breaker closed, retrying yfinance calls")
        return False

    return True


def _record_failure():
    """Record a failure and update circuit breaker state."""
    now = time.time()
    _circuit_breaker["failure_timestamps"].append(now)

    # Keep only failures from last 5 minutes
    _circuit_breaker["failure_timestamps"] = [
        ts for ts in _circuit_breaker["failure_timestamps"]
        if now - ts <= CIRCUIT_BREAKER_TIME_WINDOW_SECONDS
    ]

    _circuit_breaker["failure_count"] = len(_circuit_breaker["failure_timestamps"])

    if _circuit_breaker["failure_count"] >= CIRCUIT_BREAKER_FAILURE_THRESHOLD:
        _circuit_breaker["circuit_open"] = True
        _circuit_breaker["circuit_open_time"] = now
        logger.error(
            "Circuit breaker OPEN: %d failures in last 5 minutes, "
            "stopping retries for 60 seconds",
            _circuit_breaker["failure_count"]
        )


def _record_success():
    """Record a successful call and reset failure tracking."""
    _circuit_breaker["failure_count"] = 0
    _circuit_breaker["failure_timestamps"] = []


def _retry_with_backoff(
    func: Callable,
    *args,
    **kwargs
) -> Any:
    """Execute func with exponential backoff retry logic.

    Args:
        func: Callable to execute (typically a yfinance call)
        *args: Positional arguments to pass to func
        **kwargs: Keyword arguments to pass to func

    Returns:
        Result of func call

    Raises:
        The last exception if all retries exhausted
    """
    if _is_circuit_open():
        raise RuntimeError(
            f"yfinance circuit breaker is open. "
            f"Too many failures ({_circuit_breaker['failure_count']}) "
            f"in last 5 minutes. Retrying in 60 seconds."
        )

    last_exception = None
    backoff = INITIAL_BACKOFF_SECONDS

    for attempt in range(MAX_RETRIES + 1):
        try:
            result = func(*args, **kwargs)
            _record_success()
            return result
        except Exception as e:
            last_exception = e
            _record_failure()

            if attempt < MAX_RETRIES:
                # Add jitter: random value between 0 and backoff
                jitter = random.uniform(0, backoff)
                sleep_time = min(jitter, MAX_BACKOFF_SECONDS)

                logger.warning(
                    "yfinance call failed (attempt %d/%d), "
                    "retrying in %.2f seconds: %s",
                    attempt + 1,
                    MAX_RETRIES + 1,
                    sleep_time,
                    str(e)
                )
                time.sleep(sleep_time)
                backoff = min(backoff * 2, MAX_BACKOFF_SECONDS)
            else:
                logger.error(
                    "yfinance call failed after %d attempts: %s",
                    MAX_RETRIES + 1,
                    str(e)
                )

    raise last_exception


def get_ticker_info(ticker: str) -> dict:
    """Fetch ticker info with retry logic.

    Args:
        ticker: Ticker symbol (e.g., 'AAPL')

    Returns:
        Dictionary of ticker info from yfinance
    """
    def _fetch():
        return yf.Ticker(ticker).info

    return _retry_with_backoff(_fetch)


def get_ticker_history(ticker: str, period: str = "3mo") -> Any:
    """Fetch ticker historical data with retry logic.

    Args:
        ticker: Ticker symbol (e.g., 'AAPL')
        period: Period string (e.g., '3mo', '1y', '5y')

    Returns:
        DataFrame of historical OHLCV data
    """
    def _fetch():
        return yf.Ticker(ticker).history(period=period)

    return _retry_with_backoff(_fetch)


def download(
    tickers: Any,
    period: Optional[str] = None,
    start: Optional[str] = None,
    end: Optional[str] = None,
    **kwargs
) -> Any:
    """Download historical data for one or more tickers with retry logic.

    Args:
        tickers: Single ticker string or list of ticker strings
        period: Period string (e.g., '3mo', '1y', '5y'). Mutually exclusive with start/end.
        start: Start date string (e.g., '2020-01-01'). Mutually exclusive with period.
        end: End date string (e.g., '2023-12-31'). Mutually exclusive with period.
        **kwargs: Other keyword arguments to pass to yf.download (progress, threads, etc.)

    Returns:
        DataFrame or Series of OHLCV data
    """
    def _fetch():
        if period:
            return yf.download(tickers, period=period, **kwargs)
        else:
            return yf.download(tickers, start=start, end=end, **kwargs)

    return _retry_with_backoff(_fetch)


def get_ticker_object(ticker: str) -> yf.Ticker:
    """Get a yfinance Ticker object with retry logic.

    Note: This returns a fresh Ticker object without built-in retry.
    Use get_ticker_info() or get_ticker_history() for those operations,
    or access the object's .info and .history() methods directly.

    Args:
        ticker: Ticker symbol (e.g., 'AAPL')

    Returns:
        yfinance Ticker object
    """
    def _fetch():
        return yf.Ticker(ticker)

    return _retry_with_backoff(_fetch)
