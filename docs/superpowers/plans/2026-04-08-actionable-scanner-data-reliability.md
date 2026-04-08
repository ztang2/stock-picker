# Actionable Scanner + Data Reliability Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Transform the scanner from a ranking list into an actionable trade tool with price charts, position sizing, watchlist, and thesis narratives — while eliminating stale/NaN data issues.

**Architecture:** Two independent workstreams. Workstream 1 (Actionable Scanner) adds 4 frontend features backed by 3 new API endpoints. Workstream 2 (Data Reliability) adds backend cache healing and a scheduled refresh cron. No shared files between workstreams — they can be built in parallel.

**Tech Stack:** Python/FastAPI (backend), React/TypeScript/Recharts/Tailwind (frontend), yfinance (data), Gemini API (on-demand thesis)

---

## Workstream 2: Data Reliability (backend-only, no frontend)

### Task 1: Cache Health Module — Auto-heal NaN/Stale Data

**Files:**
- Create: `src/cache_health.py`

- [ ] **Step 1: Create `src/cache_health.py` with `diagnose_cache` and `heal_cache`**

```python
"""Cache health: detect and fix NaN/stale prices in stock_data_cache.json."""

import json
import logging
import math
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

import pandas as pd

logger = logging.getLogger(__name__)

DATA_DIR = Path(__file__).parent.parent / "data"
CACHE_FILE = DATA_DIR / "stock_data_cache.json"


def _is_nan(val) -> bool:
    """Check if a value is NaN (handles float, None, string 'nan')."""
    if val is None:
        return True
    try:
        return math.isnan(float(val))
    except (TypeError, ValueError):
        return False


def _last_trading_date() -> datetime:
    """Approximate last trading date (skip weekends)."""
    now = datetime.now(timezone.utc)
    if now.weekday() == 5:  # Saturday
        return now - timedelta(days=1)
    if now.weekday() == 6:  # Sunday
        return now - timedelta(days=2)
    return now


def diagnose_cache(cache_path: Optional[str] = None) -> dict:
    """Read-only diagnosis of cache health.

    Returns: {total, nan_count, stale_count, nan_tickers, stale_tickers, last_modified}
    """
    path = Path(cache_path) if cache_path else CACHE_FILE
    if not path.exists():
        return {"total": 0, "nan_count": 0, "stale_count": 0, "nan_tickers": [], "stale_tickers": [], "last_modified": None}

    data = json.loads(path.read_text())
    cutoff = _last_trading_date() - timedelta(days=3)
    nan_tickers = []
    stale_tickers = []

    for ticker, tdata in data.items():
        if ticker == "SPY":
            continue
        close_list = tdata.get("history", {}).get("Close", [])
        index_list = tdata.get("history_index", [])

        if not close_list or _is_nan(close_list[-1]):
            nan_tickers.append(ticker)
            continue

        if index_list:
            try:
                last_date = pd.to_datetime(index_list[-1], utc=True)
                if last_date < pd.Timestamp(cutoff, tz="UTC"):
                    stale_tickers.append(ticker)
            except Exception:
                stale_tickers.append(ticker)

    return {
        "total": len(data) - (1 if "SPY" in data else 0),
        "nan_count": len(nan_tickers),
        "stale_count": len(stale_tickers),
        "nan_tickers": nan_tickers[:50],
        "stale_tickers": stale_tickers[:50],
        "last_modified": datetime.fromtimestamp(path.stat().st_mtime).isoformat() if path.exists() else None,
    }


def heal_cache(cache_path: Optional[str] = None, max_refetch: int = 50) -> dict:
    """Detect and fix NaN/stale data in cache.

    1. Drop trailing NaN Close rows from all tickers
    2. Re-fetch up to max_refetch stale tickers from yfinance
    3. Save updated cache

    Returns: {healed_nan, refetched, dropped, total, errors}
    """
    from .pipeline import fetch_stock_data

    path = Path(cache_path) if cache_path else CACHE_FILE
    if not path.exists():
        return {"healed_nan": 0, "refetched": 0, "dropped": 0, "total": 0, "errors": []}

    data = json.loads(path.read_text())
    cutoff = _last_trading_date() - timedelta(days=3)
    healed_nan = 0
    refetched = 0
    dropped = 0
    errors = []

    # Pass 1: Drop trailing NaN Close rows
    for ticker, tdata in list(data.items()):
        if ticker == "SPY":
            continue
        close_list = tdata.get("history", {}).get("Close", [])
        if not close_list:
            continue

        # Count trailing NaNs
        trim = 0
        for val in reversed(close_list):
            if _is_nan(val):
                trim += 1
            else:
                break

        if trim > 0:
            for col in tdata["history"]:
                tdata["history"][col] = tdata["history"][col][:-trim]
            tdata["history_index"] = tdata["history_index"][:-trim]
            healed_nan += 1

            # If all data was NaN, drop ticker
            if not tdata["history"].get("Close"):
                del data[ticker]
                dropped += 1

    # Pass 2: Re-fetch stale tickers
    stale = []
    for ticker, tdata in data.items():
        if ticker == "SPY":
            continue
        index_list = tdata.get("history_index", [])
        if not index_list:
            stale.append(ticker)
            continue
        try:
            last_date = pd.to_datetime(index_list[-1], utc=True)
            if last_date < pd.Timestamp(cutoff, tz="UTC"):
                stale.append(ticker)
        except Exception:
            stale.append(ticker)

    refetch_batch = stale[:max_refetch]
    if refetch_batch:
        logger.info("Re-fetching %d stale tickers: %s...", len(refetch_batch), refetch_batch[:5])
        for ticker in refetch_batch:
            try:
                fresh = fetch_stock_data(ticker, period="1y")
                if fresh:
                    data[ticker] = fresh
                    refetched += 1
                else:
                    errors.append(f"{ticker}: fetch returned None")
            except Exception as e:
                errors.append(f"{ticker}: {e}")
            time.sleep(0.2)

    # Save
    path.write_text(json.dumps(data))
    logger.info("Cache healed: %d NaN fixed, %d refetched, %d dropped", healed_nan, refetched, dropped)

    return {
        "healed_nan": healed_nan,
        "refetched": refetched,
        "dropped": dropped,
        "total": len(data) - (1 if "SPY" in data else 0),
        "errors": errors[:20],
    }
```

- [ ] **Step 2: Verify module imports cleanly**

Run: `cd /Users/zhuorantang/clawd/stock-picker && python3 -c "from src.cache_health import diagnose_cache, heal_cache; print('OK')"`
Expected: `OK`

- [ ] **Step 3: Test `diagnose_cache` against real data**

Run: `cd /Users/zhuorantang/clawd/stock-picker && python3 -c "from src.cache_health import diagnose_cache; import json; print(json.dumps(diagnose_cache(), indent=2))"`
Expected: JSON showing `total`, `nan_count`, `stale_count` with real numbers

- [ ] **Step 4: Commit**

```bash
git add src/cache_health.py
git commit -m "feat: add cache health module — diagnose and heal NaN/stale data"
```

### Task 2: Integrate Cache Healing into Scan + Add API Endpoint

**Files:**
- Modify: `src/pipeline.py` (top of `run_scan`)
- Modify: `src/api.py` (add `/cache/health` endpoint)

- [ ] **Step 1: Add cache heal call at the start of `run_scan` in `pipeline.py`**

In `src/pipeline.py`, find the `run_scan` function (around line 236). Add at the very beginning of the function body, before any other logic:

```python
    # Auto-heal cache before scanning
    try:
        from .cache_health import heal_cache
        heal_report = heal_cache()
        logger.info("Cache heal: %s", heal_report)
    except Exception as e:
        logger.warning("Cache heal failed: %s", e)
```

- [ ] **Step 2: Add `/cache/health` endpoint in `api.py`**

Add before the static file serving section (before `_static_dist = Path(...)`):

```python
@app.get("/cache/health")
async def cache_health():
    """Read-only cache health diagnostic."""
    import asyncio
    from .cache_health import diagnose_cache
    return await asyncio.to_thread(diagnose_cache)
```

- [ ] **Step 3: Test the endpoint**

Run: `curl -s http://localhost:8000/cache/health | python3 -m json.tool`
Expected: JSON with `total`, `nan_count`, `stale_count`, `last_modified`

- [ ] **Step 4: Commit**

```bash
git add src/pipeline.py src/api.py
git commit -m "feat: integrate cache healing into scan pipeline + add /cache/health endpoint"
```

### Task 3: Scheduled Cache Refresh Script + LaunchAgent

**Files:**
- Create: `scripts/refresh_cache.py`
- Create: `com.stockpicker.cache-refresh.plist`

- [ ] **Step 1: Create `scripts/refresh_cache.py`**

```python
#!/usr/bin/env python3
"""Refresh stock data cache and run scan. Called by cron/LaunchAgent after market close."""

import json
import logging
import sys
import time
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.pipeline import fetch_stock_data, load_config, run_scan
from src.cache_health import heal_cache

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

DATA_DIR = Path(__file__).parent.parent / "data"
CACHE_FILE = DATA_DIR / "stock_data_cache.json"
BATCH_SIZE = 50
BATCH_DELAY = 1.0  # seconds between batches


def refresh_full_cache():
    """Re-fetch all tickers in the cache from yfinance."""
    if not CACHE_FILE.exists():
        logger.error("Cache file not found: %s", CACHE_FILE)
        return

    data = json.loads(CACHE_FILE.read_text())
    tickers = [t for t in data.keys() if t != "SPY"]
    logger.info("Refreshing %d tickers...", len(tickers))

    refreshed = 0
    errors = 0
    for i in range(0, len(tickers), BATCH_SIZE):
        batch = tickers[i : i + BATCH_SIZE]
        for ticker in batch:
            try:
                fresh = fetch_stock_data(ticker, period="1y")
                if fresh:
                    data[ticker] = fresh
                    refreshed += 1
                else:
                    errors += 1
            except Exception as e:
                logger.warning("Failed to refresh %s: %s", ticker, e)
                errors += 1

        logger.info("Progress: %d/%d refreshed, %d errors", refreshed, len(tickers), errors)
        if i + BATCH_SIZE < len(tickers):
            time.sleep(BATCH_DELAY)

    # Also refresh SPY
    try:
        spy = fetch_stock_data("SPY", period="1y")
        if spy:
            data["SPY"] = spy
    except Exception:
        pass

    CACHE_FILE.write_text(json.dumps(data))
    logger.info("Cache refresh complete: %d/%d tickers updated", refreshed, len(tickers))
    return refreshed, errors


def main():
    logger.info("=== Starting scheduled cache refresh ===")

    # Step 1: Refresh full cache
    refresh_full_cache()

    # Step 2: Heal any NaN rows
    report = heal_cache()
    logger.info("Heal report: %s", report)

    # Step 3: Run scan
    logger.info("Running post-refresh scan...")
    config = load_config()
    run_scan(config)
    logger.info("=== Scheduled refresh complete ===")


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Make script executable**

Run: `chmod +x /Users/zhuorantang/clawd/stock-picker/scripts/refresh_cache.py`

- [ ] **Step 3: Test the script (dry run — just verify imports)**

Run: `cd /Users/zhuorantang/clawd/stock-picker && python3 -c "from scripts.refresh_cache import main; print('imports OK')"`

Note: Don't run `main()` in test — it takes 15+ minutes for full refresh.

- [ ] **Step 4: Create LaunchAgent plist**

Create `com.stockpicker.cache-refresh.plist` in project root:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.stockpicker.cache-refresh</string>
    <key>ProgramArguments</key>
    <array>
        <string>/usr/bin/python3</string>
        <string>/Users/zhuorantang/clawd/stock-picker/scripts/refresh_cache.py</string>
    </array>
    <key>WorkingDirectory</key>
    <string>/Users/zhuorantang/clawd/stock-picker</string>
    <key>StartCalendarInterval</key>
    <array>
        <dict>
            <key>Weekday</key><integer>1</integer>
            <key>Hour</key><integer>16</integer>
            <key>Minute</key><integer>30</integer>
        </dict>
        <dict>
            <key>Weekday</key><integer>2</integer>
            <key>Hour</key><integer>16</integer>
            <key>Minute</key><integer>30</integer>
        </dict>
        <dict>
            <key>Weekday</key><integer>3</integer>
            <key>Hour</key><integer>16</integer>
            <key>Minute</key><integer>30</integer>
        </dict>
        <dict>
            <key>Weekday</key><integer>4</integer>
            <key>Hour</key><integer>16</integer>
            <key>Minute</key><integer>30</integer>
        </dict>
        <dict>
            <key>Weekday</key><integer>5</integer>
            <key>Hour</key><integer>16</integer>
            <key>Minute</key><integer>30</integer>
        </dict>
    </array>
    <key>StandardOutPath</key>
    <string>/Users/zhuorantang/clawd/stock-picker/logs/cache-refresh.log</string>
    <key>StandardErrorPath</key>
    <string>/Users/zhuorantang/clawd/stock-picker/logs/cache-refresh-error.log</string>
    <key>EnvironmentVariables</key>
    <dict>
        <key>PATH</key>
        <string>/usr/local/bin:/usr/bin:/bin:/opt/homebrew/bin</string>
    </dict>
</dict>
</plist>
```

Note: The times are in local time (ET on this Mac mini). 16:30 = 4:30 PM ET.

- [ ] **Step 5: Create logs directory and install LaunchAgent**

Run:
```bash
mkdir -p /Users/zhuorantang/clawd/stock-picker/logs
cp /Users/zhuorantang/clawd/stock-picker/com.stockpicker.cache-refresh.plist ~/Library/LaunchAgents/
launchctl load ~/Library/LaunchAgents/com.stockpicker.cache-refresh.plist
```

- [ ] **Step 6: Commit**

```bash
git add scripts/refresh_cache.py com.stockpicker.cache-refresh.plist
git commit -m "feat: add scheduled cache refresh — 4:30 PM ET weekday cron with auto-heal + scan"
```

---

## Workstream 1: Actionable Scanner

### Task 4: Chart API Endpoint

**Files:**
- Modify: `src/api.py` (add `/chart/{ticker}` endpoint)

- [ ] **Step 1: Add `/chart/{ticker}` endpoint in `api.py`**

Add near the other stock-specific endpoints (after the `/momentum/{ticker}` endpoint):

```python
@app.get("/chart/{ticker}")
async def chart_data(ticker: str, period: str = "3mo"):
    """Return OHLC + support/resistance for mini chart."""
    import asyncio

    def _get_chart(t: str, p: str):
        t = t.upper()
        cache_file = DATA_DIR / "stock_data_cache.json"
        ohlc = []
        support = None
        resistance = None

        # Try cache first
        if cache_file.exists():
            import json as _json
            data = _json.loads(cache_file.read_text())
            if t in data:
                hist_data = data[t]
                close = hist_data["history"].get("Close", [])
                high = hist_data["history"].get("High", [])
                low = hist_data["history"].get("Low", [])
                opens = hist_data["history"].get("Open", [])
                index = hist_data.get("history_index", [])

                # Filter to period
                import pandas as pd
                dates = pd.to_datetime(index, utc=True)
                if p == "3mo":
                    cutoff = pd.Timestamp.now(tz="UTC") - pd.Timedelta(days=90)
                elif p == "6mo":
                    cutoff = pd.Timestamp.now(tz="UTC") - pd.Timedelta(days=180)
                else:
                    cutoff = pd.Timestamp.now(tz="UTC") - pd.Timedelta(days=90)

                for i, d in enumerate(dates):
                    if d >= cutoff and i < len(close):
                        import math
                        c = close[i]
                        if c is not None and not (isinstance(c, float) and math.isnan(c)):
                            ohlc.append({
                                "date": d.strftime("%Y-%m-%d"),
                                "open": round(opens[i], 2) if i < len(opens) and opens[i] is not None else None,
                                "high": round(high[i], 2) if i < len(high) and high[i] is not None else None,
                                "low": round(low[i], 2) if i < len(low) and low[i] is not None else None,
                                "close": round(c, 2),
                            })

                # Compute support/resistance from momentum module
                if ohlc:
                    from .momentum import _support_resistance
                    hist_df = pd.DataFrame(data[t]["history"])
                    hist_df.index = pd.to_datetime(data[t]["history_index"], utc=True)
                    hist_df = hist_df.dropna(subset=["Close"])
                    s, r = _support_resistance(hist_df)
                    support = s
                    resistance = r

                # MA50
                ma50 = None
                valid_closes = [o["close"] for o in ohlc if o["close"] is not None]
                if len(valid_closes) >= 50:
                    ma50 = round(sum(valid_closes[-50:]) / 50, 2)

                return {"ticker": t, "ohlc": ohlc, "support": support, "resistance": resistance, "ma50": ma50}

        # Fallback: fetch from yfinance
        import yfinance as yf
        hist = yf.Ticker(t).history(period=p)
        if hist.empty:
            return {"ticker": t, "ohlc": [], "support": None, "resistance": None, "ma50": None}

        for d, row in hist.iterrows():
            import math
            c = row["Close"]
            if not math.isnan(c):
                ohlc.append({
                    "date": d.strftime("%Y-%m-%d"),
                    "open": round(row["Open"], 2),
                    "high": round(row["High"], 2),
                    "low": round(row["Low"], 2),
                    "close": round(c, 2),
                })

        from .momentum import _support_resistance
        s, r = _support_resistance(hist)
        support = s
        resistance = r

        valid_closes = [o["close"] for o in ohlc]
        ma50 = round(sum(valid_closes[-50:]) / 50, 2) if len(valid_closes) >= 50 else None

        return {"ticker": t, "ohlc": ohlc, "support": support, "resistance": resistance, "ma50": ma50}

    return await asyncio.to_thread(_get_chart, ticker, period)
```

- [ ] **Step 2: Test the endpoint**

Run: `curl -s http://localhost:8000/chart/FAF | python3 -c "import sys,json; d=json.load(sys.stdin); print('points:', len(d['ohlc']), 'support:', d['support'], 'resistance:', d['resistance'], 'ma50:', d['ma50'])"`
Expected: `points: ~63 support: XX.XX resistance: XX.XX ma50: XX.XX`

- [ ] **Step 3: Commit**

```bash
git add src/api.py
git commit -m "feat: add /chart/{ticker} endpoint — OHLC + support/resistance for mini chart"
```

### Task 5: Thesis Generator Module

**Files:**
- Create: `src/thesis.py`
- Modify: `src/api.py` (add `/thesis/{ticker}` endpoint)

- [ ] **Step 1: Create `src/thesis.py` with template-based thesis generator**

```python
"""Generate one-liner thesis explaining why a stock is interesting right now."""

import logging
from typing import Optional

logger = logging.getLogger(__name__)


def generate_thesis(stock: dict) -> str:
    """Generate a template-based thesis from scan result data.

    Args:
        stock: A stock dict from scan results (top or all_scores format).

    Returns:
        A one-liner thesis string, e.g.:
        "RSI 28 (oversold) + $4M insider buying. 32% below analyst target."
    """
    points = []

    # RSI extremes
    rsi = stock.get("rsi")
    if rsi is not None:
        if rsi < 30:
            points.append(("rsi_oversold", 10, f"RSI {rsi:.0f} (oversold)"))
        elif rsi < 35:
            points.append(("rsi_low", 5, f"RSI {rsi:.0f} (near oversold)"))
        elif rsi > 70:
            points.append(("rsi_overbought", 8, f"RSI {rsi:.0f} (overbought)"))

    # Insider activity
    insider_buy = stock.get("insider_buy_value") or 0
    insider_sell = stock.get("insider_sell_value") or 0
    if insider_buy > 1_000_000:
        points.append(("insider_buy", 9, f"${insider_buy / 1e6:.1f}M insider buying"))
    elif insider_buy > 100_000:
        points.append(("insider_buy", 6, f"${insider_buy / 1e3:.0f}K insider buying"))
    if insider_sell > 1_000_000:
        points.append(("insider_sell", 7, f"${insider_sell / 1e6:.1f}M insider selling"))

    # Earnings streak
    consecutive = stock.get("consecutive_days") or 0
    if consecutive >= 5:
        points.append(("streak", 7, f"{consecutive}-day streak in top 20"))

    # Analyst target upside
    sentiment = stock.get("sentiment")
    if isinstance(sentiment, dict):
        pt_upside = sentiment.get("pt_upside_pct") or 0
        if pt_upside > 0.2:
            points.append(("target_upside", 8, f"{pt_upside * 100:.0f}% below analyst target"))
        recommendation = sentiment.get("recommendation", "")
        if recommendation in ("strongBuy", "buy"):
            analyst_count = sentiment.get("analyst_count", 0)
            if analyst_count >= 5:
                points.append(("analyst_buy", 5, f"analysts say {recommendation} ({analyst_count})"))

    # Bollinger squeeze
    # ADX strength (from entry_score context — check adx field)
    adx = stock.get("adx")
    if adx is not None and adx > 30:
        points.append(("adx_strong", 6, f"ADX {adx:.0f} (strong trend)"))

    # Valuation
    pe = stock.get("pe_ratio")
    if pe is not None and 0 < pe < 12:
        points.append(("low_pe", 5, f"P/E {pe:.1f}"))

    # DCF upside
    dcf_mos = stock.get("dcf_margin_of_safety")
    if dcf_mos is not None and dcf_mos > 20:
        points.append(("dcf_undervalued", 7, f"{dcf_mos:.0f}% DCF margin of safety"))

    # 52w position (from current_price vs sentiment or other fields)
    # Revenue growth
    rev_growth = stock.get("revenue_growth")
    if rev_growth is not None and rev_growth > 0.15:
        points.append(("rev_growth", 5, f"{rev_growth * 100:.0f}% revenue growth"))

    # Quality
    piotroski = stock.get("piotroski_score")
    if piotroski is not None and piotroski >= 7:
        points.append(("piotroski", 4, f"Piotroski {piotroski}/9"))

    # Smart money
    smart_money = stock.get("smart_money_score")
    if smart_money is not None and smart_money > 70:
        points.append(("smart_money", 6, f"smart money score {smart_money:.0f}"))

    if not points:
        return "No standout signals"

    # Sort by priority (descending), take top 3
    points.sort(key=lambda x: x[1], reverse=True)
    top = points[:3]
    return " + ".join(p[2] for p in top)


def generate_gemini_thesis(ticker: str) -> Optional[dict]:
    """Generate a Gemini-powered bull thesis for a stock.

    Returns: {ticker, thesis, source: "gemini"} or None on failure.
    """
    import os

    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        return None

    # Collect data
    from .devils_advocate import _collect_data
    data = _collect_data(ticker)

    import google.generativeai as genai
    genai.configure(api_key=api_key)
    model = genai.GenerativeModel("gemini-2.5-flash")

    prompt = f"""You are a bullish stock analyst. Given this data for {ticker} ({data.get('company_name', ticker)}), 
write a concise 2-3 sentence investment thesis explaining why NOW is a good time to buy this stock.

Focus on: entry timing, catalysts, valuation, momentum, and any unique advantages.
Be specific with numbers. Don't hedge — make a confident case.

Data:
- Sector: {data.get('sector')} / {data.get('industry')}
- Price: ${data.get('current_price')}
- Forward P/E: {data.get('forward_pe')}
- Revenue Growth: {(data.get('revenue_growth', 0) or 0) * 100:.1f}%
- Earnings Growth: {(data.get('earnings_growth', 0) or 0) * 100:.1f}%
- Profit Margin: {(data.get('profit_margin', 0) or 0) * 100:.1f}%
- ROE: {(data.get('roe', 0) or 0) * 100:.1f}%
- Beta: {data.get('beta')}
- D/E: {data.get('debt_to_equity', 0):.2f}
- 52w Range: ${data.get('52w_low')} - ${data.get('52w_high')}
- Analyst Target: ${data.get('analyst_target')} ({data.get('recommendation')})
- Insider Buys 2026: {data.get('insider_buys_count', 0)} totaling ${data.get('insider_buy_value', 0):,.0f}
"""

    try:
        response = model.generate_content(prompt)
        return {"ticker": ticker, "thesis": response.text.strip(), "source": "gemini"}
    except Exception as e:
        logger.warning("Gemini thesis failed for %s: %s", ticker, e)
        return None
```

- [ ] **Step 2: Test template thesis with real data**

Run:
```bash
cd /Users/zhuorantang/clawd/stock-picker && python3 -c "
import json
from src.thesis import generate_thesis
scan = json.load(open('data/scan_results.json'))
for s in scan['top'][:5]:
    print(f\"{s['ticker']}: {generate_thesis(s)}\")
"
```
Expected: One-liner thesis for each of the top 5 stocks

- [ ] **Step 3: Add `/thesis/{ticker}` endpoint in `api.py`**

Add near the `/review/{ticker}` endpoint:

```python
@app.get("/thesis/{ticker}")
async def thesis(ticker: str):
    """Gemini-powered bull thesis for a stock."""
    import asyncio
    from .thesis import generate_gemini_thesis
    result = await asyncio.to_thread(generate_gemini_thesis, ticker.upper())
    if result is None:
        return {"ticker": ticker.upper(), "thesis": None, "source": "unavailable"}
    return result
```

- [ ] **Step 4: Integrate template thesis into scan pipeline**

In `src/pipeline.py`, find where `ranked` stocks are built (around line 505–548). After the dict is created for each stock but before appending, add:

```python
            from .thesis import generate_thesis
```

At the top of the loop, and add this field to the stock dict:

```python
            "thesis": generate_thesis({...the_stock_dict...}),
```

Since the dict is being built inline, the simplest approach: after `ranked.append(stock_dict)`, do:

```python
            ranked[-1]["thesis"] = generate_thesis(ranked[-1])
```

Also add the same for the `all_scores` section (around line 931–968) — after each all_scores dict is built:

```python
            all_entry["thesis"] = generate_thesis(all_entry)
```

- [ ] **Step 5: Test that scan results now include thesis**

Run: `curl -s 'http://localhost:8000/scan?force=true' -H "X-API-Key: stock-picker"` then wait for completion, then:
`curl -s http://localhost:8000/scan/cached | python3 -c "import sys,json; d=json.load(sys.stdin); [print(s['ticker'], ':', s.get('thesis', 'MISSING')) for s in d['top'][:5]]"`

Expected: Each ticker followed by a thesis one-liner

- [ ] **Step 6: Commit**

```bash
git add src/thesis.py src/api.py src/pipeline.py
git commit -m "feat: add thesis generator — template-based in scan + Gemini on-demand endpoint"
```

### Task 6: Watchlist Backend

**Files:**
- Modify: `src/api.py` (add 3 watchlist endpoints)

- [ ] **Step 1: Add watchlist endpoints in `api.py`**

Add near the other endpoints (before the static file serving section):

```python
@app.get("/watchlist")
async def get_watchlist():
    """Return watchlist with current prices and deltas."""
    watchlist_file = DATA_DIR / "watchlist.json"
    if not watchlist_file.exists():
        return {"tickers": {}}

    data = json.loads(watchlist_file.read_text())
    tickers = data.get("tickers", {})

    # Enrich with current prices from cache
    cache_file = DATA_DIR / "stock_data_cache.json"
    if cache_file.exists():
        cache = json.loads(cache_file.read_text())
        for ticker, wdata in tickers.items():
            if ticker in cache:
                close_list = cache[ticker].get("history", {}).get("Close", [])
                valid = [c for c in close_list if c is not None and not (isinstance(c, float) and __import__("math").isnan(c))]
                if valid:
                    current = valid[-1]
                    wdata["current_price"] = round(current, 2)
                    price_at_add = wdata.get("price_at_add", 0)
                    if price_at_add > 0:
                        wdata["change_pct"] = round((current - price_at_add) / price_at_add * 100, 2)
                    else:
                        wdata["change_pct"] = 0

    return {"tickers": tickers}


@app.post("/watchlist/{ticker}")
async def add_to_watchlist(ticker: str):
    """Add a ticker to the watchlist."""
    ticker = ticker.upper()
    watchlist_file = DATA_DIR / "watchlist.json"

    if watchlist_file.exists():
        data = json.loads(watchlist_file.read_text())
    else:
        data = {"tickers": {}}

    if ticker in data["tickers"]:
        return {"status": "already_exists", "ticker": ticker}

    # Get current price from cache
    price = None
    cache_file = DATA_DIR / "stock_data_cache.json"
    if cache_file.exists():
        cache = json.loads(cache_file.read_text())
        if ticker in cache:
            close_list = cache[ticker].get("history", {}).get("Close", [])
            valid = [c for c in close_list if c is not None and not (isinstance(c, float) and __import__("math").isnan(c))]
            if valid:
                price = round(valid[-1], 2)

    data["tickers"][ticker] = {
        "added": __import__("datetime").date.today().isoformat(),
        "price_at_add": price,
    }
    watchlist_file.write_text(json.dumps(data, indent=2))
    return {"status": "added", "ticker": ticker, "price_at_add": price}


@app.delete("/watchlist/{ticker}")
async def remove_from_watchlist(ticker: str):
    """Remove a ticker from the watchlist."""
    ticker = ticker.upper()
    watchlist_file = DATA_DIR / "watchlist.json"

    if not watchlist_file.exists():
        return {"status": "not_found", "ticker": ticker}

    data = json.loads(watchlist_file.read_text())
    if ticker not in data.get("tickers", {}):
        return {"status": "not_found", "ticker": ticker}

    del data["tickers"][ticker]
    watchlist_file.write_text(json.dumps(data, indent=2))
    return {"status": "removed", "ticker": ticker}
```

- [ ] **Step 2: Test watchlist endpoints**

Run:
```bash
# Add
curl -s -X POST http://localhost:8000/watchlist/LVS | python3 -m json.tool
# List
curl -s http://localhost:8000/watchlist | python3 -m json.tool
# Remove
curl -s -X DELETE http://localhost:8000/watchlist/LVS | python3 -m json.tool
```

Expected: `{"status": "added", ...}`, then list with current_price and change_pct, then `{"status": "removed", ...}`

- [ ] **Step 3: Commit**

```bash
git add src/api.py
git commit -m "feat: add watchlist API — GET/POST/DELETE /watchlist endpoints"
```

### Task 7: Frontend — Price Chart Component

**Files:**
- Create: `frontend/src/components/ticker/PriceChart.tsx`
- Modify: `frontend/src/lib/api.ts` (add `chart` method)
- Modify: `frontend/src/lib/types.ts` (add `ChartData` type)

- [ ] **Step 1: Add types and API method**

In `frontend/src/lib/types.ts`, add at the end:

```typescript
export interface ChartPoint {
  date: string;
  open: number | null;
  high: number | null;
  low: number | null;
  close: number;
}

export interface ChartData {
  ticker: string;
  ohlc: ChartPoint[];
  support: number | null;
  resistance: number | null;
  ma50: number | null;
}

export interface WatchlistEntry {
  added: string;
  price_at_add: number | null;
  current_price?: number;
  change_pct?: number;
}

export interface WatchlistResponse {
  tickers: Record<string, WatchlistEntry>;
}

export interface ThesisResponse {
  ticker: string;
  thesis: string | null;
  source: string;
}
```

In `frontend/src/lib/api.ts`, add to the `api` object:

```typescript
  chart: (ticker: string, period = "3mo") =>
    get<import("./types").ChartData>(`/chart/${ticker}?period=${period}`),
  watchlist: () => get<import("./types").WatchlistResponse>("/watchlist"),
  addToWatchlist: (ticker: string) =>
    fetch(`/watchlist/${ticker}`, { method: "POST" }).then((r) => r.json()),
  removeFromWatchlist: (ticker: string) =>
    fetch(`/watchlist/${ticker}`, { method: "DELETE" }).then((r) => r.json()),
  thesis: (ticker: string) =>
    get<import("./types").ThesisResponse>(`/thesis/${ticker}`),
```

- [ ] **Step 2: Create `PriceChart.tsx`**

```tsx
import { useEffect, useState } from "react";
import {
  ResponsiveContainer,
  AreaChart,
  Area,
  XAxis,
  YAxis,
  ReferenceLine,
  Tooltip,
} from "recharts";
import { api } from "../../lib/api";
import type { ChartData } from "../../lib/types";

interface PriceChartProps {
  ticker: string;
}

export default function PriceChart({ ticker }: PriceChartProps) {
  const [data, setData] = useState<ChartData | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    setLoading(true);
    api
      .chart(ticker)
      .then(setData)
      .catch(() => setData(null))
      .finally(() => setLoading(false));
  }, [ticker]);

  if (loading) return <div className="h-48 flex items-center justify-center text-text-muted text-sm">Loading chart...</div>;
  if (!data || data.ohlc.length === 0) return null;

  const closes = data.ohlc.map((d) => d.close);
  const minPrice = Math.min(...closes) * 0.98;
  const maxPrice = Math.max(...closes) * 1.02;
  const lastPrice = closes[closes.length - 1];
  const firstPrice = closes[0];
  const isUp = lastPrice >= firstPrice;

  return (
    <div className="rounded-xl bg-surface border border-border p-4 mb-4">
      <div className="flex justify-between items-center mb-2">
        <span className="text-xs font-semibold text-text-muted uppercase tracking-wider">3-Month Price</span>
        <span className={`text-xs font-data font-semibold ${isUp ? "text-positive" : "text-danger"}`}>
          {isUp ? "+" : ""}{((lastPrice - firstPrice) / firstPrice * 100).toFixed(1)}%
        </span>
      </div>
      <ResponsiveContainer width="100%" height={180}>
        <AreaChart data={data.ohlc} margin={{ top: 5, right: 5, bottom: 0, left: 0 }}>
          <defs>
            <linearGradient id={`gradient-${ticker}`} x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor={isUp ? "#34d399" : "#f87171"} stopOpacity={0.3} />
              <stop offset="100%" stopColor={isUp ? "#34d399" : "#f87171"} stopOpacity={0} />
            </linearGradient>
          </defs>
          <XAxis
            dataKey="date"
            tick={{ fontSize: 10, fill: "#556481" }}
            tickLine={false}
            axisLine={false}
            tickFormatter={(v: string) => v.slice(5)}
            interval={Math.floor(data.ohlc.length / 5)}
          />
          <YAxis
            domain={[minPrice, maxPrice]}
            tick={{ fontSize: 10, fill: "#556481" }}
            tickLine={false}
            axisLine={false}
            tickFormatter={(v: number) => `$${v.toFixed(0)}`}
            width={45}
          />
          <Tooltip
            contentStyle={{ background: "#111827", border: "1px solid #1e2d4a", borderRadius: "8px", fontSize: "12px" }}
            labelStyle={{ color: "#8b97b0" }}
            formatter={(v: number) => [`$${v.toFixed(2)}`, "Close"]}
          />
          {data.support && (
            <ReferenceLine y={data.support} stroke="#34d399" strokeDasharray="4 4" strokeOpacity={0.6} />
          )}
          {data.resistance && (
            <ReferenceLine y={data.resistance} stroke="#f87171" strokeDasharray="4 4" strokeOpacity={0.6} />
          )}
          {data.ma50 && (
            <ReferenceLine y={data.ma50} stroke="#556481" strokeDasharray="2 2" strokeOpacity={0.4} />
          )}
          <Area
            type="monotone"
            dataKey="close"
            stroke={isUp ? "#34d399" : "#f87171"}
            strokeWidth={1.5}
            fill={`url(#gradient-${ticker})`}
          />
        </AreaChart>
      </ResponsiveContainer>
      <div className="flex gap-4 mt-1 text-[10px] text-text-muted">
        {data.support && <span><span className="inline-block w-3 h-px bg-positive mr-1 align-middle" style={{ borderTop: "1px dashed #34d399" }} />Support ${data.support.toFixed(2)}</span>}
        {data.resistance && <span><span className="inline-block w-3 h-px bg-danger mr-1 align-middle" style={{ borderTop: "1px dashed #f87171" }} />Resistance ${data.resistance.toFixed(2)}</span>}
        {data.ma50 && <span><span className="inline-block w-3 h-px mr-1 align-middle" style={{ borderTop: "1px dashed #556481" }} />MA50 ${data.ma50.toFixed(2)}</span>}
      </div>
    </div>
  );
}
```

- [ ] **Step 3: Add PriceChart to TickerModal**

In `frontend/src/components/ticker/TickerModal.tsx`, add import at the top:

```typescript
import PriceChart from "./PriceChart";
```

Then add `<PriceChart ticker={stock.ticker} />` right before the grid that contains RadarChart and KeyMetrics (the `grid grid-cols-[220px_1fr]` div). This places the chart above the scores section.

- [ ] **Step 4: Build and verify**

Run: `cd /Users/zhuorantang/clawd/stock-picker/frontend && npm run build`
Expected: Build succeeds with no errors

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/ticker/PriceChart.tsx frontend/src/lib/api.ts frontend/src/lib/types.ts frontend/src/components/ticker/TickerModal.tsx
git commit -m "feat: add mini price chart with support/resistance to ticker modal"
```

### Task 8: Frontend — Position Size Calculator

**Files:**
- Create: `frontend/src/components/ticker/PositionSizer.tsx`
- Modify: `frontend/src/components/ticker/TickerModal.tsx`

- [ ] **Step 1: Create `PositionSizer.tsx`**

```tsx
import { useState, useEffect } from "react";
import { api } from "../../lib/api";
import type { RiskSummary } from "../../lib/types";

interface PositionSizerProps {
  ticker: string;
  currentPrice: number;
}

export default function PositionSizer({ ticker, currentPrice }: PositionSizerProps) {
  const [riskPct, setRiskPct] = useState(() => {
    const saved = localStorage.getItem("positionSizer_riskPct");
    return saved ? parseFloat(saved) : 2;
  });
  const [portfolioValue, setPortfolioValue] = useState<number | null>(null);
  const stopLossPct = 15;

  useEffect(() => {
    api.riskSummary().then((r: RiskSummary) => setPortfolioValue(r.portfolio_value ?? 0)).catch(() => {});
  }, []);

  useEffect(() => {
    localStorage.setItem("positionSizer_riskPct", String(riskPct));
  }, [riskPct]);

  if (!portfolioValue || currentPrice <= 0) return null;

  const riskPerTrade = portfolioValue * (riskPct / 100);
  const stopDistance = currentPrice * (stopLossPct / 100);
  const shares = Math.floor(riskPerTrade / stopDistance);
  const dollarAmount = shares * currentPrice;
  const weightPct = (dollarAmount / portfolioValue) * 100;
  const stopPrice = currentPrice * (1 - stopLossPct / 100);

  return (
    <div className="rounded-xl bg-surface border border-border p-4 mb-4">
      <div className="flex justify-between items-center mb-3">
        <span className="text-xs font-semibold text-text-muted uppercase tracking-wider">Position Sizer</span>
        <div className="flex items-center gap-2">
          <span className="text-[11px] text-text-muted">Risk:</span>
          <input
            type="range"
            min={0.5}
            max={5}
            step={0.5}
            value={riskPct}
            onChange={(e) => setRiskPct(parseFloat(e.target.value))}
            className="w-20 h-1 accent-accent"
          />
          <span className="text-xs font-data text-accent font-semibold w-8">{riskPct}%</span>
        </div>
      </div>
      <div className="grid grid-cols-4 gap-3">
        <div>
          <div className="text-[11px] text-text-muted">Shares</div>
          <div className="text-lg font-bold text-text-primary font-data">{shares}</div>
        </div>
        <div>
          <div className="text-[11px] text-text-muted">Amount</div>
          <div className="text-lg font-bold text-text-primary font-data">${dollarAmount.toLocaleString()}</div>
        </div>
        <div>
          <div className="text-[11px] text-text-muted">Weight</div>
          <div className="text-lg font-bold text-text-primary font-data">{weightPct.toFixed(1)}%</div>
        </div>
        <div>
          <div className="text-[11px] text-text-muted">Stop at</div>
          <div className="text-lg font-bold text-danger font-data">${stopPrice.toFixed(2)}</div>
        </div>
      </div>
      <div className="text-[11px] text-text-muted mt-2">
        Risking ${riskPerTrade.toFixed(0)} ({riskPct}% of ${portfolioValue.toLocaleString()}) with {stopLossPct}% stop-loss
      </div>
    </div>
  );
}
```

- [ ] **Step 2: Add PositionSizer to TickerModal**

In `frontend/src/components/ticker/TickerModal.tsx`, add import:

```typescript
import PositionSizer from "./PositionSizer";
```

Add `<PositionSizer ticker={stock.ticker} currentPrice={stock.current_price ?? 0} />` right after the `<PriceChart>` component (before the grid with RadarChart/KeyMetrics).

- [ ] **Step 3: Build and verify**

Run: `cd /Users/zhuorantang/clawd/stock-picker/frontend && npm run build`
Expected: Build succeeds

- [ ] **Step 4: Commit**

```bash
git add frontend/src/components/ticker/PositionSizer.tsx frontend/src/components/ticker/TickerModal.tsx
git commit -m "feat: add risk-based position size calculator to ticker modal"
```

### Task 9: Frontend — Thesis in Scanner Row

**Files:**
- Modify: `frontend/src/lib/types.ts` (add `thesis` to Stock)
- Modify: `frontend/src/components/scanner/ScannerRow.tsx`

- [ ] **Step 1: Add `thesis` field to Stock type**

In `frontend/src/lib/types.ts`, find the `Stock` interface and add:

```typescript
  thesis?: string;
```

- [ ] **Step 2: Add thesis one-liner to ScannerRow**

In `frontend/src/components/scanner/ScannerRow.tsx`, find the second `<td>` (the one showing `stock.ticker` and `stock.name`). Replace that cell with an expanded version that includes the thesis:

Find:
```tsx
      <td className="py-2.5 px-3">
        <div className="text-sm font-bold text-text-primary">{stock.ticker}</div>
        <div className="text-[11px] text-text-muted truncate max-w-[140px]">{stock.name}</div>
      </td>
```

Replace with:
```tsx
      <td className="py-2.5 px-3">
        <div className="text-sm font-bold text-text-primary">{stock.ticker}</div>
        <div className="text-[11px] text-text-muted truncate max-w-[140px]">{stock.name}</div>
        {stock.thesis && (
          <div className="text-[10px] text-accent/70 truncate max-w-[220px] mt-0.5">{stock.thesis}</div>
        )}
      </td>
```

- [ ] **Step 3: Build and verify**

Run: `cd /Users/zhuorantang/clawd/stock-picker/frontend && npm run build`
Expected: Build succeeds

- [ ] **Step 4: Commit**

```bash
git add frontend/src/lib/types.ts frontend/src/components/scanner/ScannerRow.tsx
git commit -m "feat: show thesis one-liner in scanner rows"
```

### Task 10: Frontend — Watchlist Page + Star Button

**Files:**
- Create: `frontend/src/pages/Watchlist.tsx`
- Modify: `frontend/src/App.tsx` (add route)
- Modify: `frontend/src/components/layout/Sidebar.tsx` (add nav item)
- Modify: `frontend/src/components/scanner/ScannerRow.tsx` (add star)
- Modify: `frontend/src/components/ticker/TickerModal.tsx` (add star)

- [ ] **Step 1: Create `Watchlist.tsx` page**

```tsx
import { useState } from "react";
import { motion } from "framer-motion";
import { useApi } from "../hooks/useApi";
import { useScan } from "../App";
import { api } from "../lib/api";
import { pnlColor } from "../lib/colors";
import type { WatchlistResponse } from "../lib/types";
import TickerModal from "../components/ticker/TickerModal";
import type { Stock } from "../lib/types";

const fadeUp = {
  hidden: { opacity: 0, y: 12 },
  show: { opacity: 1, y: 0, transition: { duration: 0.4 } },
};

export default function Watchlist() {
  const { data, refetch } = useApi<WatchlistResponse>(() => api.watchlist());
  const { scan } = useScan();
  const [selectedStock, setSelectedStock] = useState<Stock | null>(null);

  if (!data) return <div className="text-text-secondary">Loading watchlist...</div>;

  const tickers = Object.entries(data.tickers);

  const findStock = (ticker: string): Stock | undefined =>
    scan?.top.find((s) => s.ticker === ticker) ?? scan?.all_scores.find((s) => s.ticker === ticker);

  const handleRemove = async (ticker: string) => {
    await api.removeFromWatchlist(ticker);
    refetch();
  };

  return (
    <motion.div variants={fadeUp} initial="hidden" animate="show">
      <div className="flex justify-between items-center mb-5">
        <div>
          <h1 className="text-xl font-bold text-text-primary">Watchlist</h1>
          <div className="text-[13px] text-text-secondary">{tickers.length} stocks tracked</div>
        </div>
      </div>

      {tickers.length === 0 ? (
        <div className="text-center py-16 text-text-muted">
          <div className="text-4xl mb-3">⭐</div>
          <div className="text-sm">No stocks in watchlist yet.</div>
          <div className="text-xs mt-1">Click the star on any stock in the Scanner to add it.</div>
        </div>
      ) : (
        <div className="rounded-xl border border-border overflow-hidden">
          <table className="w-full text-sm">
            <thead>
              <tr className="bg-surface text-[11px] text-text-muted uppercase tracking-wider">
                <th className="py-2.5 px-3 text-left">Ticker</th>
                <th className="py-2.5 px-3 text-left">Added</th>
                <th className="py-2.5 px-3 text-right">Price Then</th>
                <th className="py-2.5 px-3 text-right">Price Now</th>
                <th className="py-2.5 px-3 text-right">Change</th>
                <th className="py-2.5 px-3 text-center">Signal</th>
                <th className="py-2.5 px-3 text-right">Score</th>
                <th className="py-2.5 px-3 text-center"></th>
              </tr>
            </thead>
            <tbody>
              {tickers.map(([ticker, wdata]) => {
                const stock = findStock(ticker);
                const changePct = wdata.change_pct ?? 0;
                return (
                  <tr
                    key={ticker}
                    className="border-t border-border hover:bg-white/[0.03] cursor-pointer transition-colors"
                    onClick={() => stock && setSelectedStock(stock)}
                  >
                    <td className="py-2.5 px-3">
                      <span className="font-bold text-text-primary">{ticker}</span>
                    </td>
                    <td className="py-2.5 px-3 text-text-secondary font-data">{wdata.added}</td>
                    <td className="py-2.5 px-3 text-right text-text-secondary font-data">
                      ${wdata.price_at_add?.toFixed(2) ?? "—"}
                    </td>
                    <td className="py-2.5 px-3 text-right text-text-primary font-data font-semibold">
                      ${wdata.current_price?.toFixed(2) ?? "—"}
                    </td>
                    <td className={`py-2.5 px-3 text-right font-data font-semibold ${pnlColor(changePct)}`}>
                      {changePct >= 0 ? "+" : ""}{changePct.toFixed(2)}%
                    </td>
                    <td className="py-2.5 px-3 text-center text-xs">
                      {stock?.entry_signal ?? "—"}
                    </td>
                    <td className="py-2.5 px-3 text-right font-data">
                      {stock?.composite_score?.toFixed(1) ?? "—"}
                    </td>
                    <td className="py-2.5 px-3 text-center">
                      <button
                        onClick={(e) => { e.stopPropagation(); handleRemove(ticker); }}
                        className="text-text-muted hover:text-danger transition-colors text-xs"
                        title="Remove from watchlist"
                      >
                        ✕
                      </button>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}

      {selectedStock && (
        <TickerModal stock={selectedStock} onClose={() => setSelectedStock(null)} />
      )}
    </motion.div>
  );
}
```

- [ ] **Step 2: Add Watchlist route in `App.tsx`**

Import at top:
```typescript
import Watchlist from "./pages/Watchlist";
```

Add route inside `<Routes>`, after the Momentum route:
```tsx
<Route path="/watchlist" element={<Watchlist />} />
```

- [ ] **Step 3: Add Watchlist to Sidebar**

In `frontend/src/components/layout/Sidebar.tsx`, add to the nav items array:

```typescript
{ to: "/watchlist", icon: "⭐", label: "Watchlist" },
```

Add it after the Momentum item.

- [ ] **Step 4: Add watchlist star to ScannerRow**

In `frontend/src/components/scanner/ScannerRow.tsx`, add a star button as the first cell (before rank). Add props for watchlist state:

Update the `ScannerRowProps` interface:
```typescript
interface ScannerRowProps {
  stock: Stock;
  rank: number;
  sparkline: number[];
  scoreDelta: number | null;
  onClick: () => void;
  isWatched?: boolean;
  onToggleWatch?: (ticker: string) => void;
}
```

Add a new `<td>` as the first column:
```tsx
      <td className="py-2.5 px-1.5 text-center w-8">
        <button
          onClick={(e) => { e.stopPropagation(); onToggleWatch?.(stock.ticker); }}
          className={`text-sm transition-colors ${isWatched ? "text-caution" : "text-text-muted/30 hover:text-caution/60"}`}
          title={isWatched ? "Remove from watchlist" : "Add to watchlist"}
        >
          {isWatched ? "★" : "☆"}
        </button>
      </td>
```

- [ ] **Step 5: Wire up watchlist state in Scanner page**

In `frontend/src/pages/Scanner.tsx`, add watchlist state management. Read the file first to understand its current structure, then:

Add imports and state:
```typescript
import { useState, useEffect } from "react";
import { api } from "../lib/api";
```

Add inside the component:
```typescript
const [watchedTickers, setWatchedTickers] = useState<Set<string>>(new Set());

useEffect(() => {
  api.watchlist().then((w) => setWatchedTickers(new Set(Object.keys(w.tickers)))).catch(() => {});
}, []);

const toggleWatch = async (ticker: string) => {
  if (watchedTickers.has(ticker)) {
    await api.removeFromWatchlist(ticker);
    setWatchedTickers((prev) => { const next = new Set(prev); next.delete(ticker); return next; });
  } else {
    await api.addToWatchlist(ticker);
    setWatchedTickers((prev) => new Set(prev).add(ticker));
  }
};
```

Pass to ScannerRow:
```tsx
<ScannerRow ... isWatched={watchedTickers.has(stock.ticker)} onToggleWatch={toggleWatch} />
```

- [ ] **Step 6: Build and verify**

Run: `cd /Users/zhuorantang/clawd/stock-picker/frontend && npm run build`
Expected: Build succeeds

- [ ] **Step 7: Commit**

```bash
git add frontend/src/pages/Watchlist.tsx frontend/src/App.tsx frontend/src/components/layout/Sidebar.tsx frontend/src/components/scanner/ScannerRow.tsx frontend/src/pages/Scanner.tsx
git commit -m "feat: add watchlist page, star button in scanner, sidebar nav item"
```

### Task 11: Frontend Build + End-to-End Verification

**Files:** None new — verification only

- [ ] **Step 1: Rebuild frontend**

Run: `cd /Users/zhuorantang/clawd/stock-picker/frontend && npm run build`
Expected: Clean build, no errors

- [ ] **Step 2: Force a scan to populate thesis field**

Run: `curl -s 'http://localhost:8000/scan?force=true' -H "X-API-Key: stock-picker"`
Wait for completion: `sleep 45 && curl -s http://localhost:8000/scan/status`

- [ ] **Step 3: Verify all new endpoints**

```bash
# Chart
curl -s http://localhost:8000/chart/FAF | python3 -c "import sys,json; d=json.load(sys.stdin); print('Chart:', len(d['ohlc']), 'points')"

# Cache health
curl -s http://localhost:8000/cache/health | python3 -m json.tool

# Watchlist add
curl -s -X POST http://localhost:8000/watchlist/LVS | python3 -m json.tool

# Watchlist list
curl -s http://localhost:8000/watchlist | python3 -m json.tool

# Watchlist remove
curl -s -X DELETE http://localhost:8000/watchlist/LVS | python3 -m json.tool

# Thesis (if GEMINI_API_KEY is set)
curl -s http://localhost:8000/thesis/FAF | python3 -m json.tool

# Scan results have thesis field
curl -s http://localhost:8000/scan/cached | python3 -c "import sys,json; d=json.load(sys.stdin); [print(s['ticker'], ':', s.get('thesis', 'MISSING')) for s in d['top'][:3]]"
```

- [ ] **Step 4: Manual browser check**

Open `http://localhost:8000/#/scanner` — verify:
1. Scanner rows show thesis one-liner in teal below the ticker name
2. Star button visible on each row
3. Click a stock → modal opens with price chart + position sizer above the tabs
4. Navigate to Watchlist page via sidebar

- [ ] **Step 5: Final commit if any fixes needed**

```bash
git add -A
git commit -m "fix: end-to-end verification fixes"
```
