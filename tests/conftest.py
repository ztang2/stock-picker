"""Shared fixtures and test utilities for stock picker tests."""

import json
import os
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch
import pytest
import pandas as pd
import numpy as np


_REAL_DATA_DIR = Path(__file__).resolve().parent.parent / "data"
_SENTINEL_PATHS = {
    _REAL_DATA_DIR / "scan_results.db",
    _REAL_DATA_DIR / "app.db",
    _REAL_DATA_DIR / "scan_results.json",
    _REAL_DATA_DIR / "prev_scan_results.json",
    _REAL_DATA_DIR / "signal_history.json",
    _REAL_DATA_DIR / "alerts.json",
    _REAL_DATA_DIR / "trade_history.json",
    _REAL_DATA_DIR / "holdings.json",
    _REAL_DATA_DIR / "watchlist.json",
}


@pytest.fixture(autouse=True)
def _block_real_data_writes(request, monkeypatch):
    """Fail loudly if any test attempts to write to a real data/ file.

    Tests that legitimately touch data/ paths must redirect them to a
    temp dir via their own fixtures. This autouse fixture wraps builtins.open
    and sqlite3.connect so an accidental real-path write raises immediately
    instead of silently corrupting production state.
    """
    import builtins
    import sqlite3

    real_open = builtins.open
    real_connect = sqlite3.connect

    def guarded_open(file, mode="r", *args, **kwargs):
        if isinstance(file, (str, os.PathLike)):
            path = Path(file).resolve()
            if path in _SENTINEL_PATHS and any(c in mode for c in ("w", "a", "x", "+")):
                raise RuntimeError(
                    f"Test attempted to write to real data file: {path}. "
                    "Redirect via a fixture (e.g., patch src.<module>.PATH_CONST) "
                    "before writing."
                )
        return real_open(file, mode, *args, **kwargs)

    def guarded_connect(database, *args, **kwargs):
        if isinstance(database, (str, os.PathLike)):
            path = Path(str(database)).resolve()
            if path in _SENTINEL_PATHS:
                raise RuntimeError(
                    f"Test attempted to open real SQLite DB: {path}. "
                    "Patch DB_FILE on the service module before connecting."
                )
        return real_connect(database, *args, **kwargs)

    monkeypatch.setattr(builtins, "open", guarded_open)
    monkeypatch.setattr(sqlite3, "connect", guarded_connect)


# ============================================================================
# Mock Stock Data
# ============================================================================

MOCK_STOCK_INFO = {
    "ticker": "TEST",
    "shortName": "Test Corp",
    "sector": "Technology",
    "industry": "Software",
    "marketCap": 50e9,
    "averageVolume": 5000000,
    "regularMarketPrice": 150.0,
    "currentPrice": 150.0,
    "returnOnEquity": 0.25,
    "profitMargins": 0.20,
    "currentRatio": 1.5,
    "debtToEquity": 50,
    "trailingPE": 25,
    "priceToBook": 5.0,
    "priceToSalesTrailing12Months": 8.0,
    "pegRatio": 1.2,
    "beta": 1.1,
    "dividendYield": 0.01,
    "revenueGrowth": 0.15,
    "earningsGrowth": 0.20,
    "enterpriseValue": 45e9,
    "totalDebt": 5e9,
    "totalCash": 10e9,
}

MOCK_STOCK_INFO_LARGE_CAP = {
    **MOCK_STOCK_INFO,
    "ticker": "LARGE",
    "shortName": "Large Cap Corp",
    "marketCap": 200e9,
    "trailingPE": 20,
    "priceToBook": 4.0,
}

MOCK_STOCK_INFO_SMALL_CAP = {
    **MOCK_STOCK_INFO,
    "ticker": "SMALL",
    "shortName": "Small Cap Corp",
    "marketCap": 5e9,
    "trailingPE": 30,
    "priceToBook": 6.0,
}

MOCK_STOCK_INFO_HIGH_DECLINE = {
    **MOCK_STOCK_INFO,
    "ticker": "DECLINE",
    "shortName": "Declining Corp",
    "revenueGrowth": -0.15,  # 15% revenue decline = value trap
    "marketCap": 10e9,
}


def create_mock_history(n_days: int = 252, start_price: float = 150.0) -> pd.DataFrame:
    """Create mock OHLCV data as a DataFrame."""
    dates = pd.date_range(end=pd.Timestamp.now(tz="UTC"), periods=n_days, freq="D")
    np.random.seed(42)
    prices = start_price + np.cumsum(np.random.randn(n_days) * 2)
    prices = np.maximum(prices, start_price * 0.5)  # Prevent negative prices

    return pd.DataFrame(
        {
            "Open": prices + np.random.randn(n_days) * 0.5,
            "High": prices + np.abs(np.random.randn(n_days)),
            "Low": prices - np.abs(np.random.randn(n_days)),
            "Close": prices,
            "Volume": np.random.randint(1000000, 10000000, n_days),
            "Dividends": 0,
            "Stock Splits": 0,
        },
        index=dates,
    )


def create_mock_stock_data(info: dict = None, n_days: int = 252) -> dict:
    """Create mock stock data dict with info and history."""
    if info is None:
        info = MOCK_STOCK_INFO.copy()

    hist = create_mock_history(n_days, info.get("regularMarketPrice", 150.0))

    return {
        "info": info,
        "history": hist.to_dict(orient="list"),
        "history_index": [str(d) for d in hist.index],
    }


def create_mock_spy_history(n_days: int = 252) -> pd.DataFrame:
    """Create mock SPY history for beta calculations."""
    dates = pd.date_range(end=pd.Timestamp.now(tz="UTC"), periods=n_days, freq="D")
    np.random.seed(42)
    prices = 400.0 + np.cumsum(np.random.randn(n_days) * 1.5)
    prices = np.maximum(prices, 350.0)

    return pd.DataFrame(
        {
            "Open": prices + np.random.randn(n_days) * 0.3,
            "High": prices + np.abs(np.random.randn(n_days) * 0.5),
            "Low": prices - np.abs(np.random.randn(n_days) * 0.5),
            "Close": prices,
            "Volume": np.random.randint(5000000, 20000000, n_days),
            "Dividends": 0,
            "Stock Splits": 0,
        },
        index=dates,
    )


# ============================================================================
# Fixtures
# ============================================================================

@pytest.fixture
def temp_data_dir():
    """Create a temporary data directory for tests."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


@pytest.fixture
def mock_stock_info():
    """Return mock stock info dict."""
    return MOCK_STOCK_INFO.copy()


@pytest.fixture
def mock_stock_data():
    """Return mock stock data dict with realistic structure."""
    return create_mock_stock_data()


@pytest.fixture
def mock_history():
    """Return mock OHLCV history DataFrame."""
    return create_mock_history()


@pytest.fixture
def mock_spy_history():
    """Return mock SPY history for beta calculations."""
    return create_mock_spy_history()


@pytest.fixture
def mock_scan_result():
    """Return mock scan result structure."""
    return {
        "timestamp": "2024-01-15T10:30:00",
        "strategy": "balanced",
        "market_regime": "bull",
        "stocks_analyzed": 500,
        "stocks_after_filter": 120,
        "top": [
            {
                "ticker": "AAPL",
                "name": "Apple Inc",
                "sector": "Technology",
                "industry": "Consumer Electronics",
                "market_cap": 2.8e12,
                "composite_score": 85.5,
                "fundamentals": {"score": 80},
                "valuation": {"score": 75},
                "technicals": {"score": 90},
                "risk": {"score": 85},
            },
            {
                "ticker": "MSFT",
                "name": "Microsoft Corp",
                "sector": "Technology",
                "industry": "Software",
                "market_cap": 2.6e12,
                "composite_score": 82.3,
                "fundamentals": {"score": 85},
                "valuation": {"score": 80},
                "technicals": {"score": 85},
                "risk": {"score": 78},
            },
        ],
        "all_scores": [
            {"ticker": "AAPL", "composite_score": 85.5},
            {"ticker": "MSFT", "composite_score": 82.3},
            {"ticker": "GOOGL", "composite_score": 79.1},
        ],
    }


@pytest.fixture
def mock_yfinance():
    """Mock yfinance.Ticker for testing."""
    with patch("yfinance.Ticker") as mock_ticker:
        ticker_instance = MagicMock()
        ticker_instance.info = MOCK_STOCK_INFO.copy()
        ticker_instance.history.return_value = create_mock_history()
        mock_ticker.return_value = ticker_instance
        yield mock_ticker


@pytest.fixture
def mock_pipeline_env(temp_data_dir, monkeypatch):
    """Set up environment with mocked DATA_DIR and RESULTS_FILE."""
    monkeypatch.setenv("DATA_DIR", str(temp_data_dir))

    # Mock the paths in pipeline module
    with patch("src.pipeline.DATA_DIR", temp_data_dir), \
         patch("src.pipeline.RESULTS_FILE", temp_data_dir / "scan_results.json"), \
         patch("src.pipeline.CACHE_FILE", temp_data_dir / "stock_data_cache.json"):
        yield temp_data_dir


@pytest.fixture
def mock_api_env(temp_data_dir, monkeypatch):
    """Set up environment with mocked paths for API testing."""
    monkeypatch.setenv("DATA_DIR", str(temp_data_dir))
    monkeypatch.setenv("API_KEY", "test-key-12345")

    from src.scan_results_service import ScanResultsService
    ScanResultsService._cache = None
    ScanResultsService._cache_timestamp = None

    with patch("src.api.DATA_DIR", temp_data_dir), \
         patch("src.routes.scan.DATA_DIR", temp_data_dir), \
         patch("src.scan_results_service.DATA_DIR", temp_data_dir), \
         patch("src.scan_results_service.RESULTS_FILE", temp_data_dir / "scan_results.json"), \
         patch("src.scan_results_service.DB_FILE", temp_data_dir / "scan_results.db"), \
         patch("src.scan_results_service.PREV_RESULTS_FILE", temp_data_dir / "prev_scan_results.json"):
        yield temp_data_dir

    ScanResultsService._cache = None
    ScanResultsService._cache_timestamp = None
