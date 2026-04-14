# ML Accuracy Audit
*Generated: 2026-04-12*

## Summary

The walk-forward validation methodology is **sound** but the results are **not yet statistically reliable** due to data constraints. The 89.3% STRONG_BUY accuracy is real but has important caveats documented below.

---

## What the Metrics Actually Mean

| Metric | Value | Notes |
|---|---|---|
| Training data | 8,860 samples | 49 snapshots × ~181 tickers avg |
| Time window | 52 calendar days | Feb 17 – Apr 10, 2026 |
| Walk-forward test set | 4,900 samples (55.3%) | Genuinely held-out, not in-sample |
| Overall accuracy | 67.1% | Beats random (50%) meaningfully |
| STRONG_BUY accuracy | 89.3% | n=589 — see caveats |
| Consensus BUY accuracy | 79.3% | n=1,157 |
| Regression correlation | 0.55 | Moderate predictive signal |

---

## ✅ What's Validated

**Walk-forward is correct.** The code uses time-ordered splits — train on past dates, predict on future date, never leaking future data backward. The 4,900 test samples are genuinely out-of-sample. This is the right methodology.

**The model does have signal.** 67.1% overall accuracy vs 50% random baseline. Regression correlation of 0.55 means the return predictions have real but noisy signal.

---

## ⚠️ Caveats and Limitations

### 1. Effective training window is smaller than it looks
- 49 total snapshots, but `_compute_forward_return` correctly rejects samples where < 20 trading days of price data exist
- 22 of 49 snapshots fall within the last 28 calendar days and are automatically excluded (no complete forward return yet)
- **Effective training snapshots: ~27** (Feb 17 – Mar 15, 2026)
- This is expected and correct behavior — no data leakage

### 2. Single market regime dominates the data
- 52 calendar days total (Feb–Apr 2026)
- Regime breakdown: Bear 22, Bull 18, Sideways 7, Unknown 2
- The model has never been tested on a sustained multi-year bull or bear run
- A 3-month window during volatile April 2025–2026 tariff period is not representative

### 3. STRONG_BUY 89.3% — selection bias
STRONG_BUY requires BOTH `xgb_prob > 0.65 AND lgb_return > 0.02`. This double-filter selects only the highest-confidence cases — the model is essentially saying "I'm very sure" on 589 samples. High accuracy on cherry-picked confident predictions is expected. The real question is whether that 89.3% holds out-of-sample on future data.

### 4. 52 days of data produces ~49 distinct "test dates" in walk-forward
With `months_history = min(12, n_dates - 2)`, each test "date" is one of the 49 snapshot days. That means the model is evaluated across ~25 unique test dates (the second half). 589 STRONG_BUY signals across ~25 test dates = ~24 signals per day. With 181 tickers per snapshot, that's ~13% hit rate. Statistically, 589 is okay but not large.

### 5. Forward return window vs data recency
The `_compute_forward_return` function correctly returns `None` when < 20 trading days of price data exist, so recent snapshots are excluded. No data leakage here — verified in audit.

### 6. Feature leakage risk
The model features include `composite_score` — which is computed by the pipeline. If pipeline weights change, the composite_score distribution shifts and the model's learned mapping becomes stale. The model was retrained 2026-04-04 so it's reasonably current.

---

## Recommendations

### Immediate (low effort)
1. **Add training date cutoff**: Exclude snapshots where `date > today - 25 trading days` to avoid incomplete forward returns contaminating training data. Estimated impact: removes ~5 snapshots from training, minor.

2. **Log n= everywhere**: When reporting accuracy metrics in cron reports, always include sample count so you know when numbers are based on thin data.

### Medium term
3. **Accumulate 6+ months of snapshots** before trusting ML metrics. At 49 snapshots you have a start; at ~130 snapshots (6 months) the metrics will be more reliable.

4. **Add naive baseline comparison**: Track "what if you just bought all BUY signals without ML filtering" to compare against ML-filtered results. Currently the 79.3% BUY accuracy isn't contextualized against a no-ML baseline.

5. **Separate accuracy metrics by month of data**: If accuracy in month 1 is 72% and month 2 is 85%, that's a training-data-size artifact, not a real improvement.

---

## Bottom Line

**The ML methodology is correct.** Walk-forward validation prevents in-sample overfitting. The 89.3% STRONG_BUY number is real walk-forward accuracy, not a training set artifact.

**The concern is generalization**, not methodology: 52 days of data spanning one volatile market period is insufficient to claim these numbers hold across different market conditions. As you accumulate more snapshot data over the coming months, rerun `/train` and check if accuracy remains stable. If it holds at 80%+ STRONG_BUY through a full market cycle (6-12 months), that's genuine alpha.

**Current status**: Trust the model's signals for ranking/filtering, but treat the specific 89.3% figure as "promising early result, not yet proven durable."
