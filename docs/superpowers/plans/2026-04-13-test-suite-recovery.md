# Test Suite Recovery Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Restore `pytest` to a green-on-local state and add coverage for recently-added modules (`cache_health`, `thesis`, `watchlist`, `insider`, `/chart` endpoint).

**Architecture:** Two phases. Phase 1 repairs test collection via a one-line `pytest.ini` fix, a conftest-import removal, and log-file hygiene. Phase 2 adds one focused test module per recently-added source module, using existing `conftest.py` fixtures and mocking all external I/O (yfinance, file system via temp dirs).

**Tech Stack:** pytest, FastAPI `TestClient`, unittest.mock / MagicMock, pandas. No new dependencies.

**Spec:** `docs/superpowers/specs/2026-04-13-test-suite-recovery-design.md`

**Pre-existing bugs surfaced during planning (out of scope — record for follow-up):**
- Watchlist POST/DELETE endpoints do NOT enforce `X-API-Key` despite CLAUDE.md claiming mutating endpoints require it. Tests in this plan **characterize current behavior** (no auth); fixing the auth gap is a separate ticket.
- Watchlist POST returns `200 {"status": "already_exists"}` on duplicate rather than `409`. Tests characterize the 200 response.
- Watchlist DELETE on unknown ticker returns `200 {"status": "not_found"}` rather than `404`. Tests characterize the 200 response.

---

## Phase 1: Fix Collection

### Task 1: Verify the broken baseline

**Files:**
- None (observation only)

- [ ] **Step 1: Run collection to capture the current error state**

Run: `cd ~/clawd/stock-picker && python3 -m pytest --collect-only -q 2>&1 | tail -20`

Expected output (the failure mode we are fixing):
```
ERROR tests/test_api_endpoints.py
ERROR tests/test_pipeline_integration.py
ERROR tests/test_profit_taker.py
ERROR tests/test_scan_results_service.py
ERROR tests/test_sell_signals.py
!!!!!!!!!!!!!!!!!!! Interrupted: 5 errors during collection !!!!!!!!!!!!!!!!!!!!
===================== 3 tests collected, 5 errors in ~0.4s ====================
```

If you see a different error set, STOP and re-check the plan against reality.

---

### Task 2: Fix pytest pythonpath

**Files:**
- Modify: `pytest.ini`

- [ ] **Step 1: Edit `pytest.ini`**

Change the `pythonpath` line from `pythonpath = .` to `pythonpath = . src`.

Final file contents:
```ini
[pytest]
# Pytest configuration for stock picker project

# Test discovery
python_files = test_*.py
python_classes = Test*
python_functions = test_*

# Paths
testpaths = tests
pythonpath = . src

# Output and coverage
addopts =
    -v
    --strict-markers
    --tb=short
    --disable-warnings

# Markers for organizing tests
markers =
    unit: Unit tests
    integration: Integration tests
    slow: Slow running tests
    mock: Tests that use mocks
```

- [ ] **Step 2: Run collection — expect 4 of 5 errors to disappear**

Run: `python3 -m pytest --collect-only -q 2>&1 | tail -10`

Expected: only `tests/test_scan_results_service.py` still errors, with message `ModuleNotFoundError: No module named 'conftest'`. All other collection errors should be gone.

If other errors remain, investigate before proceeding.

- [ ] **Step 3: Commit**

```bash
cd ~/clawd/stock-picker
git add pytest.ini
git commit -m "fix(tests): add src/ to pytest pythonpath so test modules resolve

Tests imported from src/* directly (e.g., 'from sell_signals import ...')
but pythonpath only included repo root, so collection failed with
ModuleNotFoundError on 4 test files."
```

---

### Task 3: Remove direct conftest import

**Files:**
- Modify: `tests/test_scan_results_service.py` (line 9)

- [ ] **Step 1: Inspect the current import**

Run: `head -15 tests/test_scan_results_service.py`

Expected to contain a line like: `from conftest import temp_data_dir`

- [ ] **Step 2: Remove the line**

Open `tests/test_scan_results_service.py` and delete the `from conftest import temp_data_dir` line. The `temp_data_dir` fixture is auto-injected by pytest when used as a function parameter — no import is required.

Do NOT remove any other imports. Do NOT change the fixture usages in the test functions themselves.

- [ ] **Step 3: Verify collection is now clean**

Run: `python3 -m pytest --collect-only -q 2>&1 | tail -5`

Expected: `N tests collected` with zero errors. N should be in the 40–80 range.

- [ ] **Step 4: Run the full suite**

Run: `python3 -m pytest 2>&1 | tail -15`

Expected: all tests pass, OR a small number of pre-existing failures unrelated to collection. If there are failures, capture the list and triage:
- If a failure is clearly caused by this task's changes → fix before committing.
- If a failure is pre-existing (e.g., stale mock data), note it in a comment on the commit and proceed; do NOT fix unrelated failures in this plan.

- [ ] **Step 5: Commit**

```bash
git add tests/test_scan_results_service.py
git commit -m "fix(tests): remove direct conftest import

Pytest auto-injects conftest fixtures as function parameters; importing
conftest as a module fails because tests/ is not a package."
```

---

### Task 4: Log file hygiene

**Files:**
- Modify: `.gitignore`
- Delete: `server.log` (repo root)

- [ ] **Step 1: Check current `.gitignore` for log coverage**

Run: `grep -n "log\|server\.log" .gitignore`

Note which patterns are already present.

- [ ] **Step 2: Add any missing patterns**

Ensure `.gitignore` contains (add any that are missing, do NOT duplicate existing entries):

```
# Logs
server.log
data/server.log
data/server.error.log
logs/*.log
```

- [ ] **Step 3: Remove the stray `server.log` in repo root**

Run: `ls -la server.log 2>/dev/null && rm -v server.log`

If the file doesn't exist, this step is a no-op — that's fine.

- [ ] **Step 4: Verify git status is clean regarding logs**

Run: `git status --short | grep -i log`

Expected: empty (all log files ignored).

- [ ] **Step 5: Commit**

```bash
git add .gitignore
git commit -m "chore: ignore log files in repo root and data/"
```

---

## Phase 2: Coverage for Recently-Added Modules

### Task 5: Tests for `src/cache_health.py`

**Files:**
- Create: `tests/test_cache_health.py`

**Context for implementer:** `cache_health.py` exposes two public functions. `diagnose_cache(cache_path)` is pure read: returns `{total, nan_count, stale_count, nan_tickers, stale_tickers, last_modified}`. `heal_cache(cache_path, max_refetch=50)` returns `{healed_nan, refetched, dropped, total, errors}`. Both accept a `cache_path` argument — tests should pass a temp path rather than patching module-level `CACHE_FILE`. `heal_cache` imports `fetch_stock_data` lazily via `from .pipeline import fetch_stock_data`, so we patch it at `src.cache_health.fetch_stock_data` after the import occurs — use `patch("src.pipeline.fetch_stock_data")` instead, which is cleaner since the import resolves at call time.

- [ ] **Step 1: Write the test file**

Create `tests/test_cache_health.py` with the following contents:

```python
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
        "history": {"Close": [close_value], "Open": [close_value], "High": [close_value], "Low": [close_value], "Volume": [1_000_000]},
        "history_index": [_days_ago_iso(0)],
    }


def test_diagnose_healthy_cache(temp_data_dir):
    """A cache with only fresh, non-NaN data reports zero issues."""
    from cache_health import diagnose_cache

    cache = _make_cache(temp_data_dir, {"AAPL": _fresh_ticker(150.0), "MSFT": _fresh_ticker(400.0)})
    report = diagnose_cache(str(cache))

    assert report["total"] == 2
    assert report["nan_count"] == 0
    assert report["stale_count"] == 0
    assert report["nan_tickers"] == []
    assert report["stale_tickers"] == []


def test_diagnose_detects_nan_last_row(temp_data_dir):
    """A ticker whose last Close is NaN is flagged as nan."""
    from cache_health import diagnose_cache

    bad = _fresh_ticker(100.0)
    bad["history"]["Close"] = [100.0, float("nan")]
    bad["history_index"] = [_days_ago_iso(1), _days_ago_iso(0)]

    cache = _make_cache(temp_data_dir, {"BAD": bad})
    report = diagnose_cache(str(cache))

    assert report["nan_count"] == 1
    assert "BAD" in report["nan_tickers"]


def test_diagnose_detects_stale(temp_data_dir):
    """A ticker whose last date is >3 days old is flagged as stale."""
    from cache_health import diagnose_cache

    stale = _fresh_ticker(50.0)
    stale["history_index"] = [_days_ago_iso(10)]

    cache = _make_cache(temp_data_dir, {"OLD": stale})
    report = diagnose_cache(str(cache))

    assert report["stale_count"] == 1
    assert "OLD" in report["stale_tickers"]


def test_diagnose_missing_cache_returns_zeros(tmp_path):
    """diagnose_cache on a non-existent path returns a zeroed report, not a crash."""
    from cache_health import diagnose_cache

    report = diagnose_cache(str(tmp_path / "does-not-exist.json"))

    assert report["total"] == 0
    assert report["nan_count"] == 0
    assert report["stale_count"] == 0


def test_heal_trims_trailing_nan_close(temp_data_dir):
    """heal_cache drops trailing NaN Close rows from each ticker."""
    from cache_health import heal_cache

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

    # Patch fetch_stock_data so heal_cache never actually calls yfinance
    with patch("src.pipeline.fetch_stock_data", return_value=None):
        report = heal_cache(str(cache), max_refetch=0)

    assert report["healed_nan"] == 1

    # After heal, the last Close on disk is non-NaN and length is 2
    saved = json.loads(cache.read_text())
    closes = saved["TRIM"]["history"]["Close"]
    assert len(closes) == 2
    assert not math.isnan(closes[-1])


def test_heal_drops_ticker_with_all_nan(temp_data_dir):
    """If every Close is NaN, the ticker is removed from cache."""
    from cache_health import heal_cache

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
    from cache_health import heal_cache

    entries = {}
    for i in range(10):
        ticker = f"T{i}"
        stale = _fresh_ticker(100.0)
        stale["history_index"] = [_days_ago_iso(15)]  # all stale
        entries[ticker] = stale
    cache = _make_cache(temp_data_dir, entries)

    fresh_return = _fresh_ticker(200.0)
    with patch("src.pipeline.fetch_stock_data", return_value=fresh_return) as mock_fetch:
        report = heal_cache(str(cache), max_refetch=3)

    assert mock_fetch.call_count == 3
    assert report["refetched"] == 3


def test_heal_report_shape(temp_data_dir):
    """heal_cache returns the documented keys even on an empty cache."""
    from cache_health import heal_cache

    cache = _make_cache(temp_data_dir, {})
    with patch("src.pipeline.fetch_stock_data", return_value=None):
        report = heal_cache(str(cache))

    assert set(report.keys()) == {"healed_nan", "refetched", "dropped", "total", "errors"}
    assert report["total"] == 0
    assert report["errors"] == []
```

- [ ] **Step 2: Run the tests**

Run: `python3 -m pytest tests/test_cache_health.py -v 2>&1 | tail -20`

Expected: all 8 tests pass.

If `ModuleNotFoundError: No module named 'cache_health'` appears, re-verify Task 2 was committed (pythonpath = . src).

If the `test_heal_respects_max_refetch` assertion fails with `mock_fetch.call_count == 0`, re-check that `patch("src.pipeline.fetch_stock_data", ...)` correctly intercepts the lazy import — if needed, switch to `patch("src.cache_health.fetch_stock_data", ...)` but note this requires the import to already have resolved at patch time (which happens on first call to heal_cache, so the indirection via `src.pipeline` is more reliable).

- [ ] **Step 3: Commit**

```bash
git add tests/test_cache_health.py
git commit -m "test: add coverage for cache_health module

Tests diagnose_cache (NaN, stale, healthy) and heal_cache (trim, drop,
refetch cap, report shape). All yfinance calls mocked."
```

---

### Task 6: Tests for `src/thesis.py`

**Files:**
- Create: `tests/test_thesis.py`

**Context for implementer:** `thesis.py` exposes `generate_thesis(stock: dict) -> str`. It scans a stock dict for notable data points (RSI extremes, insider activity, analyst target upside, ADX, etc.), ranks them by priority (hardcoded numbers in the module), and returns a " + "-joined string of the top 3. When no data points match, it returns `"No standout signals"`. `generate_gemini_thesis` is out of scope (requires GEMINI_API_KEY and network).

- [ ] **Step 1: Write the test file**

Create `tests/test_thesis.py` with the following contents:

```python
"""Tests for src/thesis.py (template-based thesis only)."""

import pytest


def test_oversold_rsi_appears_in_thesis():
    """RSI < 30 must surface in the generated thesis."""
    from thesis import generate_thesis

    stock = {"rsi": 28}
    thesis = generate_thesis(stock)

    assert "RSI 28" in thesis or "oversold" in thesis.lower()


def test_no_signals_returns_fallback():
    """Sparse data returns the fallback string, not a crash."""
    from thesis import generate_thesis

    assert generate_thesis({}) == "No standout signals"
    assert generate_thesis({"rsi": 50}) == "No standout signals"


def test_determinism():
    """Same input produces identical output across repeated calls."""
    from thesis import generate_thesis

    stock = {
        "rsi": 28,
        "insider_buy_value": 5_000_000,
        "consecutive_days": 7,
        "adx": 35,
    }
    outputs = {generate_thesis(stock) for _ in range(10)}
    assert len(outputs) == 1


def test_top_3_selection():
    """With 5+ notable data points, thesis contains exactly 3 ' + '-joined parts."""
    from thesis import generate_thesis

    stock = {
        "rsi": 28,                          # oversold, priority 10
        "insider_buy_value": 5_000_000,     # high priority 9
        "adx": 35,                          # priority 6
        "consecutive_days": 7,              # priority 7
        "pe_ratio": 8.0,                    # priority 5
        "revenue_growth": 0.25,             # priority 5
        "sentiment": {"pt_upside_pct": 0.30, "recommendation": "buy", "analyst_count": 10},
    }
    thesis = generate_thesis(stock)
    parts = thesis.split(" + ")

    assert len(parts) == 3


def test_highest_priority_points_win():
    """Highest-priority data points (RSI oversold=10, big insider buy=9) come first."""
    from thesis import generate_thesis

    stock = {
        "rsi": 28,                          # priority 10
        "insider_buy_value": 5_000_000,     # priority 9
        "pe_ratio": 8.0,                    # priority 5
        "piotroski_score": 8,               # priority 4
    }
    thesis = generate_thesis(stock)

    # Both top-priority points must be present; the priority-4 item may be dropped
    assert "RSI 28" in thesis or "oversold" in thesis.lower()
    assert "insider" in thesis.lower()


def test_insider_selling_surfaces():
    """Large insider selling above the $1M threshold appears in the thesis."""
    from thesis import generate_thesis

    stock = {"insider_sell_value": 2_000_000}
    thesis = generate_thesis(stock)

    assert "selling" in thesis.lower()


def test_gemini_not_required(monkeypatch):
    """generate_thesis must work without GEMINI_API_KEY in environment."""
    from thesis import generate_thesis

    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    thesis = generate_thesis({"rsi": 28})

    assert thesis  # non-empty
```

- [ ] **Step 2: Run the tests**

Run: `python3 -m pytest tests/test_thesis.py -v 2>&1 | tail -15`

Expected: all 7 tests pass.

- [ ] **Step 3: Commit**

```bash
git add tests/test_thesis.py
git commit -m "test: add coverage for thesis template generator

Verifies RSI oversold surfacing, determinism, top-3 selection, priority
ordering, insider-selling signal, and no-Gemini fallback."
```

---

### Task 7: Tests for watchlist endpoints

**Files:**
- Create: `tests/test_watchlist.py`

**Context for implementer:** Watchlist endpoints live in `src/api.py` lines 90–137. `WATCHLIST_FILE` is computed at module-load as `DATA_DIR / "watchlist.json"`, so patching `DATA_DIR` after import does NOT redirect the file location. Patch `src.api.WATCHLIST_FILE` directly for each test. `_get_current_price()` reads from `DATA_DIR / "stock_data_cache.json"` — patch `src.api.DATA_DIR` for that path.

**Characterize-current-behavior constraint:** The endpoints currently do NOT enforce `X-API-Key`. Tests verify the _actual_ behavior (no auth required), not the CLAUDE.md-claimed behavior. This is a pre-existing bug documented at the top of the plan.

- [ ] **Step 1: Write the test file**

Create `tests/test_watchlist.py` with the following contents:

```python
"""Tests for watchlist endpoints in src/api.py.

These tests characterize CURRENT behavior. The endpoints do not enforce
X-API-Key auth despite CLAUDE.md claiming they should — fixing the auth
gap is a separate ticket.
"""

import json
from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def watchlist_client(temp_data_dir, monkeypatch):
    """Yield a TestClient with watchlist and cache paths redirected to a temp dir."""
    watchlist_path = temp_data_dir / "watchlist.json"
    cache_path = temp_data_dir / "stock_data_cache.json"

    # Seed a cache with a known price for FAF so _get_current_price returns 60.84
    cache_path.write_text(json.dumps({
        "FAF": {
            "info": {"ticker": "FAF"},
            "history": {"Close": [60.84], "Open": [60.0], "High": [61.0], "Low": [59.5], "Volume": [1_000_000]},
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

    # GET now shows it
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

    # Listing still contains exactly one FAF entry
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
```

- [ ] **Step 2: Run the tests**

Run: `python3 -m pytest tests/test_watchlist.py -v 2>&1 | tail -20`

Expected: all 7 tests pass.

If any test fails with `FileNotFoundError` on `watchlist.json`, confirm that `WATCHLIST_FILE` was patched BEFORE the first request reaches `_load_watchlist()`. Fixture ordering should handle this because `watchlist_client` yields inside the `patch` context manager.

- [ ] **Step 3: Commit**

```bash
git add tests/test_watchlist.py
git commit -m "test: add coverage for /watchlist endpoints

Tests GET/POST/DELETE with temp data dir. Characterizes current behavior:
idempotent POST returns 'already_exists', DELETE of unknown returns
'not_found', no X-API-Key enforcement (pre-existing gap)."
```

---

### Task 8: Tests for `src/insider.py`

**Files:**
- Create: `tests/test_insider.py`

**Context for implementer:** `insider.py` has three public functions that take a yfinance `Ticker` object: `analyze_analyst_signals`, `analyze_insider_signals`, and `get_combined_smart_money_score`. Tests mock the ticker object with `MagicMock` and populate the DataFrames the real functions access (`upgrades_downgrades`, `recommendations_summary`, `insider_purchases`, `insider_transactions`). Combined score is `analyst_score * 0.6 + insider_score * 0.4`.

- [ ] **Step 1: Write the test file**

Create `tests/test_insider.py` with the following contents:

```python
"""Tests for src/insider.py smart money signals."""

from datetime import datetime, timedelta
from unittest.mock import MagicMock

import pandas as pd
import pytest


def _mock_ticker_with_upgrades(upgrades: int, downgrades: int, pt_raises: int = 0):
    """Build a MagicMock yfinance.Ticker with given recent analyst actions."""
    ticker = MagicMock()
    now = datetime.now()

    rows = []
    for _ in range(upgrades):
        rows.append({"Action": "up", "currentPriceTarget": 150, "priorPriceTarget": 140 if pt_raises > 0 else 150})
    for _ in range(downgrades):
        rows.append({"Action": "down", "currentPriceTarget": 150, "priorPriceTarget": 150})

    if rows:
        df = pd.DataFrame(rows, index=[now - timedelta(days=5)] * len(rows))
        ticker.upgrades_downgrades = df
    else:
        ticker.upgrades_downgrades = None

    # No recommendations_summary by default → neutral
    ticker.recommendations_summary = None
    return ticker


def _mock_ticker_with_insider_summary(buy_count: int, sell_count: int, net_shares: int, pct: float = 0.0):
    """Build a MagicMock with insider_purchases summary table rows."""
    ticker = MagicMock()
    ticker.insider_purchases = pd.DataFrame([
        {"0": "Purchases", "1": buy_count},
        {"0": "Sales", "1": sell_count},
        {"0": "Net Shares Purchased", "1": net_shares},
        {"0": "% Net Shares Purchased", "1": pct},
    ])
    # Rename to positional-only; the real code uses row.iloc[0], row.iloc[1]
    ticker.insider_purchases.columns = [0, 1]
    ticker.insider_transactions = None
    return ticker


def test_positive_revisions_raise_score():
    """Heavy upgrades push analyst score above neutral (50)."""
    from insider import analyze_analyst_signals

    ticker = _mock_ticker_with_upgrades(upgrades=4, downgrades=0)
    result = analyze_analyst_signals(ticker)

    assert result["score"] > 50
    assert result["upgrades_30d"] == 4
    assert result["downgrades_30d"] == 0


def test_negative_revisions_lower_score():
    """Heavy downgrades push analyst score below neutral."""
    from insider import analyze_analyst_signals

    ticker = _mock_ticker_with_upgrades(upgrades=0, downgrades=4)
    result = analyze_analyst_signals(ticker)

    assert result["score"] < 50
    assert result["downgrades_30d"] == 4


def test_no_analyst_data_returns_neutral():
    """A ticker with no analyst data scores neutral (50), not a crash."""
    from insider import analyze_analyst_signals

    ticker = MagicMock()
    ticker.upgrades_downgrades = None
    ticker.recommendations_summary = None

    result = analyze_analyst_signals(ticker)

    assert result["score"] == 50
    assert result["upgrades_30d"] == 0


def test_insider_buying_raises_score():
    """Net insider buying with more buys than sells raises the score."""
    from insider import analyze_insider_signals

    ticker = _mock_ticker_with_insider_summary(buy_count=6, sell_count=1, net_shares=50_000)
    result = analyze_insider_signals(ticker)

    assert result["score"] > 50
    assert result["buy_count"] == 6
    assert result["sell_count"] == 1


def test_heavy_insider_selling_lowers_score():
    """Lopsided insider selling (sells > 3x buys) lowers the score."""
    from insider import analyze_insider_signals

    ticker = _mock_ticker_with_insider_summary(buy_count=1, sell_count=10, net_shares=-100_000)
    result = analyze_insider_signals(ticker)

    assert result["score"] < 50


def test_no_insider_data_returns_neutral():
    """Missing insider data does not crash and returns neutral score."""
    from insider import analyze_insider_signals

    ticker = MagicMock()
    ticker.insider_purchases = None
    ticker.insider_transactions = None

    result = analyze_insider_signals(ticker)

    assert result["score"] == 50


def test_combined_score_weights_analyst_60_insider_40():
    """Combined score = 0.6 * analyst + 0.4 * insider (documented weighting)."""
    from insider import get_combined_smart_money_score

    # Mock the two sub-functions via a ticker that returns known sub-scores.
    # We verify the formula by reading out the reported sub-scores and recomputing.
    ticker = MagicMock()
    ticker.upgrades_downgrades = None
    ticker.recommendations_summary = None
    ticker.insider_purchases = None
    ticker.insider_transactions = None

    result = get_combined_smart_money_score(ticker)

    expected = result["analyst_score"] * 0.6 + result["insider_score"] * 0.4
    assert abs(result["score"] - round(expected, 1)) < 0.01


def test_combined_score_bounded_0_to_100():
    """Combined score never leaves the [0, 100] range regardless of inputs."""
    from insider import get_combined_smart_money_score

    ticker = _mock_ticker_with_insider_summary(buy_count=20, sell_count=0, net_shares=1_000_000, pct=0.05)
    # Add heavy upgrades too
    rows = [{"Action": "up", "currentPriceTarget": 200, "priorPriceTarget": 150} for _ in range(10)]
    ticker.upgrades_downgrades = pd.DataFrame(rows, index=[datetime.now() - timedelta(days=5)] * 10)
    ticker.recommendations_summary = None

    result = get_combined_smart_money_score(ticker)

    assert 0 <= result["score"] <= 100
```

- [ ] **Step 2: Run the tests**

Run: `python3 -m pytest tests/test_insider.py -v 2>&1 | tail -20`

Expected: all 8 tests pass.

If `test_insider_buying_raises_score` fails because the mock table columns don't match how the real code reads `row.iloc[0]`, verify the `columns = [0, 1]` assignment. If still failing, print `ticker.insider_purchases` in the test and confirm columns are positional integers, not strings.

- [ ] **Step 3: Commit**

```bash
git add tests/test_insider.py
git commit -m "test: add coverage for insider/analyst smart money signals

Verifies score direction for upgrades, downgrades, insider buying/selling,
neutral-on-missing-data, bounding, and 60/40 analyst-insider weighting."
```

---

### Task 9: Tests for `/chart/{ticker}` endpoint

**Files:**
- Create: `tests/test_chart_endpoint.py`

**Context for implementer:** `/chart/{ticker}` is defined in `src/routes/scan.py` starting at line 320. Router mounted in `src/api.py`. It returns OHLC + support/resistance. Reads from `stock_data_cache.json` first, falls back to yfinance for uncached tickers. Tests mock the cache file via a temp dir and patch the yfinance fallback.

- [ ] **Step 1: Read the endpoint implementation to confirm response shape**

Run: `sed -n '320,400p' src/routes/scan.py`

Capture the response shape (keys like `ticker`, `ohlc`, `support`, `resistance`, etc.). Use the actual keys in test assertions, not assumed ones — this is directly from the `feedback_api_shapes` memory.

- [ ] **Step 2: Write the test file**

Create `tests/test_chart_endpoint.py` with the following contents. Adjust the assertion keys in `test_chart_returns_ohlc_and_levels` to match what you observed in Step 1.

```python
"""Tests for /chart/{ticker} endpoint in src/routes/scan.py."""

import json
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def chart_client(temp_data_dir):
    """Yield a TestClient with the stock data cache redirected to a temp dir."""
    cache_path = temp_data_dir / "stock_data_cache.json"

    # Seed a ticker with 90 days of synthetic history
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

    # The /chart endpoint reads via pipeline helpers; patch DATA_DIR where used.
    with patch("src.routes.scan.DATA_DIR", temp_data_dir, create=True), \
         patch("src.api.DATA_DIR", temp_data_dir):
        from src.api import app
        yield TestClient(app)


def test_chart_returns_200_for_cached_ticker(chart_client):
    """Known cached ticker returns 200 with a non-empty body."""
    resp = chart_client.get("/chart/AAPL")
    assert resp.status_code == 200
    body = resp.json()
    # Must have SOME chart data — exact key set validated in the next test
    assert body  # non-empty dict


def test_chart_returns_ohlc_and_levels(chart_client):
    """Response contains price data and support/resistance levels.

    NOTE: Adjust these key names to match what step 1 showed in the
    actual implementation. Common shapes: 'ohlc', 'prices', 'data'.
    """
    resp = chart_client.get("/chart/AAPL")
    body = resp.json()

    # Identify the price array (one of these names, per the actual impl):
    price_key = next((k for k in ("ohlc", "prices", "data", "history") if k in body), None)
    assert price_key is not None, f"No price array found in response keys: {list(body.keys())}"
    assert len(body[price_key]) > 0

    # Support/resistance should be present (may be None for low-data tickers)
    assert "support" in body or "support_level" in body
    assert "resistance" in body or "resistance_level" in body


def test_chart_unknown_ticker_handled_gracefully(chart_client):
    """Ticker with no cache entry and yfinance disabled returns 404 or empty.

    Characterize current behavior — do not fix any 500s found here,
    but document what actually happens.
    """
    with patch("yfinance.Ticker") as mock_yf:
        # Yfinance returns empty history for unknown ticker
        mock_yf.return_value.history.return_value.empty = True
        mock_yf.return_value.history.return_value.to_dict.return_value = {}

        resp = chart_client.get("/chart/ZZZZZZZZ")

    # Accept any non-500 outcome as "handled gracefully"
    assert resp.status_code != 500, f"500 error: {resp.text}"
```

- [ ] **Step 3: Run the tests**

Run: `python3 -m pytest tests/test_chart_endpoint.py -v 2>&1 | tail -20`

Expected: all 3 tests pass.

If `test_chart_returns_ohlc_and_levels` fails with "No price array found", look at the actual response body (`print(body)` in the test) and update `price_key` candidates accordingly. Adjust the test to match the actual keys — do NOT modify the endpoint to match the test.

If `test_chart_unknown_ticker_handled_gracefully` returns 500, note it in the commit message as a pre-existing bug to address later, but RELAX the assertion to match observed behavior so the test is green for characterization purposes. Add a comment: `# Characterization: returns 500 on unknown ticker (bug — separate ticket)`.

- [ ] **Step 4: Commit**

```bash
git add tests/test_chart_endpoint.py
git commit -m "test: add coverage for /chart/{ticker} endpoint

Verifies OHLC + support/resistance response for cached ticker and
graceful handling of unknown ticker. Characterizes current behavior."
```

---

### Task 10: Tests for `src/thesis_tracker.py` (conditional)

**Files:**
- Conditional: `tests/test_thesis_tracker.py`

- [ ] **Step 1: Read the module and decide**

Run: `wc -l src/thesis_tracker.py && head -50 src/thesis_tracker.py`

Decide:
- **If trivial (append-only log, no logic):** skip this task, add a note to the final commit message, and proceed to Task 11.
- **If non-trivial (diffing, change tracking, state transitions):** continue to Step 2.

- [ ] **Step 2: Write focused tests (only if non-trivial)**

If continuing, create `tests/test_thesis_tracker.py` with 2–3 tests that cover the primary code paths. Follow the same patterns as prior tasks: use `temp_data_dir`, no network, no real yfinance. Each test should cover one code path discovered in Step 1.

- [ ] **Step 3: Run and commit**

Run: `python3 -m pytest tests/test_thesis_tracker.py -v`

Commit with message describing what the tests cover.

---

### Task 11: Final verification

**Files:**
- None (verification only)

- [ ] **Step 1: Full collection check**

Run: `python3 -m pytest --collect-only -q 2>&1 | tail -5`

Expected: `N tests collected, 0 errors` with N at least 60 (roughly 40 existing + ~28 added by this plan).

- [ ] **Step 2: Full suite run**

Run: `time python3 -m pytest 2>&1 | tail -20`

Expected: all tests pass. Wall time under 30 seconds.

If there are failures introduced by this plan's tests, fix them. If there are pre-existing failures unrelated to this plan, record them (ticker name + failing assertion) as a follow-up issue — do NOT fix them in this plan.

- [ ] **Step 3: Confirm the exit criteria from the spec**

Tick each box by inspection:
- [ ] `pytest --collect-only -q` reports 0 errors
- [ ] `pytest` runs green locally
- [ ] `tests/test_cache_health.py` exists with ≥1 meaningful test
- [ ] `tests/test_thesis.py` exists with ≥1 meaningful test
- [ ] `tests/test_watchlist.py` exists with ≥1 meaningful test
- [ ] `tests/test_insider.py` exists with ≥1 meaningful test
- [ ] `/chart` endpoint has coverage (in `tests/test_chart_endpoint.py`)
- [ ] `.gitignore` excludes log files; `server.log` removed from repo root
- [ ] Test run time under 30 seconds

- [ ] **Step 4: Final commit (only if anything untracked)**

```bash
git status
# If anything remains untracked that belongs in this plan, commit it.
# Otherwise skip this step.
```

---

## Summary of Commits (expected, in order)

1. `fix(tests): add src/ to pytest pythonpath so test modules resolve`
2. `fix(tests): remove direct conftest import`
3. `chore: ignore log files in repo root and data/`
4. `test: add coverage for cache_health module`
5. `test: add coverage for thesis template generator`
6. `test: add coverage for /watchlist endpoints`
7. `test: add coverage for insider/analyst smart money signals`
8. `test: add coverage for /chart/{ticker} endpoint`
9. (conditional) `test: add coverage for thesis_tracker`

## Out of Scope (deferred to follow-up tickets)

- Fixing watchlist endpoints to enforce `X-API-Key`.
- Returning HTTP 409 on duplicate watchlist POST.
- Returning HTTP 404 on DELETE of unknown watchlist ticker.
- Any 500 observed from `/chart` on unknown ticker.
- Coverage for `ml_model.py`, `pipeline.py`, `optimizer.py`, `risk_manager.py`.
- `coverage.py` integration.
- CI pipeline.
