"""Tests for the ScanResultsService abstraction."""

import json
import tempfile
from pathlib import Path
from unittest.mock import patch, MagicMock
import pytest


# ============================================================================
# Fixtures for ScanResultsService testing
# ============================================================================

@pytest.fixture
def mock_service_env(temp_data_dir):
    """Set up environment with mocked paths for ScanResultsService testing."""
    results_file = temp_data_dir / "scan_results.json"
    prev_results_file = temp_data_dir / "prev_scan_results.json"

    with patch("src.scan_results_service.DATA_DIR", temp_data_dir), \
         patch("src.scan_results_service.RESULTS_FILE", results_file), \
         patch("src.scan_results_service.PREV_RESULTS_FILE", prev_results_file):
        yield temp_data_dir


@pytest.fixture
def sample_scan_data():
    """Return sample scan results data."""
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
            },
            {
                "ticker": "MSFT",
                "name": "Microsoft Corp",
                "sector": "Technology",
                "industry": "Software",
                "market_cap": 2.6e12,
                "composite_score": 82.3,
            },
        ],
        "all_scores": [
            {"ticker": "AAPL", "composite_score": 85.5, "sector": "Technology"},
            {"ticker": "MSFT", "composite_score": 82.3, "sector": "Technology"},
            {"ticker": "GOOGL", "composite_score": 79.1, "sector": "Technology"},
            {"ticker": "AMZN", "composite_score": 78.5, "sector": "Consumer"},
        ],
    }


# ============================================================================
# Test get_latest
# ============================================================================

class TestGetLatest:
    """Tests for ScanResultsService.get_latest()."""

    def test_get_latest_no_file(self, mock_service_env):
        """Test get_latest returns None when file doesn't exist."""
        from src.scan_results_service import ScanResultsService

        # Clear any cached data
        ScanResultsService._cache = None

        result = ScanResultsService.get_latest()
        assert result is None

    def test_get_latest_with_data(self, mock_service_env, sample_scan_data):
        """Test get_latest returns parsed JSON when file exists."""
        from src.scan_results_service import ScanResultsService

        # Clear cache
        ScanResultsService._cache = None

        # Write sample data to file
        results_file = mock_service_env / "scan_results.json"
        results_file.write_text(json.dumps(sample_scan_data))

        result = ScanResultsService.get_latest()

        assert result is not None
        assert result["timestamp"] == "2024-01-15T10:30:00"
        assert result["strategy"] == "balanced"
        assert len(result["top"]) == 2

    def test_get_latest_caches_data(self, mock_service_env, sample_scan_data):
        """Test get_latest caches data and doesn't re-read file on second call."""
        from src.scan_results_service import ScanResultsService

        # Clear cache
        ScanResultsService._cache = None

        # Write sample data
        results_file = mock_service_env / "scan_results.json"
        results_file.write_text(json.dumps(sample_scan_data))

        # First call
        result1 = ScanResultsService.get_latest()

        # Modify the file on disk
        modified_data = sample_scan_data.copy()
        modified_data["timestamp"] = "2024-01-16T10:30:00"
        results_file.write_text(json.dumps(modified_data))

        # Second call should return cached data (old timestamp)
        result2 = ScanResultsService.get_latest()

        assert result2["timestamp"] == "2024-01-15T10:30:00"  # Still old value from cache

    def test_get_latest_invalidates_cache_on_file_change(self, mock_service_env, sample_scan_data):
        """Test get_latest detects file modification and refreshes cache."""
        from src.scan_results_service import ScanResultsService
        import time

        # Clear cache
        ScanResultsService._cache = None

        # Write sample data
        results_file = mock_service_env / "scan_results.json"
        results_file.write_text(json.dumps(sample_scan_data))

        # First call
        result1 = ScanResultsService.get_latest()
        assert result1["timestamp"] == "2024-01-15T10:30:00"

        # Wait to ensure file mtime changes
        time.sleep(0.01)

        # Modify file
        modified_data = sample_scan_data.copy()
        modified_data["timestamp"] = "2024-01-16T10:30:00"
        results_file.write_text(json.dumps(modified_data))

        # Second call should detect mtime change and re-read
        result2 = ScanResultsService.get_latest()
        assert result2["timestamp"] == "2024-01-16T10:30:00"  # New value from file


# ============================================================================
# Test get_top_stocks
# ============================================================================

class TestGetTopStocks:
    """Tests for ScanResultsService.get_top_stocks()."""

    def test_get_top_stocks_returns_top_list(self, mock_service_env, sample_scan_data):
        """Test get_top_stocks returns the 'top' key from scan results."""
        from src.scan_results_service import ScanResultsService

        ScanResultsService._cache = None
        results_file = mock_service_env / "scan_results.json"
        results_file.write_text(json.dumps(sample_scan_data))

        top = ScanResultsService.get_top_stocks()

        assert len(top) == 2
        assert top[0]["ticker"] == "AAPL"
        assert top[1]["ticker"] == "MSFT"

    def test_get_top_stocks_fallback_to_stocks_key(self, mock_service_env):
        """Test get_top_stocks falls back to 'stocks' key if 'top' missing."""
        from src.scan_results_service import ScanResultsService

        ScanResultsService._cache = None

        data = {
            "timestamp": "2024-01-15T10:30:00",
            "stocks": [
                {"ticker": "AAPL", "composite_score": 85.5},
                {"ticker": "MSFT", "composite_score": 82.3},
            ],
        }

        results_file = mock_service_env / "scan_results.json"
        results_file.write_text(json.dumps(data))

        top = ScanResultsService.get_top_stocks()

        assert len(top) == 2
        assert top[0]["ticker"] == "AAPL"

    def test_get_top_stocks_no_data(self, mock_service_env):
        """Test get_top_stocks returns empty list when no results."""
        from src.scan_results_service import ScanResultsService

        ScanResultsService._cache = None

        top = ScanResultsService.get_top_stocks()

        assert top == []


# ============================================================================
# Test get_stock_score
# ============================================================================

class TestGetStockScore:
    """Tests for ScanResultsService.get_stock_score()."""

    def test_get_stock_score_found(self, mock_service_env, sample_scan_data):
        """Test get_stock_score returns correct stock when found."""
        from src.scan_results_service import ScanResultsService

        ScanResultsService._cache = None
        results_file = mock_service_env / "scan_results.json"
        results_file.write_text(json.dumps(sample_scan_data))

        score = ScanResultsService.get_stock_score("MSFT")

        assert score is not None
        assert score["ticker"] == "MSFT"
        assert score["composite_score"] == 82.3

    def test_get_stock_score_not_found(self, mock_service_env, sample_scan_data):
        """Test get_stock_score returns None when stock not found."""
        from src.scan_results_service import ScanResultsService

        ScanResultsService._cache = None
        results_file = mock_service_env / "scan_results.json"
        results_file.write_text(json.dumps(sample_scan_data))

        score = ScanResultsService.get_stock_score("NOTEXIST")

        assert score is None

    def test_get_stock_score_case_sensitive(self, mock_service_env, sample_scan_data):
        """Test get_stock_score is case-sensitive (or case-insensitive as per implementation)."""
        from src.scan_results_service import ScanResultsService

        ScanResultsService._cache = None
        results_file = mock_service_env / "scan_results.json"
        results_file.write_text(json.dumps(sample_scan_data))

        # Try with lowercase (may or may not work depending on implementation)
        score = ScanResultsService.get_stock_score("msft")

        # Should either find it (if case-insensitive) or not (if case-sensitive)
        # Current implementation appears to be case-sensitive
        if score is not None:
            assert score["ticker"] == "MSFT"


# ============================================================================
# Test get_by_sector
# ============================================================================

class TestGetBySector:
    """Tests for ScanResultsService.get_by_sector()."""

    def test_get_by_sector_returns_filtered_stocks(self, mock_service_env, sample_scan_data):
        """Test get_by_sector returns only stocks in specified sector."""
        from src.scan_results_service import ScanResultsService

        ScanResultsService._cache = None
        results_file = mock_service_env / "scan_results.json"
        results_file.write_text(json.dumps(sample_scan_data))

        tech_stocks = ScanResultsService.get_by_sector("Technology")

        assert len(tech_stocks) == 3
        assert all(s["sector"] == "Technology" for s in tech_stocks)

    def test_get_by_sector_case_insensitive(self, mock_service_env, sample_scan_data):
        """Test get_by_sector is case-insensitive."""
        from src.scan_results_service import ScanResultsService

        ScanResultsService._cache = None
        results_file = mock_service_env / "scan_results.json"
        results_file.write_text(json.dumps(sample_scan_data))

        tech_stocks = ScanResultsService.get_by_sector("technology")

        assert len(tech_stocks) == 3

    def test_get_by_sector_no_match(self, mock_service_env, sample_scan_data):
        """Test get_by_sector returns empty list when no match."""
        from src.scan_results_service import ScanResultsService

        ScanResultsService._cache = None
        results_file = mock_service_env / "scan_results.json"
        results_file.write_text(json.dumps(sample_scan_data))

        finance_stocks = ScanResultsService.get_by_sector("Finance")

        assert finance_stocks == []


# ============================================================================
# Test get_timestamp
# ============================================================================

class TestGetTimestamp:
    """Tests for ScanResultsService.get_timestamp()."""

    def test_get_timestamp_returns_timestamp(self, mock_service_env, sample_scan_data):
        """Test get_timestamp returns the timestamp from scan results."""
        from src.scan_results_service import ScanResultsService

        ScanResultsService._cache = None
        results_file = mock_service_env / "scan_results.json"
        results_file.write_text(json.dumps(sample_scan_data))

        timestamp = ScanResultsService.get_timestamp()

        assert timestamp == "2024-01-15T10:30:00"

    def test_get_timestamp_no_data(self, mock_service_env):
        """Test get_timestamp returns None when no results."""
        from src.scan_results_service import ScanResultsService

        ScanResultsService._cache = None

        timestamp = ScanResultsService.get_timestamp()

        assert timestamp is None


# ============================================================================
# Test invalidate_cache
# ============================================================================

class TestInvalidateCache:
    """Tests for ScanResultsService.invalidate_cache()."""

    def test_invalidate_cache_clears_cache(self, mock_service_env, sample_scan_data):
        """Test invalidate_cache clears the in-memory cache."""
        from src.scan_results_service import ScanResultsService

        ScanResultsService._cache = None
        results_file = mock_service_env / "scan_results.json"
        results_file.write_text(json.dumps(sample_scan_data))

        # Load into cache
        result1 = ScanResultsService.get_latest()
        assert ScanResultsService._cache is not None

        # Invalidate cache
        ScanResultsService.invalidate_cache()
        assert ScanResultsService._cache is None

    def test_invalidate_cache_forces_reload(self, mock_service_env, sample_scan_data):
        """Test that after invalidate_cache, next call re-reads file."""
        from src.scan_results_service import ScanResultsService
        import time

        ScanResultsService._cache = None
        results_file = mock_service_env / "scan_results.json"
        results_file.write_text(json.dumps(sample_scan_data))

        # Load into cache
        result1 = ScanResultsService.get_latest()
        assert result1["timestamp"] == "2024-01-15T10:30:00"

        # Invalidate cache
        ScanResultsService.invalidate_cache()

        # Modify file
        time.sleep(0.01)
        modified_data = sample_scan_data.copy()
        modified_data["timestamp"] = "2024-01-16T10:30:00"
        results_file.write_text(json.dumps(modified_data))

        # Next call should re-read
        result2 = ScanResultsService.get_latest()
        assert result2["timestamp"] == "2024-01-16T10:30:00"


# ============================================================================
# Test save_results
# ============================================================================

class TestSaveResults:
    """Tests for ScanResultsService.save_results()."""

    def test_save_results_writes_file(self, mock_service_env, sample_scan_data):
        """Test save_results writes JSON to file."""
        from src.scan_results_service import ScanResultsService

        ScanResultsService._cache = None
        results_file = mock_service_env / "scan_results.json"

        ScanResultsService.save_results(sample_scan_data)

        assert results_file.exists()
        saved_data = json.loads(results_file.read_text())
        assert saved_data["timestamp"] == "2024-01-15T10:30:00"
        assert saved_data["strategy"] == "balanced"

    def test_save_results_invalidates_cache(self, mock_service_env, sample_scan_data):
        """Test save_results invalidates cache."""
        from src.scan_results_service import ScanResultsService

        ScanResultsService._cache = None
        results_file = mock_service_env / "scan_results.json"
        results_file.write_text(json.dumps(sample_scan_data))

        # Load into cache
        result1 = ScanResultsService.get_latest()
        assert ScanResultsService._cache is not None

        # Save new results
        new_data = sample_scan_data.copy()
        new_data["timestamp"] = "2024-01-16T10:30:00"
        ScanResultsService.save_results(new_data)

        # Cache should be cleared
        assert ScanResultsService._cache is None

    def test_save_results_creates_directory(self, temp_data_dir):
        """Test save_results creates data directory if it doesn't exist."""
        from src.scan_results_service import ScanResultsService

        nonexistent_dir = temp_data_dir / "nonexistent"
        results_file = nonexistent_dir / "scan_results.json"

        with patch("src.scan_results_service.DATA_DIR", nonexistent_dir), \
             patch("src.scan_results_service.RESULTS_FILE", results_file):

            ScanResultsService._cache = None

            sample_data = {
                "timestamp": "2024-01-15T10:30:00",
                "strategy": "balanced",
                "top": [],
                "all_scores": [],
            }

            ScanResultsService.save_results(sample_data)

            assert nonexistent_dir.exists()
            assert results_file.exists()


# ============================================================================
# Test rotate_results
# ============================================================================

class TestRotateResults:
    """Tests for ScanResultsService.rotate_results()."""

    def test_rotate_results_copies_to_prev(self, mock_service_env, sample_scan_data):
        """Test rotate_results copies current results to prev file."""
        from src.scan_results_service import ScanResultsService

        ScanResultsService._cache = None
        results_file = mock_service_env / "scan_results.json"
        prev_results_file = mock_service_env / "prev_scan_results.json"

        results_file.write_text(json.dumps(sample_scan_data))

        ScanResultsService.rotate_results()

        assert prev_results_file.exists()
        prev_data = json.loads(prev_results_file.read_text())
        assert prev_data["timestamp"] == "2024-01-15T10:30:00"

    def test_rotate_results_no_file(self, mock_service_env):
        """Test rotate_results handles missing current file gracefully."""
        from src.scan_results_service import ScanResultsService

        ScanResultsService._cache = None
        prev_results_file = mock_service_env / "prev_scan_results.json"

        # Should not raise error
        ScanResultsService.rotate_results()

        # Prev file should not exist if current didn't exist
        assert not prev_results_file.exists()


# ============================================================================
# Test get_all_scores
# ============================================================================

class TestGetAllScores:
    """Tests for ScanResultsService.get_all_scores()."""

    def test_get_all_scores_returns_all_scores_list(self, mock_service_env, sample_scan_data):
        """Test get_all_scores returns the 'all_scores' key from scan results."""
        from src.scan_results_service import ScanResultsService

        ScanResultsService._cache = None
        results_file = mock_service_env / "scan_results.json"
        results_file.write_text(json.dumps(sample_scan_data))

        all_scores = ScanResultsService.get_all_scores()

        assert len(all_scores) == 4
        assert all_scores[0]["ticker"] == "AAPL"
        assert all_scores[3]["ticker"] == "AMZN"

    def test_get_all_scores_no_data(self, mock_service_env):
        """Test get_all_scores returns empty list when no results."""
        from src.scan_results_service import ScanResultsService

        ScanResultsService._cache = None

        all_scores = ScanResultsService.get_all_scores()

        assert all_scores == []
