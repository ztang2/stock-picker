# Sell Signals Feature

## Overview

Added comprehensive sell/exit signal detection to the stock picker model. This feature identifies when to exit positions based on technical, fundamental, and momentum deterioration.

## Implementation

### 1. Core Module: `src/sell_signals.py`

**Main Function:** `compute_sell_signals(hist, fundamentals_score, prev_fundamentals_score, current_signal, prev_signal, resistance, entry_price, stop_loss_pct)`

**Sell Signal Triggers:**

1. **RSI Overbought** (>70 = warning, >80 = strong)
   - Detects when momentum has become excessive
   - Weight: 15-25 points

2. **Price Near Resistance**
   - Triggers when price is within 2% of resistance level
   - Weight: 12 points

3. **Signal Downgrade**
   - Detects when entry signal downgrades (e.g., STRONG_BUY → WAIT)
   - Weight: 10 points per downgrade level

4. **Fundamental Deterioration**
   - Tracks score drops >10 points (major drop >15 points)
   - Weight: 10-18 points

5. **Stop-Loss Threshold**
   - Configurable threshold (default -15%)
   - Weight: 30 points (highest priority)

6. **MACD Bearish Crossover**
   - Detects when MACD crosses below signal line
   - Weight: 15 points

7. **Moving Average Breakdown**
   - MA50 breakdown: 12 points
   - MA200 breakdown: 20 points

**Output Structure:**
```python
{
    "sell_signal": "STRONG_SELL" | "SELL" | "HOLD" | "N/A",
    "sell_score": 0-100,
    "urgency": "high" | "medium" | "low" | "none",
    "sell_reasons": ["list of trigger descriptions"],
    "rsi_overbought": bool,
    "near_resistance": bool,
    "signal_downgrade": bool,
    "fundamental_deterioration": bool,
    "stop_loss_triggered": bool,
    "macd_bearish": bool,
    "ma_breakdown": bool,
    "current_price": float,
    "rsi": float,
    "macd": {...},
    "ma_breakdown_info": {...},
    "stop_loss_info": {...}
}
```

**Signal Thresholds:**
- **STRONG_SELL**: sell_score ≥ 40 (urgency: high)
- **SELL**: sell_score ≥ 25 (urgency: medium)
- **HOLD**: sell_score ≥ 15 (urgency: low)
- **N/A**: sell_score < 15 (urgency: none)

### 2. Pipeline Integration: `src/pipeline.py`

**Changes:**
- Added `sell_signals` import
- Updated `analyze_single()` to accept `prev_data` parameter for comparison
- Loads previous scan results to enable signal/fundamental tracking
- Computes sell signals for each stock during analysis
- Includes sell signal data in output:
  - `sell_signal`: The signal rating
  - `sell_urgency`: Urgency level
  - `sell_reasons`: List of triggers

**Usage in Pipeline:**
```python
from src.pipeline import run_scan

results = run_scan(strategy="balanced")
for stock in results["top"]:
    print(f"{stock['ticker']}: {stock['sell_signal']} ({stock['sell_urgency']})")
    if stock['sell_signal'] != 'N/A':
        print(f"  Reasons: {', '.join(stock['sell_reasons'])}")
```

### 3. Alerts Integration: `src/alerts.py`

**New Alert Types:**
- **strong_sell**: Triggered when sell_signal = "STRONG_SELL" (severity: critical)
- **sell_warning**: Triggered when sell_signal = "SELL" (severity: warning)

Alerts include top 2 sell reasons for context.

### 4. Testing: `test_sell_signals.py`

Comprehensive test suite covering:
1. Basic functionality and structure
2. RSI overbought detection
3. Resistance proximity
4. Signal downgrade tracking
5. Fundamental deterioration
6. Stop-loss triggers
7. MACD bearish crossover
8. Moving average breakdown
9. Combined signals (multiple triggers)

**Run tests:**
```bash
python3 test_sell_signals.py
```

All tests passing ✓

## How to Use

### 1. Run a Stock Scan with Sell Signals

```python
from src.pipeline import run_scan

# Run standard scan
results = run_scan()

# Check sell signals in top picks
for stock in results["top"]:
    if stock["sell_signal"] in ["STRONG_SELL", "SELL"]:
        print(f"⚠️ {stock['ticker']}: {stock['sell_signal']}")
        print(f"   Urgency: {stock['sell_urgency']}")
        print(f"   Reasons: {stock['sell_reasons']}")
```

### 2. Check Sell Signals for Specific Stock

```python
from src.pipeline import get_stock_detail

detail = get_stock_detail("AAPL")
sell_signals = detail["sell_signals"]

print(f"Sell Signal: {sell_signals['sell_signal']}")
print(f"Score: {sell_signals['sell_score']}")
print(f"Reasons: {sell_signals['sell_reasons']}")
```

### 3. Monitor Portfolio with Custom Entry Prices

```python
import pandas as pd
from src.sell_signals import compute_sell_signals

# Load your stock's price history
hist = ...  # pd.DataFrame with OHLCV

# Check against your entry price
signals = compute_sell_signals(
    hist=hist,
    entry_price=150.00,  # Your entry price
    stop_loss_pct=-12.0,  # Custom stop-loss (default -15%)
)

if signals["stop_loss_triggered"]:
    print(f"🚨 Stop-loss triggered! Loss: {signals['stop_loss_info']['loss_pct']:.1f}%")
```

### 4. Use in Morning Briefing

The alerts system automatically includes sell signal warnings:

```python
from src.alerts import check_alerts

alerts = check_alerts()

# Filter for sell signals
sell_alerts = [a for a in alerts if a['type'] in ['strong_sell', 'sell_warning']]

for alert in sell_alerts:
    print(f"{alert['severity'].upper()}: {alert['message']}")
```

## Example Output

```
Stock: MSFT
  Entry Signal: STRONG_BUY
  Sell Signal: HOLD
  Urgency: low
  Sell Reasons: RSI overbought (72.3)
  
Stock: TSLA
  Entry Signal: BUY
  Sell Signal: STRONG_SELL
  Urgency: high
  Sell Reasons: RSI extremely overbought (84.2), Signal downgraded from STRONG_BUY to WAIT, Price near resistance ($245.80, +1.2%)
```

## Integration Notes

- **Backward Compatible**: Existing code continues to work; sell signals are additional data
- **Optional Parameters**: Most parameters in `compute_sell_signals()` are optional for flexibility
- **Comparison Logic**: Requires previous scan data for signal downgrades and fundamental deterioration tracking
- **Screening Mode**: When entry_price is None (screening mode), stop-loss check is informational only

## Next Steps / Future Enhancements

1. **Portfolio Tracking**: Create a portfolio file to track actual entry prices for personalized stop-loss alerts
2. **Position Sizing**: Integrate sell signals with position sizing recommendations
3. **Alert Thresholds**: Make sell signal thresholds configurable per user risk tolerance
4. **Sell Signal History**: Track historical sell signals to measure accuracy
5. **Email/SMS Alerts**: Add notification channels for STRONG_SELL signals

## Testing

Run the test suite to verify functionality:

```bash
cd ~/clawd/stock-picker
python3 test_sell_signals.py
```

Expected output: All 9 tests pass ✓

## Files Modified

- `src/sell_signals.py` (new) - Core sell signal logic
- `src/pipeline.py` - Integration with analysis pipeline
- `src/alerts.py` - Sell signal alerts for briefing
- `test_sell_signals.py` (new) - Comprehensive test suite

## Commit

```
git log -1 --oneline
bf31d1a Add sell signals feature
```
