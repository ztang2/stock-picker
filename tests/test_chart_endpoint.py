"""Tests for /chart/{ticker} endpoint in src/routes/scan.py."""

import json
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def chart_client(temp_data_dir):
    """Yield a TestClient with the stock data cache redirected to a temp dir."""
    cache_path = temp_data_dir / "stock_data_cache.json"

    closes = [100.0 + i * 0.5 for i in range(90)]
    dates = [f"2026-01-{(i % 28) + 1:02d}T00:00:00" for i in range(90)]
    cache_path.write_text(json.dumps({
        "AAPL": {
            "info": {"ticker": "AAPL"},
            "history": {
                "Open": closes,
                "High": [c + 1 for c in closes],
                "Low": [c - 1 for c in closes],
                "Close": closes,
                "Volume": [1_000_000] * 90,
            },
            "history_index": dates,
        }
    }))

    # DATA_DIR is imported into scan.py from deps.py (which re-exports from pipeline.py)
    patches = [
        patch("src.routes.scan.DATA_DIR", temp_data_dir),
    ]
    for p in patches:
        p.start()

    from src.api import app
    try:
        yield TestClient(app)
    finally:
        for p in patches:
            p.stop()


def test_chart_returns_200_for_cached_ticker(chart_client):
    """Known cached ticker returns 200 with a non-empty body."""
    resp = chart_client.get("/chart/AAPL")
    assert resp.status_code == 200
    body = resp.json()
    assert body  # non-empty


def test_chart_returns_ohlc_and_levels(chart_client):
    """Response contains ticker, ohlc array, support, resistance, and ma50."""
    resp = chart_client.get("/chart/AAPL")
    body = resp.json()

    assert "ticker" in body
    assert body["ticker"] == "AAPL"

    assert "ohlc" in body
    assert isinstance(body["ohlc"], list)
    assert len(body["ohlc"]) > 0

    # Each OHLC entry has date, open, high, low, close
    first = body["ohlc"][0]
    for key in ("date", "open", "high", "low", "close"):
        assert key in first, f"Missing '{key}' in ohlc entry: {first}"

    assert "support" in body
    assert "resistance" in body
    assert "ma50" in body


def test_chart_unknown_ticker_handled_gracefully(chart_client):
    """Ticker with no cache entry returns a handled response, not a 500.

    The endpoint returns 404 when no data is found (not a 500 crash).
    get_ticker_history is imported inside _load_chart so patch at source.
    """
    import pandas as pd

    with patch("src.yfinance_client.get_ticker_history", return_value=pd.DataFrame()):
        resp = chart_client.get("/chart/ZZZZZZZZ")

    # Endpoint raises HTTPException(404) when data is unavailable
    assert resp.status_code == 404, (
        f"Expected 404 for unknown ticker, got {resp.status_code}: {resp.text}"
    )
