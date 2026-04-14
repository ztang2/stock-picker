"""Tests for src/cache_health.py."""

import json
import math
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

import pytest


def _make_cache(tmpdir: Path, entries: dict) -> Path:
    """Write a stock_data_cache.json-shaped file and return its path."""
    path = tmpdir / "cache.json"
    path.write_text(json.dumps(entries))
    return path


def _days_ago_iso(n: int) -> str:
    """Return an ISO timestamp N calendar days in the past."""
    return (datetime.now(timezone.utc) - timedelta(days=n)).isoformat()


def _fresh_ticker(close_value: float = 100.0) -> dict:
    """Return a ticker entry with one fresh price point."""
    return {
        "info": {"ticker": "TEST"},
        "history": {
            "Close": [close_value],
            "Open": [close_value],
            "High": [close_value],
            "Low": [close_value],
            "Volume": [1_000_000],
        },
        "history_index": [_days_ago_iso(0)],
    }


def test_diagnose_healthy_cache(temp_data_dir):
    """A cache with only fresh, non-NaN data reports zero issues."""
    from src.cache_health import diagnose_cache

    cache = _make_cache(temp_data_dir, {"AAPL": _fresh_ticker(150.0), "MSFT": _fresh_ticker(400.0)})
    report = diagnose_cache(str(cache))

    assert report["total"] == 2
    assert report["nan_count"] == 0
    assert report["stale_count"] == 0
    assert report["nan_tickers"] == []
    assert report["stale_tickers"] == []


def test_diagnose_detects_nan_last_row(temp_data_dir):
    """A ticker whose last Close is NaN is flagged as nan."""
    from src.cache_health import diagnose_cache

    bad = _fresh_ticker(100.0)
    bad["history"]["Close"] = [100.0, float("nan")]
    bad["history_index"] = [_days_ago_iso(1), _days_ago_iso(0)]

    cache = _make_cache(temp_data_dir, {"BAD": bad})
    report = diagnose_cache(str(cache))

    assert report["nan_count"] == 1
    assert "BAD" in report["nan_tickers"]


def test_diagnose_detects_stale(temp_data_dir):
    """A ticker whose last date is >3 days old is flagged as stale."""
    from src.cache_health import diagnose_cache

    stale = _fresh_ticker(50.0)
    stale["history_index"] = [_days_ago_iso(10)]

    cache = _make_cache(temp_data_dir, {"OLD": stale})
    report = diagnose_cache(str(cache))

    assert report["stale_count"] == 1
    assert "OLD" in report["stale_tickers"]


def test_diagnose_missing_cache_returns_zeros(tmp_path):
    """diagnose_cache on a non-existent path returns a zeroed report, not a crash."""
    from src.cache_health import diagnose_cache

    report = diagnose_cache(str(tmp_path / "does-not-exist.json"))

    assert report["total"] == 0
    assert report["nan_count"] == 0
    assert report["stale_count"] == 0


def test_heal_trims_trailing_nan_close(temp_data_dir):
    """heal_cache drops trailing NaN Close rows from each ticker."""
    from src.cache_health import heal_cache

    entry = {
        "info": {"ticker": "TRIM"},
        "history": {
            "Close": [100.0, 101.0, float("nan")],
            "Open": [100.0, 101.0, 101.0],
            "High": [100.0, 101.0, 101.0],
            "Low": [100.0, 101.0, 101.0],
            "Volume": [1000, 1000, 1000],
        },
        "history_index": [_days_ago_iso(2), _days_ago_iso(1), _days_ago_iso(0)],
    }
    cache = _make_cache(temp_data_dir, {"TRIM": entry})

    with patch("src.pipeline.fetch_stock_data", return_value=None):
        report = heal_cache(str(cache), max_refetch=0)

    assert report["healed_nan"] == 1

    saved = json.loads(cache.read_text())
    closes = saved["TRIM"]["history"]["Close"]
    assert len(closes) == 2
    assert not math.isnan(closes[-1])


def test_heal_drops_ticker_with_all_nan(temp_data_dir):
    """If every Close is NaN, the ticker is removed from cache."""
    from src.cache_health import heal_cache

    entry = {
        "info": {"ticker": "DEAD"},
        "history": {
            "Close": [float("nan"), float("nan")],
            "Open": [float("nan"), float("nan")],
            "High": [float("nan"), float("nan")],
            "Low": [float("nan"), float("nan")],
            "Volume": [0, 0],
        },
        "history_index": [_days_ago_iso(1), _days_ago_iso(0)],
    }
    cache = _make_cache(temp_data_dir, {"DEAD": entry})

    with patch("src.pipeline.fetch_stock_data", return_value=None):
        report = heal_cache(str(cache), max_refetch=0)

    assert report["dropped"] == 1

    saved = json.loads(cache.read_text())
    assert "DEAD" not in saved


def test_heal_respects_max_refetch(temp_data_dir):
    """heal_cache only re-fetches up to max_refetch stale tickers."""
    from src.cache_health import heal_cache

    entries = {}
    for i in range(10):
        ticker = f"T{i}"
        stale = _fresh_ticker(100.0)
        stale["history_index"] = [_days_ago_iso(15)]
        entries[ticker] = stale
    cache = _make_cache(temp_data_dir, entries)

    fresh_return = _fresh_ticker(200.0)
    with patch("src.pipeline.fetch_stock_data", return_value=fresh_return) as mock_fetch:
        report = heal_cache(str(cache), max_refetch=3)

    assert mock_fetch.call_count == 3
    assert report["refetched"] == 3


def test_heal_report_shape(temp_data_dir):
    """heal_cache returns the documented keys even on an empty cache."""
    from src.cache_health import heal_cache

    cache = _make_cache(temp_data_dir, {})
    with patch("src.pipeline.fetch_stock_data", return_value=None):
        report = heal_cache(str(cache))

    assert set(report.keys()) == {"healed_nan", "refetched", "dropped", "total", "errors"}
    assert report["total"] == 0
    assert report["errors"] == []
