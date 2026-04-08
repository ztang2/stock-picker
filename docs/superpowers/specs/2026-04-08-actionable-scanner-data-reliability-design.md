# Actionable Scanner + Data Reliability — Design Spec

**Date:** 2026-04-08
**Status:** Approved

## Goal

Two independent improvements to the stock-picker app:
1. Transform the scanner from a ranking list into an actionable trade-decision tool
2. Eliminate stale/NaN data issues that cause blank prices and unreliable signals

## Workstream 1: Actionable Scanner

### 1.1 Mini Price Chart with Entry Zone

**What:** 3-month line chart for each stock in the ticker modal, showing support/resistance levels as highlighted zones.

**Backend:**
- `GET /chart/{ticker}?period=3mo` — returns OHLC array + support/resistance levels from momentum module
- Data source: `stock_data_cache.json` history (already cached), fall back to yfinance if missing

**Frontend:**
- New `PriceChart.tsx` component using Recharts (already in deps)
- Line chart with:
  - Close price line
  - Support level as green dashed line / shaded zone
  - Resistance level as red dashed line / shaded zone
  - Current price marker
  - MA50 line (grey, subtle)
- Rendered in the ticker modal as a new section above the tabs
- Responsive — fills modal width

### 1.2 Risk-Based Position Size Calculator

**What:** For each stock, suggest how many shares to buy based on portfolio value, risk budget, and stop-loss distance.

**Formula:**
```
risk_per_trade = portfolio_value * risk_pct  (default 2%)
stop_distance = current_price * stop_loss_pct  (default 15%)
shares = risk_per_trade / stop_distance
dollar_amount = shares * current_price
weight_pct = dollar_amount / portfolio_value * 100
```

**Backend:**
- No new endpoint needed — calculate client-side using data already available from `/risk/summary` (portfolio_value) and `/scan/cached` (current_price)
- Risk % configurable, stored in `localStorage` (default 2%)

**Frontend:**
- New `PositionSizer.tsx` component in ticker modal
- Shows: "Buy **X shares** ($Y) — risking $Z (2% of portfolio) to stop at $W"
- Slider or input to adjust risk % (1-5%)
- Adjusts dynamically as user changes risk tolerance

### 1.3 Watchlist

**What:** Save stocks you're interested in but not ready to buy. Track price movement since added.

**Backend:**
- `data/watchlist.json` — `{"tickers": {"FAF": {"added": "2026-04-08", "price_at_add": 60.84}, ...}}`
- `GET /watchlist` — returns watchlist with current prices and delta since added
- `POST /watchlist/{ticker}` — add ticker (records current price + date)
- `DELETE /watchlist/{ticker}` — remove ticker

**Frontend:**
- "Add to Watchlist" star/button in scanner rows and ticker modal
- New **Watchlist** page (add to sidebar nav):
  - Table: ticker, date added, price then, price now, change %, entry signal, composite score
  - Click row opens ticker modal
  - Remove button per row
- Visual indicator on scanner rows for stocks already in watchlist

### 1.4 "Why Now" Thesis

**What:** One-liner explaining why this stock is interesting right now.

**Template-based (scanner row):**
Stitched from data points using rules. Examples:
- "RSI 28 (oversold) + $4M insider buying + 3 earnings beats. 32% below target."
- "Bollinger squeeze + ADX 35 (strong trend) + 21% revenue growth."
- "Near 52w low, P/E 8.6 vs sector 15.2, analysts say Strong Buy."

Logic: pick top 3 most notable data points from: RSI extremes, insider activity, earnings streak, distance to analyst target, Bollinger squeeze, ADX strength, valuation vs sector, 52w position.

**Backend:**
- `src/thesis.py` — `generate_thesis(stock_data: dict) -> str`
- Called during scan, stored in scan results as `thesis` field
- No Gemini dependency for the template version

**Gemini on-demand (modal):**
- Existing Devil's Advocate already calls Gemini — add a "bull thesis" prompt variant
- New endpoint: `GET /thesis/{ticker}` — returns Gemini-generated thesis (async, like `/review`)
- Frontend: "Why Now" section in ticker modal, loads on-demand when modal opens

## Workstream 2: Data Reliability

### 2.1 Auto-heal Cache

**What:** Before every scan, validate the cache and fix bad data.

**New module: `src/cache_health.py`**

```python
def heal_cache(cache_path: str) -> dict:
    """Detect and fix NaN/stale data in stock_data_cache.json.
    
    Returns: {healed: int, dropped: int, total: int, errors: []}
    """
```

**Logic:**
1. Load `stock_data_cache.json`
2. For each ticker:
   - Check if last Close is NaN → drop that row (like the fix we applied today)
   - Check if last date is >2 trading days old → mark as stale
3. For stale tickers (up to 50 at a time to avoid rate limits):
   - Re-fetch from yfinance with `period="1y"`
   - Replace in cache
4. Save updated cache
5. Return health report

**Integration:**
- Called at the start of `run_scan()` in `pipeline.py`
- Health report logged and optionally returned in scan results

**Endpoint:**
- `GET /cache/health` — returns current cache health without healing (read-only diagnostic)

### 2.2 Scheduled Cache Refresh

**What:** Cron job that auto-refreshes the full cache after market close.

**Schedule:** 4:30 PM ET weekdays (after market closes at 4:00 PM)

**Flow:**
1. Refresh full `stock_data_cache.json` (re-fetch all ~900 tickers from yfinance)
2. Run cache heal to clean any NaN rows
3. Trigger a full scan
4. Scan results are cached → morning briefing cron uses fresh data

**Implementation:**
- New script: `scripts/refresh_cache.py` — standalone script that can be called by cron
- New LaunchAgent plist: `com.stockpicker.cache-refresh` (or add to existing cron)
- Batched fetching: 50 tickers at a time with 1s delay to avoid yfinance rate limits

## Files Changed

### New files:
- `src/cache_health.py` — cache validation and healing
- `src/thesis.py` — template-based thesis generator
- `scripts/refresh_cache.py` — standalone cache refresh script
- `frontend/src/components/ticker/PriceChart.tsx` — mini price chart
- `frontend/src/components/ticker/PositionSizer.tsx` — position size calculator
- `frontend/src/pages/Watchlist.tsx` — watchlist page
- `com.stockpicker.cache-refresh.plist` — LaunchAgent for scheduled refresh

### Modified files:
- `src/api.py` — new endpoints: `/chart/{ticker}`, `/watchlist`, `/watchlist/{ticker}`, `/thesis/{ticker}`, `/cache/health`
- `src/pipeline.py` — call `heal_cache()` before scan, add `thesis` field to scan results
- `src/momentum.py` — no changes (support/resistance already computed)
- `frontend/src/lib/api.ts` — new API client methods
- `frontend/src/lib/types.ts` — new types for watchlist, chart data
- `frontend/src/App.tsx` — add Watchlist route
- `frontend/src/components/layout/Sidebar.tsx` — add Watchlist nav item
- `frontend/src/components/scanner/ScannerRow.tsx` — add thesis one-liner + watchlist star
- `frontend/src/components/ticker/TickerModal.tsx` — add PriceChart + PositionSizer sections

## What's NOT in scope
- Risk/Reward ratio display (can add later)
- Portfolio management UI (next iteration)
- Smart alerts/notifications (next iteration)
- Data health dashboard in UI (auto-heal should make this unnecessary)
- SQLite migration
