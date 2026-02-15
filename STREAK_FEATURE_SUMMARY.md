# Streak Tracking Feature - Implementation Summary

## ✅ Task Completed

Successfully added a "consecutive days in top 20" tracking feature to the stock picker.

## 📋 Requirements Met

### 1. ✅ Compare current top 20 against previous snapshots
- Implemented in `src/streak_tracker.py`
- Uses `signal_history.json` to reconstruct historical top 20 lists by date
- Compares current top 20 with historical data to calculate streaks

### 2. ✅ Persistent storage in `data/streak_tracker.json`
```json
{
  "AAPL": {
    "consecutive_days": 12,
    "first_seen": "2025-02-03",
    "last_seen": "2025-02-15"
  }
}
```

### 3. ✅ Add `consecutive_days` to scan results
- Added to each stock in `data/scan_results.json`
- Automatically populated during scan pipeline
- Also includes `first_seen` date

### 4. ✅ Updated morning briefing with indicators
- 📅 Established picks (7+ days)
- 🔥 Hot streaks (3-6 days)
- 🆕 New entries (1-2 days)
- Groups stocks by streak category in briefing
- Shows signal type with emoji: 🟢 STRONG_BUY | 🔵 BUY | ⚪ HOLD

### 5. ✅ Integrated into pipeline
- Streak update runs after scan completes (in `src/pipeline.py`)
- Happens automatically after earnings guard and before results are saved
- No manual intervention needed

### 6. ✅ Reset streak when ticker drops out
- Streak set to 0 when ticker not in current top 20
- Old dropped tickers cleaned up after 1 day
- New streaks start from 1 when ticker re-enters

## 📁 Files Created/Modified

### New Files
1. **`src/streak_tracker.py`** (235 lines)
   - Core tracking logic
   - Functions: `update_streaks()`, `get_streak()`, `add_streaks_to_results()`

2. **`test_streaks.py`** (85 lines)
   - Comprehensive test script
   - Validates all functionality

3. **`STREAK_TRACKING.md`**
   - Complete documentation

4. **`data/streak_tracker.json`**
   - Persistent storage (auto-generated)

### Modified Files
1. **`src/pipeline.py`**
   - Added import: `from .streak_tracker import update_streaks, add_streaks_to_results`
   - Added streak update after earnings guard
   - Added streak data to results

2. **`src/alerts.py`**
   - Added import: `from .streak_tracker import get_all_streaks`
   - Added `generate_morning_briefing()` function (90+ lines)
   - Formats stocks by streak category with emoji indicators

3. **`src/api.py`**
   - Added imports for streak functions and briefing
   - Added `/streaks` endpoint
   - Added `/streaks/{ticker}` endpoint
   - Added `/briefing` endpoint

## 🧪 Testing

### Test Results
```
✅ Scan complete. 20 stocks ranked.
✅ 20 tickers have streak data
✅ All top stocks have consecutive_days field
✅ Briefing generated
✅ streak_tracker.json exists (2105 bytes)
✅ ALL TESTS PASSED!
```

### How to Test
```bash
cd ~/clawd/stock-picker
python3 test_streaks.py
```

## 🔄 Integration with Existing Flow

### Daily Snapshot (4pm ET cron)
The existing cron job already saves to `signal_history.json`. The streak tracker automatically:
1. Reads historical snapshots from this file
2. Reconstructs top 20 lists by date
3. Calculates consecutive days for each ticker
4. Updates `streak_tracker.json`

### Pipeline Flow
```
run_scan() 
  → earnings_guard 
  → update_streaks()           ← NEW
  → add_streaks_to_results()   ← NEW
  → save results
```

## 📊 API Endpoints

### Get All Streaks
```bash
curl http://localhost:8000/streaks
```

### Get Specific Ticker Streak
```bash
curl http://localhost:8000/streaks/AAPL
```

### Morning Briefing
```bash
curl http://localhost:8000/briefing?top_n=20
```

## 💡 Key Features

1. **Weekend-Aware**: Handles market closure gaps (up to 3 days)
2. **Historical Analysis**: Reconstructs streaks from signal_history.json
3. **Auto-Cleanup**: Removes old dropped tickers after 1 day
4. **Zero Config**: Works automatically with existing cron setup
5. **Persistent**: Survives restarts via JSON storage
6. **Visual**: Color-coded briefing with emoji indicators

## 📝 Usage Examples

### In Code
```python
from src.streak_tracker import get_streak, update_streaks, get_all_streaks
from src.alerts import generate_morning_briefing

# Get streak for specific ticker
days, first_seen, last_seen = get_streak("AAPL")
print(f"AAPL has been in top 20 for {days} consecutive days")

# Get all streaks
streaks = get_all_streaks()
for ticker, data in streaks.items():
    print(f"{ticker}: {data['consecutive_days']} days")

# Generate morning briefing
briefing = generate_morning_briefing(top_n=20)
print(briefing)
```

### Via API
```bash
# Get briefing
curl http://localhost:8000/briefing | jq -r '.briefing'

# Get AAPL streak
curl http://localhost:8000/streaks/AAPL | jq
```

## 🎯 Edge Cases Handled

1. **First run**: All stocks start with streak = 1
2. **Market closure**: Weekend gaps (2-3 days) don't break streaks
3. **Ticker drops out**: Streak reset to 0
4. **Ticker re-enters**: New streak starts from 1
5. **No history**: Gracefully handles empty signal_history.json
6. **Corrupted data**: Falls back to empty dict on JSON errors

## 🚀 Next Steps (Optional Enhancements)

Potential future improvements:
- Add streak trend charts to web UI
- Email alerts for stocks reaching 7/14/30 day milestones
- Compare streak performance vs non-streak picks
- Track "longest streak" historical record per ticker
- Add streak-based strategy filter (only pick stocks with 3+ day streaks)

## 📦 Commits

```
8a325f8 Add streak tracking documentation
190e459 Add consecutive days in top 20 tracking feature
```

## ✨ Summary

The consecutive days tracking feature is fully implemented, tested, and integrated into the stock picker pipeline. It automatically tracks how long each ticker has been in the top 20, displays this information in scan results, and provides a visually appealing morning briefing with streak indicators. The feature requires no manual intervention and works seamlessly with the existing daily snapshot workflow.
