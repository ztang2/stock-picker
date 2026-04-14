"""Tests for watchlist endpoints in src/api.py.

These tests characterize CURRENT behavior. The endpoints do not enforce
X-API-Key auth despite CLAUDE.md claiming they should — fixing the auth
gap is a separate ticket.
"""

import json
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def watchlist_client(temp_data_dir):
    """Yield a TestClient with watchlist and cache paths redirected to a temp dir."""
    watchlist_path = temp_data_dir / "watchlist.json"
    cache_path = temp_data_dir / "stock_data_cache.json"

    # Seed a cache with a known price for FAF so _get_current_price returns 60.84
    cache_path.write_text(json.dumps({
        "FAF": {
            "info": {"ticker": "FAF"},
            "history": {
                "Close": [60.84],
                "Open": [60.0],
                "High": [61.0],
                "Low": [59.5],
                "Volume": [1_000_000],
            },
            "history_index": ["2026-04-13T00:00:00"],
        }
    }))

    with patch("src.api.WATCHLIST_FILE", watchlist_path), \
         patch("src.api.DATA_DIR", temp_data_dir):
        from src.api import app
        yield TestClient(app)


def test_get_empty_watchlist(watchlist_client):
    """GET on a fresh watchlist returns an empty tickers dict."""
    resp = watchlist_client.get("/watchlist")
    assert resp.status_code == 200
    assert resp.json() == {"tickers": {}}


def test_post_adds_ticker_with_price_snapshot(watchlist_client):
    """POST records the ticker with current price and today's date."""
    resp = watchlist_client.post("/watchlist/FAF")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "added"
    assert body["ticker"] == "FAF"
    assert body["price_at_add"] == 60.84

    listing = watchlist_client.get("/watchlist").json()
    assert "FAF" in listing["tickers"]
    assert listing["tickers"]["FAF"]["price_at_add"] == 60.84
    assert listing["tickers"]["FAF"]["current_price"] == 60.84
    assert listing["tickers"]["FAF"]["change_pct"] == 0.0


def test_post_is_idempotent_with_already_exists_status(watchlist_client):
    """Adding the same ticker twice returns 'already_exists' — current behavior."""
    first = watchlist_client.post("/watchlist/FAF")
    assert first.status_code == 200
    assert first.json()["status"] == "added"

    second = watchlist_client.post("/watchlist/FAF")
    assert second.status_code == 200
    assert second.json()["status"] == "already_exists"

    listing = watchlist_client.get("/watchlist").json()
    assert list(listing["tickers"].keys()).count("FAF") == 1


def test_post_uppercases_ticker(watchlist_client):
    """Ticker is normalized to uppercase in storage."""
    resp = watchlist_client.post("/watchlist/faf")
    assert resp.status_code == 200
    assert resp.json()["ticker"] == "FAF"


def test_delete_removes_ticker(watchlist_client):
    """DELETE removes the ticker from the watchlist."""
    watchlist_client.post("/watchlist/FAF")
    resp = watchlist_client.delete("/watchlist/FAF")
    assert resp.status_code == 200
    assert resp.json() == {"status": "removed", "ticker": "FAF"}

    listing = watchlist_client.get("/watchlist").json()
    assert "FAF" not in listing["tickers"]


def test_delete_unknown_ticker_returns_not_found_status(watchlist_client):
    """DELETE on a ticker that was never added returns 200 with 'not_found' — current behavior."""
    resp = watchlist_client.delete("/watchlist/ZZZZ")
    assert resp.status_code == 200
    assert resp.json()["status"] == "not_found"


def test_post_without_api_key_succeeds(watchlist_client):
    """Current behavior: POST does not enforce X-API-Key.

    Documented as a pre-existing bug. When auth is added later,
    update this test to require a valid key.
    """
    resp = watchlist_client.post("/watchlist/FAF")
    assert resp.status_code == 200
