"""API endpoint tests using FastAPI TestClient."""

import json
import time
from pathlib import Path
from unittest.mock import patch, MagicMock
import pytest
from fastapi.testclient import TestClient


# ============================================================================
# Fixtures for API testing
# ============================================================================

@pytest.fixture
def client(mock_api_env):
    """Create a TestClient for the API."""
    from src.api import app
    return TestClient(app)


@pytest.fixture
def mock_scan_results(temp_data_dir):
    """Create mock scan results file."""
    results = {
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

    results_file = temp_data_dir / "scan_results.json"
    results_file.write_text(json.dumps(results, indent=2))

    return results


# ============================================================================
# Test Health Endpoint
# ============================================================================

class TestHealthEndpoint:
    """Tests for GET /health endpoint."""

    def test_health_returns_ok(self, client):
        """Test that /health returns 200 OK."""
        response = client.get("/health")
        assert response.status_code == 200
        assert response.json() == {"status": "ok"}


# ============================================================================
# Test Strategies Endpoint
# ============================================================================

class TestStrategiesEndpoint:
    """Tests for GET /strategies endpoint."""

    @patch("src.api.list_strategies")
    def test_strategies_returns_list(self, mock_list_strat, client):
        """Test that /strategies returns a list of strategies."""
        mock_list_strat.return_value = [
            {"name": "conservative", "description": "Low risk"},
            {"name": "balanced", "description": "Medium risk"},
            {"name": "aggressive", "description": "High risk"},
        ]

        response = client.get("/strategies")
        assert response.status_code == 200
        data = response.json()
        assert "strategies" in data
        assert len(data["strategies"]) == 3


# ============================================================================
# Test Scan Endpoint
# ============================================================================

class TestScanEndpoint:
    """Tests for /scan endpoint."""

    @patch("src.api.run_scan")
    @patch("src.api.load_config")
    def test_scan_sync_mode(self, mock_config, mock_run_scan, client):
        """Test /scan with sync=true returns results immediately."""
        mock_config.return_value = {"filters": {}}
        mock_run_scan.return_value = {
            "timestamp": "2024-01-15T10:30:00",
            "strategy": "balanced",
            "top": [],
            "all_scores": [],
            "stocks_analyzed": 500,
            "stocks_after_filter": 100,
        }

        response = client.get("/scan?sync=true&strategy=balanced", headers={"X-API-Key": "test-key-12345"})

        assert response.status_code == 200
        data = response.json()
        assert "timestamp" in data
        assert data["strategy"] == "balanced"

    @patch("src.api.run_scan")
    @patch("src.api.load_config")
    def test_scan_async_mode(self, mock_config, mock_run_scan, client):
        """Test /scan without sync parameter starts background task."""
        mock_config.return_value = {"filters": {}}

        response = client.get("/scan?strategy=balanced", headers={"X-API-Key": "test-key-12345"})

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "started"

    def test_scan_missing_api_key(self, client):
        """Test /scan without API key returns 401 when key is required."""
        response = client.get("/scan?sync=true")
        assert response.status_code == 401

    @patch("src.api.load_config")
    def test_scan_with_sector_filter(self, mock_config, client):
        """Test /scan accepts sector parameter."""
        mock_config.return_value = {"filters": {}}

        with patch("src.api.run_scan") as mock_run_scan:
            mock_run_scan.return_value = {
                "timestamp": "2024-01-15T10:30:00",
                "strategy": "balanced",
                "top": [],
                "all_scores": [],
                "stocks_analyzed": 100,
                "stocks_after_filter": 20,
            }

            response = client.get(
                "/scan?sync=true&sector=Technology",
                headers={"X-API-Key": "test-key-12345"}
            )

            assert response.status_code == 200
            mock_run_scan.assert_called_once()
            call_kwargs = mock_run_scan.call_args[1]
            assert call_kwargs["sector"] == "Technology"

    @patch("src.api.load_config")
    def test_scan_with_market_cap_filters(self, mock_config, client):
        """Test /scan accepts min_cap and max_cap parameters."""
        mock_config.return_value = {"filters": {}}

        with patch("src.api.run_scan") as mock_run_scan:
            mock_run_scan.return_value = {
                "timestamp": "2024-01-15T10:30:00",
                "strategy": "balanced",
                "top": [],
                "all_scores": [],
                "stocks_analyzed": 100,
                "stocks_after_filter": 20,
            }

            response = client.get(
                "/scan?sync=true&min_cap=10000000000&max_cap=100000000000",
                headers={"X-API-Key": "test-key-12345"}
            )

            assert response.status_code == 200
            mock_run_scan.assert_called_once()
            call_kwargs = mock_run_scan.call_args[1]
            assert call_kwargs["min_cap"] == 10000000000
            assert call_kwargs["max_cap"] == 100000000000

    @patch("src.api.load_config")
    def test_scan_with_exclude_tickers(self, mock_config, client):
        """Test /scan accepts exclude parameter."""
        mock_config.return_value = {"filters": {}}

        with patch("src.api.run_scan") as mock_run_scan:
            mock_run_scan.return_value = {
                "timestamp": "2024-01-15T10:30:00",
                "strategy": "balanced",
                "top": [],
                "all_scores": [],
                "stocks_analyzed": 100,
                "stocks_after_filter": 20,
            }

            response = client.get(
                "/scan?sync=true&exclude=AAPL,MSFT,GOOGL",
                headers={"X-API-Key": "test-key-12345"}
            )

            assert response.status_code == 200
            mock_run_scan.assert_called_once()
            call_kwargs = mock_run_scan.call_args[1]
            assert "AAPL" in call_kwargs["exclude_tickers"]
            assert "MSFT" in call_kwargs["exclude_tickers"]
            assert "GOOGL" in call_kwargs["exclude_tickers"]


# ============================================================================
# Test Scan Status Endpoint
# ============================================================================

class TestScanStatusEndpoint:
    """Tests for /scan/status endpoint."""

    def test_scan_status_returns_status(self, client):
        """Test /scan/status returns current scan status."""
        response = client.get("/scan/status")
        assert response.status_code == 200
        data = response.json()
        assert "running" in data


# ============================================================================
# Test Scan Cached Endpoint
# ============================================================================

class TestScanCachedEndpoint:
    """Tests for /scan/cached endpoint."""

    def test_scan_cached_no_data(self, client):
        """Test /scan/cached returns 404 when no cached results."""
        response = client.get("/scan/cached")
        assert response.status_code == 404

    def test_scan_cached_with_data(self, client, mock_scan_results, temp_data_dir):
        """Test /scan/cached returns cached results when available."""
        with patch("src.api.RESULTS_FILE", temp_data_dir / "scan_results.json"):
            response = client.get("/scan/cached")

            assert response.status_code == 200
            data = response.json()
            assert data["timestamp"] == "2024-01-15T10:30:00"
            assert data["strategy"] == "balanced"
            assert len(data["top"]) == 2


# ============================================================================
# Test Stock Detail Endpoint
# ============================================================================

class TestStockDetailEndpoint:
    """Tests for /stock/{ticker} endpoint."""

    @patch("src.api.get_stock_detail")
    def test_stock_detail_found(self, mock_detail, client):
        """Test /stock/{ticker} returns stock details when found."""
        mock_detail.return_value = {
            "ticker": "AAPL",
            "name": "Apple Inc",
            "sector": "Technology",
            "market_cap": 2.8e12,
            "fundamentals": {"score": 80},
            "valuation": {"score": 75},
            "technicals": {"score": 90},
            "risk": {"score": 85},
        }

        response = client.get("/stock/AAPL")

        assert response.status_code == 200
        data = response.json()
        assert data["ticker"] == "AAPL"
        assert data["name"] == "Apple Inc"

    @patch("src.api.get_stock_detail")
    def test_stock_detail_not_found(self, mock_detail, client):
        """Test /stock/{ticker} returns 404 when stock not found."""
        mock_detail.return_value = None

        response = client.get("/stock/NOTEXIST")

        assert response.status_code == 404


# ============================================================================
# Test Alerts Endpoint
# ============================================================================

class TestAlertsEndpoint:
    """Tests for /alerts endpoint."""

    @patch("src.api.check_alerts")
    @patch("src.api.get_alert_history")
    def test_alerts_returns_current_and_history(self, mock_history, mock_current, client):
        """Test /alerts returns both current alerts and history."""
        mock_current.return_value = [
            {"ticker": "AAPL", "alert_type": "momentum", "severity": "high"}
        ]
        mock_history.return_value = [
            {"ticker": "AAPL", "alert_type": "momentum", "severity": "high", "timestamp": "2024-01-15T10:00:00"}
        ]

        response = client.get("/alerts")

        assert response.status_code == 200
        data = response.json()
        assert "current" in data
        assert "history" in data
        assert len(data["current"]) == 1
        assert len(data["history"]) == 1


# ============================================================================
# Test Backtest Endpoint
# ============================================================================

class TestBacktestEndpoint:
    """Tests for /backtest endpoint."""

    @patch("src.api.run_backtest")
    def test_backtest_returns_results(self, mock_backtest, client):
        """Test /backtest returns backtest results."""
        mock_backtest.return_value = {
            "strategy": "balanced",
            "start_date": "2023-01-01",
            "end_date": "2024-01-01",
            "total_return": 0.15,
            "sharpe_ratio": 1.5,
            "max_drawdown": 0.10,
            "trades": [],
        }

        response = client.get(
            "/backtest?strategy=balanced",
            headers={"X-API-Key": "test-key-12345"}
        )

        assert response.status_code == 200
        data = response.json()
        assert data["strategy"] == "balanced"
        assert "total_return" in data
        assert "sharpe_ratio" in data

    @patch("src.api.run_backtest")
    def test_backtest_with_date_range(self, mock_backtest, client):
        """Test /backtest accepts start_date and end_date parameters."""
        mock_backtest.return_value = {
            "strategy": "balanced",
            "start_date": "2023-01-01",
            "end_date": "2024-01-01",
            "total_return": 0.15,
            "sharpe_ratio": 1.5,
            "max_drawdown": 0.10,
            "trades": [],
        }

        response = client.get(
            "/backtest?strategy=balanced&start_date=2023-01-01&end_date=2024-01-01",
            headers={"X-API-Key": "test-key-12345"}
        )

        assert response.status_code == 200


# ============================================================================
# Test API Key Verification
# ============================================================================

class TestAPIKeyVerification:
    """Tests for API key verification."""

    def test_verify_api_key_valid(self, client):
        """Test that valid API key is accepted."""
        with patch("src.api.run_scan"):
            response = client.get("/scan?sync=true", headers={"X-API-Key": "test-key-12345"})
            # Should not return 401
            assert response.status_code != 401

    def test_verify_api_key_invalid(self, client):
        """Test that invalid API key returns 401."""
        response = client.get("/scan?sync=true", headers={"X-API-Key": "wrong-key"})
        assert response.status_code == 401

    def test_verify_api_key_missing(self, client):
        """Test that missing API key returns 401."""
        response = client.get("/scan?sync=true")
        assert response.status_code == 401


# ============================================================================
# Test Compare Strategies Endpoint
# ============================================================================

class TestCompareStrategiesEndpoint:
    """Tests for /compare endpoint."""

    @patch("src.api.run_scan")
    @patch("src.api.load_config")
    @patch("src.api.get_strategy")
    def test_compare_strategies(self, mock_get_strat, mock_config, mock_scan, client):
        """Test /compare runs multiple strategies and returns comparison."""
        mock_config.return_value = {"filters": {}}
        mock_get_strat.return_value = {"name": "test", "weights": {}}

        def scan_side_effect(*args, **kwargs):
            strategy = kwargs.get("strategy", "balanced")
            return {
                "timestamp": "2024-01-15T10:30:00",
                "strategy": strategy,
                "top": [],
                "stocks_analyzed": 500,
                "stocks_after_filter": 100,
            }

        mock_scan.side_effect = scan_side_effect

        response = client.get("/compare?strategies=conservative,balanced,aggressive")

        assert response.status_code == 200
        data = response.json()
        assert "comparison" in data
        assert len(data["comparison"]) == 3
