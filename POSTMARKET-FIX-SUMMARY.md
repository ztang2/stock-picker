# Post-Market Check Fix — Summary

**Date**: 2026-02-23  
**Task**: Fix Robin's unreliable stock-picker post-market check  
**Status**: ✅ COMPLETE

---

## Problem

Robin was running a massive inline Python script in the cron prompt that:
1. Broke when data structures changed (e.g., `top` → `stocks` key)
2. Panicked with "SEVERE DATA LOSS" when data was fine, just keyed differently
3. Had no error isolation — one failure killed the whole check
4. Was unmaintainable and fragile

---

## Solution

### Part 1: Created `/portfolio/check` API Endpoint ✅

**Location**: `~/clawd/stock-picker/src/api.py` (lines 566-816)

**Endpoint**: `GET http://localhost:8000/portfolio/check`

**Features**:
- ✅ Consolidated all post-market logic in one place
- ✅ Defensive key access: `d.get('top', d.get('stocks', []))`
- ✅ Each section wrapped in try/except (no cascading failures)
- ✅ Handles key name inconsistencies (`composite` vs `composite_score`)
- ✅ Loads holdings from `~/clawd/memory/trades.md`
- ✅ Enriches with current prices via yfinance
- ✅ Returns comprehensive JSON response

**Response Structure**:
```json
{
  "validation": {
    "report": "...",
    "raw": {...}
  },
  "holdings": [
    {
      "ticker": "EQT",
      "entry_price": 57.12,
      "current_price": 59.03,
      "today_change_pct": 0,
      "total_return_pct": 3.34,
      "score": 83.51,
      "signal": "HOLD"
    }
  ],
  "rebalance": {
    "report": "...",
    "suggestions": [...]
  },
  "snapshots": {
    "report": "...",
    "status": "ok|issues_found",
    "details": {...}
  },
  "portfolio_summary": {
    "avg_return": 1.34,
    "best": "EQT +3.34%",
    "worst": "ACGL -0.66%",
    "holdings_count": 2
  },
  "sanity_warnings": [],
  "timestamp": "2026-02-23T17:44:33.722056"
}
```

---

### Part 2: Updated Cron Prompt ✅

**Location**: `~/clawd/stock-picker/cron-prompt-postmarket.txt`

**Key Changes**:
- ✅ Just calls `curl -s 'http://localhost:8000/portfolio/check'`
- ✅ Formats JSON response into Discord message
- ✅ Includes defensive instructions:
  - "If any section returns an error, note it but don't panic"
  - "Verify claims before alarming — if snapshots look empty, ls the directory first"
  - "Data structure changes ≠ data loss"

**Usage**: Copy this prompt text to Robin's post-market cron job.

---

### Part 3: Hardened Data Key Access Everywhere ✅

**Pattern**: `d.get('top', d.get('stocks', []))`

**Files Updated**:
- ✅ `src/api.py` (9 occurrences)
- ✅ `src/validation.py` (2 occurrences)
- ✅ `src/alerts.py` (3 occurrences)
- ✅ `src/ml_model.py` (4 occurrences)
- ✅ `src/ml_audit.py` (1 occurrence)
- ✅ `src/accuracy.py` (1 occurrence)
- ✅ `src/model_report.py` (1 occurrence)
- ✅ `src/snapshot_verify.py` (2 occurrences)
- ✅ `src/pipeline.py` (1 occurrence)

**Total**: 24 defensive key accesses added across 9 files.

---

## Testing

### Test Command:
```bash
curl -s 'http://localhost:8000/portfolio/check' | python3 -m json.tool
```

### Test Results:
```
✅ VALIDATION: 20 stocks validated
✅ HOLDINGS: 2 positions found (EQT +3.34%, ACGL -0.66%)
✅ REBALANCE: No swaps needed (within tolerance band)
✅ SNAPSHOTS: 100% complete, 3/3 days captured
✅ PORTFOLIO SUMMARY: Avg +1.34%
```

**Status**: All sections working correctly. Endpoint ready for production.

---

## Git Commit

```bash
cd ~/clawd/stock-picker
git add -A
git commit -m "feat: add /portfolio/check endpoint, harden data key access"
```

**Commit Hash**: `faf2c18`

**Files Changed**: 15 files, 5435 insertions, 45 deletions

---

## Next Steps for Deployment

1. **Update Robin's cron job**:
   - Replace the inline Python script with the prompt from `cron-prompt-postmarket.txt`
   - Set schedule: Daily after market close (4:30 PM EST)

2. **Monitor first run**:
   - Check that Robin formats the response correctly
   - Verify Discord message is readable
   - Confirm no false alarms

3. **Verify error handling**:
   - If a section fails, check that Robin notes it calmly
   - Confirm Robin doesn't panic over structure changes

---

## Key Improvements

| Before | After |
|--------|-------|
| Inline Python in cron prompt (500+ lines) | Simple curl call to API endpoint |
| Breaks on key name changes | Defensive fallbacks everywhere |
| One error kills entire check | Each section isolated |
| Panics on structure changes | Distinguishes structure vs data loss |
| Unmaintainable mess | Clean, testable API endpoint |

---

## Technical Details

### Defensive Key Access Pattern:
```python
# OLD (fragile):
top = data["top"]  # KeyError if key changes

# NEW (defensive):
top = data.get("top", data.get("stocks", []))
```

### Error Isolation Pattern:
```python
try:
    result = risky_operation()
    response["section"] = result
except Exception as e:
    logger.error("Section failed", exc_info=True)
    response["section"] = {"error": str(e)}
```

### Key Name Normalization:
```python
# Handle both naming conventions
score = data.get("composite_score", data.get("composite", 0))
signal = data.get("entry_signal", data.get("signal", "N/A"))
```

---

## Lessons Learned

1. **Don't put business logic in cron prompts** — Use API endpoints
2. **Defensive coding prevents panic** — Fallbacks > hard failures
3. **Error isolation is critical** — One failure shouldn't cascade
4. **Structure changes ≠ catastrophe** — Key names can evolve
5. **Verify before alarming** — Check if data actually missing

---

**End of Summary**
