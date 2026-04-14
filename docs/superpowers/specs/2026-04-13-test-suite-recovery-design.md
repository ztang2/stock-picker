# Test Suite Recovery — Design Spec

**Date:** 2026-04-13
**Status:** Approved
**Part of:** Systematic improvement pass (Spec 1 of 3). Specs 2 (observability) and 3 (model quality) land on top of this foundation.

## Goal

Restore the test suite to a trustworthy green-on-local state so that subsequent model and ops changes can ship with a safety net. Currently 5 of 8 test modules fail at collection time and 5 recently-added modules have no coverage.

## Current State

`pytest --collect-only` output:

```
ERROR tests/test_api_endpoints.py           — ModuleNotFoundError: No module named 'api'
ERROR tests/test_pipeline_integration.py    — ModuleNotFoundError: No module named 'pipeline'
ERROR tests/test_profit_taker.py            — ModuleNotFoundError: No module named 'profit_taker'
ERROR tests/test_scan_results_service.py    — ModuleNotFoundError: No module named 'conftest'
ERROR tests/test_sell_signals.py            — ModuleNotFoundError: No module named 'sell_signals'
3 tests collected, 5 errors
```

`pytest.ini` sets `pythonpath = .` which makes the repo root importable but not `src/`. Tests import their target modules directly (`from sell_signals import …`), which fails.

One file (`test_scan_results_service.py`) also does `from conftest import temp_data_dir` — conftest fixtures are injected by pytest, not imported, so this line fails independently of the pythonpath issue.

## Workstream 1: Fix Collection

### 1.1 Add `src/` to pythonpath

Edit `pytest.ini`:

```ini
[pytest]
python_files = test_*.py
python_classes = Test*
python_functions = test_*
testpaths = tests
pythonpath = . src          # was: pythonpath = .
```

This allows `from sell_signals import …` and `from api import …` to resolve without modifying a single test file.

### 1.2 Remove direct conftest import

In `tests/test_scan_results_service.py`:

```python
# REMOVE
from conftest import temp_data_dir

# Use fixture as a function parameter (pytest auto-injects)
def test_something(temp_data_dir):
    ...
```

### 1.3 Log file hygiene

- Add `data/server.log`, `data/server.error.log`, `server.log`, `logs/cache-refresh*.log` to `.gitignore` (if not already covered).
- Delete the stray `server.log` in repo root.
- Do NOT touch `data/server.log` contents — that's for Spec 2 (log rotation).

### 1.4 Verify

```bash
python3 -m pytest --collect-only -q
# Expect: "N tests collected, 0 errors"

python3 -m pytest
# Expect: all collected tests pass
```

## Workstream 2: Coverage for Recently-Added Modules

Tests written for modules merged in the last ~30 days that currently have no coverage. Use fixtures from `tests/conftest.py` (already has rich `MOCK_STOCK_INFO`, etc.).

### 2.1 `src/cache_health.py` — `tests/test_cache_health.py`

Public surface: `heal_cache(cache_path) -> dict` returning `{healed, dropped, total, errors}`.

Tests:
- **Detects NaN last row.** Given a ticker whose last Close is NaN, `heal_cache` identifies it as needing heal.
- **Detects stale tickers.** Given a ticker whose last date is >2 trading days old, flags as stale.
- **Healthy cache is a no-op.** Fresh, non-NaN data produces zero healed/dropped.
- **Respects rate limit.** With >50 stale tickers, only processes 50 per call (mock yfinance to assert call count).
- **Returns health report.** Report shape matches `{healed: int, dropped: int, total: int, errors: list}`.

All yfinance calls mocked. No network.

### 2.2 `src/thesis.py` — `tests/test_thesis.py`

Public surface: `generate_thesis(stock_data: dict) -> str`.

Tests:
- **Oversold RSI fires.** Stock with RSI=28 produces a thesis mentioning "oversold" or "RSI 28".
- **Top-3 selection.** Given 5+ notable data points, output contains exactly 3 of them.
- **Determinism.** Same input → identical output across repeated calls.
- **Graceful on sparse data.** Stock missing most fields still returns a non-empty string (not a crash).
- **No Gemini dependency.** Test runs without `GEMINI_API_KEY` set.

### 2.3 Watchlist endpoints — `tests/test_watchlist.py`

Public surface: `GET /watchlist`, `POST /watchlist/{ticker}`, `DELETE /watchlist/{ticker}`.

Tests use FastAPI `TestClient` and a temp `data/` dir fixture.

Tests:
- **GET empty returns empty structure.** Fresh watchlist.json → `{tickers: {}}`.
- **POST adds with price snapshot.** After `POST /watchlist/FAF`, GET shows FAF with `added` date and `price_at_add`.
- **POST is idempotent.** Adding same ticker twice doesn't duplicate or error (either 200 with no-op or 409; pick one and test it).
- **DELETE removes.** After DELETE, ticker absent from GET response.
- **API key required.** POST/DELETE without `X-API-Key` returns 401/403. GET is public.

### 2.4 `src/insider.py` — `tests/test_insider.py`

Public surface: smart money score combining analyst revisions + insider trades.

Tests:
- **Positive revisions + insider buying → high score.**
- **Negative revisions + insider selling → low score.**
- **Missing analyst data → falls back to insider-only score.**
- **Missing both → returns neutral/None, not a crash.**

Exact function signatures and score shape confirmed during implementation by reading `src/insider.py` first.

### 2.5 `/chart/{ticker}` endpoint — add to `tests/test_api_endpoints.py`

Tests:
- **Returns OHLC + support/resistance for cached ticker.** Verify response shape matches frontend `ChartData` type.
- **Falls back to yfinance for uncached ticker.** Mock yfinance; assert it's called when ticker missing from cache.
- **Unknown ticker returns 404.** Ticker with no data anywhere → 404, not 500.

### 2.6 `src/thesis_tracker.py` — conditional

Read the module during implementation. If logic is trivial (append-only log), skip. If non-trivial (diffing, tracking changes over time), add 2-3 tests.

## Out of Scope

- **`src/ml_model.py`, `pipeline.py`, `optimizer.py`, `risk_manager.py`** — large, stable, high effort for low incremental safety. Test when we touch them.
- **Coverage reporting (coverage.py).** Premature; green tests is the bar.
- **CI integration.** Single-dev Mac mini; local green is enough.
- **Rewriting passing tests.** Don't churn what works.
- **Log rotation / routing fixes.** Spec 2.
- **Any model or behavior changes.** Tests characterize existing behavior; they do not fix model bugs in this spec.

## Files Changed

### Modified
- `pytest.ini` — `pythonpath = . src`
- `tests/test_scan_results_service.py` — remove `from conftest import` line
- `tests/test_api_endpoints.py` — add `/chart/{ticker}` tests
- `.gitignore` — ensure log files excluded
- Remove `server.log` from repo root

### New
- `tests/test_cache_health.py`
- `tests/test_thesis.py`
- `tests/test_watchlist.py`
- `tests/test_insider.py`
- `tests/test_thesis_tracker.py` (conditional on module complexity)

## Exit Criteria

1. `python3 -m pytest --collect-only -q` reports 0 errors.
2. `python3 -m pytest` runs green locally.
3. Each module in §2.1–§2.5 has ≥1 meaningful test that would fail if the module's primary function returned a stub.
4. `.gitignore` covers all log output locations; `server.log` removed from repo root.
5. Test run time remains under 30 seconds (no network, mock yfinance).

## Sequencing Within This Spec

1. Fix collection (§1.1, §1.2, §1.3) — verify green before adding new tests.
2. Add tests in order §2.1 → §2.5, each committed separately. §2.6 decided inline.
3. Final `pytest` run must be green before the spec is considered done.

## Dependencies

None. Purely local test changes. No model, API shape, or data file changes.
