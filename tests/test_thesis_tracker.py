"""Tests for src/thesis_tracker.py — focused coverage of state transitions."""

import json
from unittest.mock import MagicMock, patch

import pytest


@pytest.fixture
def thesis_env(temp_data_dir):
    """Redirect thesis storage to a temp dir."""
    thesis_file = temp_data_dir / "thesis_tracker.json"
    with patch("src.thesis_tracker.THESIS_FILE", thesis_file), \
         patch("src.thesis_tracker.DATA_DIR", temp_data_dir):
        yield thesis_file


def test_record_then_get_round_trip(thesis_env):
    """record_thesis writes to disk; get_thesis reads it back with enrichment."""
    from src import thesis_tracker

    with patch("src.thesis_tracker.get_ticker_object") as mock_get:
        mock_ticker = MagicMock()
        mock_ticker.info = {"currentPrice": 160.0, "regularMarketPrice": 160.0}
        mock_get.return_value = mock_ticker

        thesis_tracker.record_thesis(
            ticker="AAPL",
            thesis="Dominant ecosystem + cash flow",
            entry_price=150.0,
            target_price=180.0,
            stop_loss=135.0,
            conditions=["revenue growth above 5%"],
            time_horizon="1 year",
        )

        fetched = thesis_tracker.get_thesis("AAPL")

    assert fetched is not None
    assert fetched["ticker"] == "AAPL"
    assert fetched["entry_price"] == 150.0
    assert fetched["target_price"] == 180.0
    assert fetched["current_price"] == 160.0
    # Return: (160 - 150) / 150 * 100 = 6.67
    assert fetched["return_pct"] == pytest.approx(6.67, abs=0.01)
    # Target progress: (160 - 150) / (180 - 150) * 100 = 33.33
    assert fetched["target_progress_pct"] == pytest.approx(33.33, abs=0.01)


def test_check_thesis_detects_stop_loss_breach(thesis_env):
    """check_thesis returns status 'BREACHED' when current price <= stop_loss."""
    from src import thesis_tracker

    with patch("src.thesis_tracker.get_ticker_object") as mock_get:
        # Record with stop_loss at 135
        mock_ticker = MagicMock()
        mock_ticker.info = {"currentPrice": 150.0}
        mock_get.return_value = mock_ticker

        thesis_tracker.record_thesis(
            ticker="AAPL",
            thesis="Test",
            entry_price=150.0,
            target_price=180.0,
            stop_loss=135.0,
        )

        # Now simulate price dropping to 130 (below stop_loss)
        mock_ticker.info = {"currentPrice": 130.0}
        result = thesis_tracker.check_thesis("AAPL")

    assert result["status"] == "BREACHED"
    assert any("STOP LOSS" in w for w in result["warnings"])


def test_close_thesis_sets_status_and_reason(thesis_env):
    """close_thesis transitions a recorded thesis to status=closed with reason recorded."""
    from src import thesis_tracker

    with patch("src.thesis_tracker.get_ticker_object") as mock_get:
        mock_ticker = MagicMock()
        mock_ticker.info = {"currentPrice": 150.0}
        mock_get.return_value = mock_ticker

        thesis_tracker.record_thesis(
            ticker="AAPL",
            thesis="Test close flow",
            entry_price=150.0,
        )

        result = thesis_tracker.close_thesis("AAPL", reason="target hit")

    assert result["status"] == "closed"
    assert result["reason"] == "target hit"

    # Verify persistence
    saved = json.loads(thesis_env.read_text())
    assert saved["AAPL"]["status"] == "closed"
    assert saved["AAPL"]["close_reason"] == "target hit"
    assert "closed_at" in saved["AAPL"]
