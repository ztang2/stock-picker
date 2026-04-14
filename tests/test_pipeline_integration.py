"""Integration tests for the stock screening pipeline."""

import json
import time
from pathlib import Path
from unittest.mock import patch, MagicMock, call
import pytest
import pandas as pd

import tests.conftest as _ct

MOCK_STOCK_INFO = _ct.MOCK_STOCK_INFO
MOCK_STOCK_INFO_LARGE_CAP = _ct.MOCK_STOCK_INFO_LARGE_CAP
MOCK_STOCK_INFO_SMALL_CAP = _ct.MOCK_STOCK_INFO_SMALL_CAP
MOCK_STOCK_INFO_HIGH_DECLINE = _ct.MOCK_STOCK_INFO_HIGH_DECLINE
create_mock_stock_data = _ct.create_mock_stock_data
create_mock_history = _ct.create_mock_history
create_mock_spy_history = _ct.create_mock_spy_history


# ============================================================================
# Fixtures for pipeline testing
# ============================================================================

@pytest.fixture
def mock_scoring_functions():
    """Mock all the individual scoring functions."""
    with patch("src.pipeline.score_fundamentals") as mock_fund, \
         patch("src.pipeline.score_valuation") as mock_val, \
         patch("src.pipeline.score_technicals") as mock_tech, \
         patch("src.pipeline.score_risk") as mock_risk, \
         patch("src.pipeline.score_growth") as mock_growth, \
         patch("src.pipeline.score_analyst_sentiment") as mock_sentiment, \
         patch("src.pipeline.compute_momentum") as mock_momentum, \
         patch("src.pipeline.compute_sell_signals") as mock_sell, \
         patch("src.pipeline.compute_sector_relative_scores") as mock_sector, \
         patch("src.pipeline.get_strategy") as mock_strat:

        # Set reasonable defaults
        mock_fund.return_value = {"score": 75, "details": {}}
        mock_val.return_value = {"score": 80, "details": {}}
        mock_tech.return_value = {"score": 85, "details": {}}
        mock_risk.return_value = {"score": 70, "beta": 1.2, "details": {}}
        mock_growth.return_value = {"score": 72, "revenue_growth": 0.12, "details": {}}
        mock_sentiment.return_value = {"score": 65, "details": {}}
        mock_momentum.return_value = {
            "score": 78,
            "entry_signal": "BUY",
            "resistance": 155.0,
            "adx": 35,
            "details": {}
        }
        mock_sell.return_value = {"signals": []}
        mock_sector.return_value = {}
        mock_strat.return_value = {"name": "balanced", "weights": {}}

        yield {
            "fundamentals": mock_fund,
            "valuation": mock_val,
            "technicals": mock_tech,
            "risk": mock_risk,
            "growth": mock_growth,
            "sentiment": mock_sentiment,
            "momentum": mock_momentum,
            "sell_signals": mock_sell,
            "sector": mock_sector,
            "strategy": mock_strat,
        }


# ============================================================================
# Test _reconstruct_hist
# ============================================================================

class TestReconstructHist:
    """Tests for the _reconstruct_hist function."""

    def test_reconstruct_hist_valid_data(self):
        """Test reconstructing history from cached data."""
        from src.pipeline import _reconstruct_hist

        data = create_mock_stock_data()
        hist = _reconstruct_hist(data)

        assert isinstance(hist, pd.DataFrame)
        assert "Close" in hist.columns
        assert len(hist) > 0
        assert hist.index.name == "Date" or hist.index.tz == "UTC"

    def test_reconstruct_hist_drops_na(self):
        """Test that _reconstruct_hist drops rows with NaN Close prices."""
        from src.pipeline import _reconstruct_hist

        data = create_mock_stock_data()
        # Inject some NaN values
        data["history"]["Close"][0] = None
        data["history"]["Close"][5] = None

        hist = _reconstruct_hist(data)

        # Should have fewer rows due to dropna
        original_count = len(data["history"]["Close"])
        assert len(hist) < original_count
        assert hist["Close"].notna().all()


# ============================================================================
# Test analyze_single
# ============================================================================

class TestAnalyzeSingle:
    """Tests for the analyze_single function."""

    def test_analyze_single_returns_expected_keys(self, mock_scoring_functions):
        """Test that analyze_single returns all required keys."""
        from src.pipeline import analyze_single

        stock_data = create_mock_stock_data(MOCK_STOCK_INFO)
        spy_hist = create_mock_spy_history()

        result = analyze_single(
            ticker="TEST",
            data=stock_data,
            spy_hist=spy_hist,
            regime="bull"
        )

        # Check all required top-level keys
        required_keys = {
            "ticker", "name", "sector", "industry", "market_cap",
            "dividend_yield", "fundamentals", "valuation", "technicals",
            "risk", "growth", "sentiment", "momentum", "sell_signals"
        }
        assert set(result.keys()) >= required_keys

        # Check values
        assert result["ticker"] == "TEST"
        assert result["name"] == "Test Corp"
        assert result["sector"] == "Technology"
        assert isinstance(result["fundamentals"], dict)
        assert isinstance(result["valuation"], dict)

    def test_analyze_single_passes_growth_to_valuation(self, mock_scoring_functions):
        """Test that growth score is passed to valuation scorer."""
        from src.pipeline import analyze_single

        stock_data = create_mock_stock_data()
        mock_growth = mock_scoring_functions["growth"]
        mock_growth.return_value = {"score": 75, "revenue_growth": 0.15}

        mock_val = mock_scoring_functions["valuation"]
        mock_val.return_value = {"score": 80}

        analyze_single("TEST", stock_data)

        # Verify valuation was called with growth_score
        mock_val.assert_called_once()
        call_kwargs = mock_val.call_args[1]
        assert "growth_score" in call_kwargs
        assert call_kwargs["growth_score"] == 75

    def test_analyze_single_with_prev_data(self, mock_scoring_functions):
        """Test that previous data is used for sell signal comparison."""
        from src.pipeline import analyze_single

        stock_data = create_mock_stock_data()
        prev_data = {
            "fundamentals": {"score": 70},
            "momentum": {"entry_signal": "BUY"}
        }

        mock_sell = mock_scoring_functions["sell_signals"]
        analyze_single("TEST", stock_data, prev_data=prev_data)

        # Verify sell_signals was called with prev data
        mock_sell.assert_called_once()
        call_kwargs = mock_sell.call_args[1]
        assert call_kwargs["prev_fundamentals_score"] == 70
        assert call_kwargs["prev_signal"] == "BUY"

    def test_analyze_single_with_market_regime(self, mock_scoring_functions):
        """Test that market regime is passed to sell signal scorer."""
        from src.pipeline import analyze_single

        stock_data = create_mock_stock_data()
        mock_sell = mock_scoring_functions["sell_signals"]

        analyze_single("TEST", stock_data, regime="bear")

        mock_sell.assert_called_once()
        call_kwargs = mock_sell.call_args[1]
        assert call_kwargs["regime"] == "bear"


# ============================================================================
# Test apply_filters
# ============================================================================

class TestApplyFilters:
    """Tests for the apply_filters function."""

    def test_apply_filters_no_filters(self):
        """Test that apply_filters returns all stocks when no filters applied."""
        from src.pipeline import apply_filters

        results = [
            {"ticker": "A", "sector": "Tech", "market_cap": 100e9},
            {"ticker": "B", "sector": "Health", "market_cap": 50e9},
        ]

        filtered = apply_filters(results)
        assert len(filtered) == 2

    def test_apply_filters_sector(self):
        """Test sector filtering."""
        from src.pipeline import apply_filters

        results = [
            {"ticker": "A", "sector": "Technology", "market_cap": 100e9},
            {"ticker": "B", "sector": "Healthcare", "market_cap": 50e9},
            {"ticker": "C", "sector": "Technology", "market_cap": 75e9},
        ]

        filtered = apply_filters(results, sector="Technology")
        assert len(filtered) == 2
        assert all(r["sector"] == "Technology" for r in filtered)

    def test_apply_filters_sector_case_insensitive(self):
        """Test that sector filtering is case-insensitive."""
        from src.pipeline import apply_filters

        results = [
            {"ticker": "A", "sector": "Technology", "market_cap": 100e9},
            {"ticker": "B", "sector": "healthcare", "market_cap": 50e9},
        ]

        filtered = apply_filters(results, sector="TECHNOLOGY")
        assert len(filtered) == 1
        assert filtered[0]["ticker"] == "A"

    def test_apply_filters_market_cap_min(self):
        """Test minimum market cap filtering."""
        from src.pipeline import apply_filters

        results = [
            {"ticker": "A", "sector": "Tech", "market_cap": 100e9},
            {"ticker": "B", "sector": "Tech", "market_cap": 50e9},
            {"ticker": "C", "sector": "Tech", "market_cap": 10e9},
        ]

        filtered = apply_filters(results, min_cap=25e9)
        assert len(filtered) == 2
        assert all(r["market_cap"] >= 25e9 for r in filtered)

    def test_apply_filters_market_cap_max(self):
        """Test maximum market cap filtering."""
        from src.pipeline import apply_filters

        results = [
            {"ticker": "A", "sector": "Tech", "market_cap": 100e9},
            {"ticker": "B", "sector": "Tech", "market_cap": 50e9},
            {"ticker": "C", "sector": "Tech", "market_cap": 10e9},
        ]

        filtered = apply_filters(results, max_cap=75e9)
        assert len(filtered) == 2
        assert all(r["market_cap"] <= 75e9 for r in filtered)

    def test_apply_filters_market_cap_range(self):
        """Test both min and max market cap filtering."""
        from src.pipeline import apply_filters

        results = [
            {"ticker": "A", "sector": "Tech", "market_cap": 100e9},
            {"ticker": "B", "sector": "Tech", "market_cap": 50e9},
            {"ticker": "C", "sector": "Tech", "market_cap": 10e9},
        ]

        filtered = apply_filters(results, min_cap=25e9, max_cap=75e9)
        assert len(filtered) == 1
        assert filtered[0]["ticker"] == "B"

    def test_apply_filters_exclude_tickers(self):
        """Test ticker exclusion."""
        from src.pipeline import apply_filters

        results = [
            {"ticker": "AAPL", "sector": "Tech", "market_cap": 100e9},
            {"ticker": "MSFT", "sector": "Tech", "market_cap": 90e9},
            {"ticker": "GOOGL", "sector": "Tech", "market_cap": 80e9},
        ]

        filtered = apply_filters(results, exclude_tickers=["AAPL", "GOOGL"])
        assert len(filtered) == 1
        assert filtered[0]["ticker"] == "MSFT"

    def test_apply_filters_exclude_case_insensitive(self):
        """Test that ticker exclusion is case-insensitive."""
        from src.pipeline import apply_filters

        results = [
            {"ticker": "AAPL", "sector": "Tech", "market_cap": 100e9},
            {"ticker": "MSFT", "sector": "Tech", "market_cap": 90e9},
        ]

        filtered = apply_filters(results, exclude_tickers=["aapl"])
        assert len(filtered) == 1
        assert filtered[0]["ticker"] == "MSFT"

    def test_apply_filters_value_trap_revenue_decline(self):
        """Test value trap filter (>10% revenue decline)."""
        from src.pipeline import apply_filters

        results = [
            {"ticker": "A", "growth": {"revenue_growth": 0.10}},
            {"ticker": "B", "growth": {"revenue_growth": -0.05}},
            {"ticker": "C", "growth": {"revenue_growth": -0.15}},  # >10% decline
            {"ticker": "D", "growth": None},
        ]

        filtered = apply_filters(results)
        # Should exclude C (>10% decline)
        assert len(filtered) == 3
        assert all(r["ticker"] != "C" for r in filtered)

    def test_apply_filters_industry(self):
        """Test industry filtering."""
        from src.pipeline import apply_filters

        results = [
            {"ticker": "A", "industry": "Software"},
            {"ticker": "B", "industry": "Hardware"},
            {"ticker": "C", "industry": "Software"},
        ]

        filtered = apply_filters(results, industries=["Software"])
        assert len(filtered) == 2
        assert all(r["industry"] == "Software" for r in filtered)

    def test_apply_filters_strategy_filters_max_beta(self):
        """Test strategy filter for maximum beta."""
        from src.pipeline import apply_filters

        results = [
            {"ticker": "A", "risk": {"beta": 0.8}},
            {"ticker": "B", "risk": {"beta": 1.2}},
            {"ticker": "C", "risk": {"beta": 1.5}},
        ]

        strategy_filters = {"max_beta": 1.1}
        filtered = apply_filters(results, strategy_filters=strategy_filters)
        assert len(filtered) == 1
        assert filtered[0]["ticker"] == "A"

    def test_apply_filters_strategy_filters_min_dividend(self):
        """Test strategy filter for minimum dividend yield."""
        from src.pipeline import apply_filters

        results = [
            {"ticker": "A", "info_cache": {"dividendYield": 0.05}},
            {"ticker": "B", "info_cache": {"dividendYield": 0.02}},
            {"ticker": "C", "dividend_yield": 0.03},
        ]

        strategy_filters = {"min_dividend_yield": 0.03}
        filtered = apply_filters(results, strategy_filters=strategy_filters)
        assert len(filtered) == 2

    def test_apply_filters_strategy_filters_min_revenue_growth(self):
        """Test strategy filter for minimum revenue growth."""
        from src.pipeline import apply_filters

        results = [
            {"ticker": "A", "growth": {"revenue_growth": 0.20}},
            {"ticker": "B", "growth": {"revenue_growth": 0.05}},
            {"ticker": "C", "growth": {"revenue_growth": -0.05}},
        ]

        strategy_filters = {"min_revenue_growth": 0.10}
        filtered = apply_filters(results, strategy_filters=strategy_filters)
        assert len(filtered) == 1
        assert filtered[0]["ticker"] == "A"

    def test_apply_filters_combined(self):
        """Test multiple filters applied together."""
        from src.pipeline import apply_filters

        results = [
            {"ticker": "AAPL", "sector": "Technology", "market_cap": 200e9, "growth": {"revenue_growth": 0.12}},
            {"ticker": "MSFT", "sector": "Technology", "market_cap": 180e9, "growth": {"revenue_growth": 0.15}},
            {"ticker": "XOM", "sector": "Energy", "market_cap": 400e9, "growth": {"revenue_growth": -0.05}},
            {"ticker": "JNJ", "sector": "Healthcare", "market_cap": 350e9, "growth": {"revenue_growth": 0.08}},
        ]

        filtered = apply_filters(
            results,
            sector="Technology",
            min_cap=100e9,
            exclude_tickers=["AAPL"]
        )

        assert len(filtered) == 1
        assert filtered[0]["ticker"] == "MSFT"


# ============================================================================
# Test run_scan
# ============================================================================

class TestRunScan:
    """Tests for the run_scan function."""

    @patch("src.pipeline.load_config")
    @patch("src.pipeline.detect_market_regime")
    @patch("src.pipeline.get_sp500_tickers")
    @patch("src.pipeline.fetch_stock_data")
    @patch("src.pipeline.analyze_single")
    @patch("src.pipeline.apply_filters")
    @patch("src.pipeline.compute_composite")
    @patch("src.pipeline.update_streaks")
    @patch("src.pipeline.add_streaks_to_results")
    @patch("src.pipeline.ScanResultsService")
    def test_run_scan_output_structure(
        self,
        mock_service,
        mock_add_streaks,
        mock_update_streaks,
        mock_composite,
        mock_apply_filters,
        mock_analyze,
        mock_fetch,
        mock_tickers,
        mock_regime,
        mock_config,
        temp_data_dir,
    ):
        """Test that run_scan produces the expected output structure."""
        from src.pipeline import run_scan

        # Setup mocks
        mock_config.return_value = {"filters": {}, "strategies": {}}
        mock_regime.return_value = "bull"
        mock_tickers.return_value = ["TEST1", "TEST2"]
        mock_fetch.side_effect = [
            create_mock_stock_data(MOCK_STOCK_INFO),
            create_mock_stock_data(MOCK_STOCK_INFO_LARGE_CAP),
        ]

        # Mock analyze_single results
        analyze_results = [
            {
                "ticker": "TEST1",
                "name": "Test Corp 1",
                "sector": "Technology",
                "industry": "Software",
                "market_cap": 50e9,
                "composite_score": 85.5,
                "fundamentals": {"score": 80},
                "valuation": {"score": 75},
                "technicals": {"score": 90},
                "risk": {"score": 85},
            },
            {
                "ticker": "TEST2",
                "name": "Test Corp 2",
                "sector": "Technology",
                "industry": "Software",
                "market_cap": 100e9,
                "composite_score": 82.3,
                "fundamentals": {"score": 85},
                "valuation": {"score": 80},
                "technicals": {"score": 85},
                "risk": {"score": 78},
            },
        ]
        mock_analyze.side_effect = analyze_results

        # Mock apply_filters to return all results
        mock_apply_filters.return_value = analyze_results

        # Mock compute_composite to add composite_score
        def add_scores(results, *args, **kwargs):
            for r in results:
                r["composite_score"] = 85.0
            return results

        mock_composite.side_effect = add_scores

        mock_update_streaks.return_value = analyze_results
        mock_add_streaks.return_value = analyze_results

        # Run scan
        result = run_scan()

        # Verify output structure
        assert isinstance(result, dict)
        assert "timestamp" in result
        assert "strategy" in result
        assert "market_regime" in result
        assert "top" in result
        assert "all_scores" in result
        assert "stocks_analyzed" in result
        assert "stocks_after_filter" in result

        # Verify content
        assert result["market_regime"] == "bull"
        assert result["stocks_analyzed"] == 2
        assert result["stocks_after_filter"] == 2
        assert len(result["top"]) <= 20  # Top should be at most 20
        assert len(result["all_scores"]) == 2

    @patch("src.pipeline.load_config")
    @patch("src.pipeline.get_sp500_tickers")
    def test_run_scan_custom_sector_filter(
        self,
        mock_tickers,
        mock_config,
        temp_data_dir,
    ):
        """Test that run_scan respects custom sector parameter."""
        from src.pipeline import run_scan

        mock_config.return_value = {"filters": {}, "strategies": {}}
        mock_tickers.return_value = []

        # Should not raise error
        with patch("src.pipeline.detect_market_regime"), \
             patch("src.pipeline.apply_filters") as mock_filters:
            mock_filters.return_value = []
            result = run_scan(sector="Technology")

        # Verify apply_filters was called with sector parameter
        assert mock_filters.called
        call_kwargs = mock_filters.call_args[1]
        assert call_kwargs.get("sector") == "Technology"
