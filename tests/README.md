# Stock Picker Integration Tests

This directory contains comprehensive integration tests for the stock picker application, covering the critical path: pipeline processing, API endpoints, and the scan results service.

## Overview

The test suite consists of three main test modules:

1. **test_pipeline_integration.py** - Tests for the stock screening pipeline
2. **test_api_endpoints.py** - Tests for FastAPI endpoints
3. **test_scan_results_service.py** - Tests for the ScanResultsService abstraction

All tests use mocking extensively to avoid hitting real APIs (yfinance, SEC EDGAR, etc.).

## Test Files

### conftest.py
Shared fixtures and mock data generators used across all test modules.

**Key fixtures:**
- `mock_stock_info` - Sample stock info dictionary
- `mock_stock_data` - Complete stock data with history
- `mock_history` - OHLCV DataFrame with 252 trading days
- `mock_spy_history` - SPY history for beta calculations
- `mock_scan_result` - Example scan result structure
- `temp_data_dir` - Temporary directory for file operations
- `mock_pipeline_env` - Environment setup for pipeline tests
- `mock_api_env` - Environment setup for API tests

### test_pipeline_integration.py

Tests core pipeline functionality without hitting real APIs.

**Key test classes:**

#### TestReconstructHist
- `test_reconstruct_hist_valid_data()` - Verifies DataFrame reconstruction from cached data
- `test_reconstruct_hist_drops_na()` - Ensures NaN values are properly dropped

#### TestAnalyzeSingle
- `test_analyze_single_returns_expected_keys()` - Verifies all required output keys
- `test_analyze_single_passes_growth_to_valuation()` - Growth score propagation
- `test_analyze_single_with_prev_data()` - Previous data handling for sell signals
- `test_analyze_single_with_market_regime()` - Market regime support

#### TestApplyFilters
Comprehensive filter testing:
- Sector filtering (case-insensitive)
- Market cap ranges (min/max)
- Ticker exclusion
- Industry filtering
- Strategy-specific filters (beta, dividend, revenue growth)
- Value trap detection (>10% revenue decline)
- Combined filter application

#### TestRunScan
- `test_run_scan_output_structure()` - Validates full output schema
- `test_run_scan_custom_sector_filter()` - Custom parameters

### test_api_endpoints.py

Tests all FastAPI endpoints using TestClient.

**Key test classes:**

#### TestHealthEndpoint
- `test_health_returns_ok()` - Basic health check

#### TestStrategiesEndpoint
- `test_strategies_returns_list()` - Strategy list endpoint

#### TestScanEndpoint
- `test_scan_sync_mode()` - Synchronous scan execution
- `test_scan_async_mode()` - Asynchronous scan (background task)
- `test_scan_with_sector_filter()` - Sector parameter
- `test_scan_with_market_cap_filters()` - Min/max cap parameters
- `test_scan_with_exclude_tickers()` - Ticker exclusion
- `test_scan_missing_api_key()` - Authentication

#### TestScanCachedEndpoint
- `test_scan_cached_no_data()` - Returns 404 when no cache exists
- `test_scan_cached_with_data()` - Returns cached results

#### TestStockDetailEndpoint
- `test_stock_detail_found()` - Found stock details
- `test_stock_detail_not_found()` - 404 for missing stock

#### TestAlertsEndpoint
- `test_alerts_returns_current_and_history()` - Alert structure

#### TestBacktestEndpoint
- `test_backtest_returns_results()` - Backtest output
- `test_backtest_with_date_range()` - Date range parameters

#### TestAPIKeyVerification
- `test_verify_api_key_valid()` - Valid key acceptance
- `test_verify_api_key_invalid()` - Invalid key rejection
- `test_verify_api_key_missing()` - Missing key handling

#### TestCompareStrategiesEndpoint
- `test_compare_strategies()` - Multi-strategy comparison

### test_scan_results_service.py

Tests the ScanResultsService abstraction layer.

**Key test classes:**

#### TestGetLatest
- `test_get_latest_no_file()` - Returns None when missing
- `test_get_latest_with_data()` - Parses JSON correctly
- `test_get_latest_caches_data()` - In-memory caching
- `test_get_latest_invalidates_cache_on_file_change()` - Cache invalidation on mtime change

#### TestGetTopStocks
- `test_get_top_stocks_returns_top_list()` - Returns 'top' key
- `test_get_top_stocks_fallback_to_stocks_key()` - Fallback logic
- `test_get_top_stocks_no_data()` - Empty list when no results

#### TestGetStockScore
- `test_get_stock_score_found()` - Find specific ticker
- `test_get_stock_score_not_found()` - Returns None for missing
- `test_get_stock_score_case_sensitive()` - Case sensitivity

#### TestGetBySector
- `test_get_by_sector_returns_filtered_stocks()` - Sector filtering
- `test_get_by_sector_case_insensitive()` - Case handling
- `test_get_by_sector_no_match()` - Empty list for no match

#### TestGetTimestamp
- `test_get_timestamp_returns_timestamp()` - Timestamp extraction
- `test_get_timestamp_no_data()` - Returns None when missing

#### TestInvalidateCache
- `test_invalidate_cache_clears_cache()` - Cache clearing
- `test_invalidate_cache_forces_reload()` - File re-reading after invalidation

#### TestSaveResults
- `test_save_results_writes_file()` - JSON file writing
- `test_save_results_invalidates_cache()` - Cache invalidation
- `test_save_results_creates_directory()` - Auto directory creation

#### TestRotateResults
- `test_rotate_results_copies_to_prev()` - File rotation
- `test_rotate_results_no_file()` - Graceful handling of missing file

#### TestGetAllScores
- `test_get_all_scores_returns_all_scores_list()` - All scores access
- `test_get_all_scores_no_data()` - Empty list when missing

## Running Tests

### Install test dependencies:
```bash
pip install -r requirements.txt
```

### Run all tests:
```bash
pytest tests/
```

### Run specific test file:
```bash
pytest tests/test_pipeline_integration.py
```

### Run specific test class:
```bash
pytest tests/test_pipeline_integration.py::TestApplyFilters
```

### Run specific test:
```bash
pytest tests/test_pipeline_integration.py::TestApplyFilters::test_apply_filters_sector
```

### Run with coverage:
```bash
pytest tests/ --cov=src --cov-report=html
```

### Run with verbose output:
```bash
pytest tests/ -v
```

### Run only fast tests (skip slow ones):
```bash
pytest tests/ -m "not slow"
```

## Test Design Principles

1. **No Real API Calls** - All external APIs (yfinance, SEC EDGAR, etc.) are mocked
2. **Isolated Tests** - Each test is independent and can run in any order
3. **Realistic Data** - Mock data reflects realistic stock data structures
4. **Comprehensive Coverage** - Tests cover happy paths, edge cases, and error conditions
5. **Clear Naming** - Test names describe what is being tested and expected outcome
6. **Fixtures** - Common setup is in conftest.py to avoid duplication

## Mock Data

The test suite includes realistic mock data:

- **MOCK_STOCK_INFO** - Representative tech stock info
- **MOCK_STOCK_INFO_LARGE_CAP** - Large market cap stock
- **MOCK_STOCK_INFO_SMALL_CAP** - Small market cap stock
- **MOCK_STOCK_INFO_HIGH_DECLINE** - Stock with revenue decline (value trap)
- **create_mock_history()** - Generates realistic OHLCV data
- **create_mock_spy_history()** - SPY data for beta calculations

## Future Enhancements

1. Add performance benchmarks for pipeline operations
2. Add integration tests with real (cached) API responses
3. Add regression tests for specific stocks/strategies
4. Add mutation testing to verify test quality
5. Add load testing for concurrent API requests
6. Add property-based testing with Hypothesis
