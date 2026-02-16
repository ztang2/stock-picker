# CLAUDE.md — Stock Picker Project Context

## What This Is
A quantitative stock screening model that scans S&P 500 daily, scores stocks across multiple dimensions, and generates buy/sell signals. Built for personal use, not production trading.

## Architecture
- **Language:** Python 3
- **Web:** FastAPI backend + single-page HTML dashboard (`static/index.html`)
- **Data sources:** yfinance (primary, free, unlimited) + FMP (supplementary, 250 calls/day free tier)
- **Storage:** JSON files in `data/` (no database yet — migrate to SQLite when data grows)
- **Hosting:** Runs on Mac mini (Apple Silicon), always-on

## Key Files
```
src/
  pipeline.py      — Main scan orchestrator (fetch → analyze → score → rank)
  fundamentals.py  — ROE, margins, FCF, debt ratios
  valuation.py     — P/E, P/S, PEG scoring
  technicals.py    — RSI, MACD, moving averages
  risk.py          — Beta, Sharpe, max drawdown, volatility
  growth.py        — Revenue/earnings growth, margin trends
  momentum.py      — Entry signals (STRONG_BUY/BUY/HOLD/WAIT)
  sell_signals.py  — Exit signals (STRONG_SELL/SELL/HOLD/N/A)
  scorer.py        — Weighted composite scoring with percentile ranking
  strategies.py    — Three strategies: conservative, balanced, aggressive
  streak_tracker.py — Consecutive days in top 20 tracking
  earnings_guard.py — Earnings date proximity warnings
  sector.py        — Sector-relative scoring
  alerts.py        — Morning briefing generation
  accuracy.py      — Prediction accuracy tracking
  fmp.py           — FMP API data fetcher
  api.py           — FastAPI endpoints
  sentiment.py     — Sentiment analysis (exists, not yet wired in)

static/
  index.html       — Single-file dashboard (dark/light theme)

data/
  stock_data_cache.json   — Main cache (~19MB, .gitignored)
  scan_results.json       — Latest scan output
  signal_history.json     — Historical signal snapshots
  streak_tracker.json     — Consecutive days tracking
  fmp_cache/              — Per-ticker FMP data (.gitignored)
```

## Strategies & Weights
- **Conservative:** fundamentals 45%, valuation 30%, risk 15%, technicals 10%, growth 0%
- **Balanced:** fundamentals 30%, technicals 25%, valuation 20%, growth 15%, risk 10%
- **Aggressive:** technicals 35%, growth 35%, fundamentals 15%, valuation 10%, risk 5%

## Cron Jobs (automated)
- **6:00 AM PT daily** — FMP cache fill
- **Morning** — Briefing to Discord #stock-picker
- **4:00 PM ET weekdays** — Accuracy snapshot + streak update

## Sell Signal Triggers
- RSI overbought (>70 warning, >80 strong sell)
- Price near resistance (within 2%)
- Signal downgrade (e.g., BUY → WAIT)
- Fundamental deterioration (score drop >15 points)
- Weak fundamentals floor (score <40)
- Valuation score = 0 (negative earnings)
- Risk score = 0 (extreme volatility)
- Stop-loss threshold (default -15%)
- MACD bearish crossover
- MA50/MA200 breakdown

## Running
```bash
# Start API server
python3 -m uvicorn src.api:app --host 0.0.0.0 --port 8080

# Run scan from CLI
python3 -c "from src.pipeline import run_scan; run_scan()"

# Run tests
python3 -m pytest test_sell_signals.py -v
```

## Rules
- Don't tune the model for individual stocks — rules must apply universally
- yfinance is primary data source; FMP supplements fundamentals
- OpenBB was evaluated and rejected (no advantage over direct yfinance)
- All changes must be committed and pushed to GitHub (private repo)

## Roadmap (in order)
1. ~~Sell signals~~ ✅
2. ~~Consecutive days tracking~~ ✅
3. ~~Wire sentiment into scoring (5% weight)~~ ✅
4. ~~Sell signals trend context (ADX awareness)~~ ✅
5. ~~Relax entry signal thresholds~~ ✅
6. ~~Sector-relative scoring into composite (10% weight)~~ ✅
7. ~~Growth-adjusted valuation~~ ✅
8. Cross-reference yfinance + FMP (after FMP fully cached)
9. Market regime detection (bear/bull — adjust thresholds based on SPY 200MA)
10. Walk-forward optimization (auto-tune weights from accuracy data)
11. Portfolio tracking / watchlist (Robinhood, manual entry)
12. Correlation check (pairwise correlation on portfolio picks)
13. Peer comparison (sub-sector ranking)
14. Streak consistency bonus (consecutive days → composite boost)

## Owner
Zhuoran Tang (@ztang2) — using Robinhood, planning $3000 balanced portfolio (ALL, ACGL, MCK, EQT, NEM)
