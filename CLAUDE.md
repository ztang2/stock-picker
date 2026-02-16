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
  sentiment.py     — Sentiment analysis (wired into composite scoring, 3-7% weight)

static/
  index.html       — Single-file dashboard (dark/light theme)

data/
  stock_data_cache.json   — Main cache (~19MB, .gitignored)
  scan_results.json       — Latest scan output
  signal_history.json     — Historical signal snapshots
  streak_tracker.json     — Consecutive days tracking
  fmp_cache/              — Per-ticker FMP data (.gitignored)
```

## Strategies & Weights (updated with sentiment + sector-relative)
- **Conservative:** fundamentals 40%, valuation 26%, risk 13%, sector-relative 10%, technicals 8%, sentiment 3%, growth 0%
- **Balanced:** fundamentals 26%, technicals 22%, valuation 17%, growth 12%, sector-relative 10%, risk 8%, sentiment 5%
- **Aggressive:** technicals 31%, growth 27%, fundamentals 13%, sector-relative 10%, valuation 8%, sentiment 7%, risk 4%

## Cron Jobs (automated)
- **6:00 AM PT daily** — FMP cache fill
- **Morning** — Briefing to Discord #stock-picker
- **4:00 PM ET weekdays** — Accuracy snapshot + streak update

## Sell Signal Triggers
- RSI overbought (>70 warning, >80 strong sell) — **ADX-aware:** thresholds raised to 80/85 when ADX > 40 (strong trend)
- Price near resistance (within 2%)
- Signal downgrade (e.g., BUY → WAIT)
- Fundamental deterioration (score drop >15 points)
- Weak fundamentals floor (score <40)
- Valuation score = 0 (negative earnings)
- Risk score = 0 (extreme volatility)
- Stop-loss threshold (default -15%)
- MACD bearish crossover
- MA50/MA200 breakdown

## Recent Improvements (Feb 2026)
1. **Sentiment Analysis (5% weight):** News headline sentiment analysis now integrated into composite scoring (3% conservative, 5% balanced, 7% aggressive)
2. **ADX-Aware Sell Signals:** Strong trends (ADX > 40) allow higher RSI thresholds before triggering sell signals. RSI sell scores discounted by 50% when price is >10% above MA50 in strong uptrend.
3. **Relaxed Entry Thresholds:** BUY signal now triggered with 2+ conditions (was 3+) OR entry_score >= 50. Top-20 stocks with score >75 auto-upgraded to BUY unless red flags present.
4. **Sector-Relative Scoring (10% weight):** Within-sector rank now contributes to composite score, promoting sector diversification.
5. **Growth-Adjusted Valuation:** High-growth stocks (growth_score > 80) get valuation penalty dampened by 1.3x. Stocks with PEG < 1.5 receive +15 point valuation boost.

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
