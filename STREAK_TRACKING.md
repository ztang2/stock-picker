# Consecutive Days Tracking Feature

## Overview
Tracks how many consecutive days each ticker has remained in the top 20 stock picks.

## Files Added/Modified

### New Files
- **`src/streak_tracker.py`** - Core streak tracking module
- **`data/streak_tracker.json`** - Persistent storage for streak data
- **`test_streaks.py`** - Test script to validate functionality

### Modified Files
- **`src/pipeline.py`** - Integrated streak tracking after scan completion
- **`src/alerts.py`** - Added morning briefing with streak indicators
- **`src/api.py`** - Added API endpoints for streaks and briefing

## How It Works

### 1. Automatic Tracking
After each scan completes, the pipeline automatically:
- Extracts top 20 tickers from scan results
- Compares against historical snapshots in `signal_history.json`
- Calculates consecutive days for each ticker
- Updates `data/streak_tracker.json`

### 2. Data Format
```json
{
  "AAPL": {
    "consecutive_days": 12,
    "first_seen": "2026-02-03",
    "last_seen": "2026-02-15"
  }
}
```

### 3. Streak Reset Logic
- When a ticker **drops out** of top 20 → streak reset to 0
- When a ticker **re-enters** → new streak starts from 1
- Weekend gaps (2-3 days) are accounted for

### 4. Integration Points

#### Pipeline (automatic)
```python
# In src/pipeline.py (line ~445)
top20_tickers = [stock["ticker"] for stock in ranked[:20]]
update_streaks(top20_tickers, current_date)
ranked = add_streaks_to_results(ranked)
```

#### Scan Results
Each stock in `data/scan_results.json` now includes:
```json
{
  "ticker": "AAPL",
  "consecutive_days": 12,
  "first_seen": "2026-02-03",
  ...
}
```

### 5. Morning Briefing
Generate with streak indicators:
```python
from src.alerts import generate_morning_briefing
briefing = generate_morning_briefing()
print(briefing)
```

Output example:
```
📅 ESTABLISHED PICKS (7+ days in top 20)
  #1 🟢 AAPL   Apple Inc.              Score:  92.50 | 12 days

🔥 HOT STREAKS (3-6 days)
  #3 🔵 MSFT   Microsoft Corporation   Score:  89.30 | 5 days

🆕 NEW ENTRIES (1-2 days)
  #5 🔵 GOOGL  Alphabet Inc.           Score:  86.10 | 1 days
```

Indicators:
- 📅 **Established** - 7+ consecutive days
- 🔥 **Hot Streak** - 3-6 days
- 🆕 **New Entry** - 1-2 days
- 🟢 STRONG_BUY | 🔵 BUY | ⚪ HOLD/WAIT

## API Endpoints

### Get All Streaks
```bash
GET /streaks
```
Returns all current streak data.

### Get Ticker Streak
```bash
GET /streaks/{ticker}
```
Returns streak info for specific ticker.

### Morning Briefing
```bash
GET /briefing?top_n=20
```
Returns formatted morning briefing with streak indicators.

## Testing
Run the test script:
```bash
cd ~/clawd/stock-picker
python3 test_streaks.py
```

This will:
1. Run a scan
2. Update streaks
3. Verify consecutive_days field in results
4. Generate and display morning briefing
5. Validate streak_tracker.json file

## Cron Integration
The daily 4pm ET snapshot already saves to `signal_history.json`. The streak tracker automatically uses this historical data to calculate streaks when the pipeline runs.

No additional cron jobs needed - streak tracking is integrated into the normal scan flow.

## Notes
- Streaks are based on historical snapshots in `signal_history.json`
- Weekend/market closure gaps (up to 3 days) are handled gracefully
- Old dropped tickers are cleaned up after 1 day to keep file size manageable
- Streaks persist across restarts via `streak_tracker.json`
