# How to Run ML Health Audit

## Quick Start

### Run audit and view report:
```bash
cd ~/clawd/stock-picker
python3 -m src.ml_audit
```

### Or in Python:
```python
from src.ml_audit import audit_ml_health, format_audit_report

report = audit_ml_health()
print(format_audit_report(report))
```

## What the Audit Checks

1. **ML Model Exists** - Verifies `data/ml/model.pkl` file exists
2. **Daily Snapshots Being Saved** - Checks `data/daily_snapshots/` directory
3. **Recent Snapshot** - Warns if last snapshot > 7 days old
4. **ML Scores in Scan Results** - Verifies ML predictions are not None
5. **ML Score Diversity** - Detects if all predictions are identical
6. **ML Weight > 0** - Checks if ML is active in scoring
7. **ML Affecting Rankings** - Compares base_score vs composite_score
8. **ML Accuracy (7 days)** - Average accuracy over last week
9. **ML Accuracy (30 days)** - Average accuracy over last month
10. **Validation Log Exists** - Checks if ML validation is running

## Interpreting Results

### Verdict Levels:
- ✅ **HEALTHY**: All systems operational
- ⚠️ **WARNING**: Issues detected but not critical
- ❌ **CRITICAL**: Hard failures requiring immediate attention

### Status Icons:
- ✅ **PASS**: Check passed
- ⚠️ **WARNING**: Potential issue
- ❌ **FAIL**: Critical failure
- ℹ️ **INFO**: Informational only

## Example Output

```
============================================================
ML HEALTH AUDIT REPORT
============================================================
Audit Date: 2026-02-20T00:57:10
Verdict: HEALTHY

CHECKS:
  ✅ PASS ML model exists
     → Model file: data/ml/model.pkl
  ✅ PASS Recent snapshots
     → 15 snapshots, last: 2026-02-20 (0 days ago)
  ✅ PASS ML scores in scan results
     → 20 stocks have ML scores, 18 unique values
  ✅ PASS ML affecting rankings
     → ML weight=0.1, avg score change=3.45
  ✅ PASS ML accuracy (7 days)
     → 54.2% (7 days)
  ✅ PASS ML accuracy (30 days)
     → 52.1% (25 days)

============================================================
```

## Automation

### Add to cron (weekly):
```bash
# Every Monday at 9 AM
0 9 * * 1 cd ~/clawd/stock-picker && python3 -m src.ml_audit >> logs/ml_audit.log 2>&1
```

### Check audit history:
```python
import json
from pathlib import Path

audit_log = Path('data/ml_audit_log.json')
if audit_log.exists():
    audits = json.loads(audit_log.read_text())
    for audit in audits[-5:]:  # Last 5 audits
        print(f"{audit['audit_date']}: {audit['verdict']}")
```

## Troubleshooting

### ML scores are None
- **Cause**: Model file missing or prediction failed
- **Fix**: Run `python3 -c "from src.ml_model import train_model; train_model()"`

### ML weight is 0
- **Cause**: Not enough daily snapshots (need 10+)
- **Fix**: Wait for more daily scans, or check snapshot directory

### ML accuracy < 50%
- **Cause**: Model underperforming
- **Fix**: Retrain model with more data or investigate feature issues
- **Auto-fix**: System will auto-disable ML after 10 consecutive poor days

### Snapshots not being saved
- **Cause**: Daily scan not running
- **Fix**: Check cron jobs, verify scan is completing successfully

## Integration with Validation

The audit works alongside daily validation:

```python
from src.validation import validate_predictions, get_validation_summary

# Daily validation (run after market close)
report = validate_predictions()

# Weekly summary (includes ML accuracy)
summary = get_validation_summary(days=7)
print(f"ML accuracy: {summary['ml_avg_accuracy']}%")
```

## Data Files

All audit-related files stored in `data/`:
- `ml_audit_log.json` - Audit history (52 weeks)
- `ml_validation_log.json` - Daily ML prediction validation
- `ml_weight_state.json` - Auto-disable state (if ML underperforming)

## Next Steps

1. Run audit weekly to monitor ML health
2. Review validation logs daily to track accuracy
3. Retrain model monthly or when accuracy drops
4. Adjust ML weight thresholds if needed based on performance
