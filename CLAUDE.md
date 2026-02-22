# CLAUDE.md — Stock Picker Project Context

## What This Is
A quantitative stock screening model that scans S&P 500 daily, scores stocks across multiple dimensions, and generates buy/sell signals. Built for personal use, not production trading.

## Architecture
- **Language:** Python 3.9
- **Web:** FastAPI backend + single-page HTML dashboard (`static/index.html`)

- **Storage:** JSON files in `data/` (no database yet — migrate to SQLite when data grows)
- **Hosting:** Runs on Mac mini (Apple Silicon), always-on via LaunchAgent (`com.stockpicker.server`)
- **Server:** uvicorn with `--reload --reload-dir src` (requires `watchfiles` package)
- **Auth:** API key via `X-API-Key` header (set `API_KEY` in `.env`); required for mutating endpoints

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

  api.py           — FastAPI endpoints (async /scan, /scan/status polling)
  indicators.py    — Shared RSI implementation (used by technicals, momentum, sell_signals, market_regime)
  insider.py       — Smart money analysis (analyst revisions + insider trading)
  sentiment.py     — Sentiment analysis (DISABLED: rate-limited + too naive, weight=0 in all strategies)

static/
  index.html       — Single-file dashboard (dark/light theme)

data/
  stock_data_cache.json   — Main cache (~19MB, .gitignored)
  scan_results.json       — Latest scan output
  signal_history.json     — Historical signal snapshots
  streak_tracker.json     — Consecutive days tracking

```

## Strategies & Weights
Defined in `src/strategies.py` (single source of truth). Sentiment disabled across all strategies.
- **Conservative:** fundamentals 42%, valuation 27%, risk 13%, sector-relative 10%, technicals 8%, growth 0%, sentiment 0%
- **Balanced:** fundamentals 28%, technicals 22%, valuation 18%, growth 13%, sector-relative 10%, risk 9%, sentiment 0%
- **Aggressive:** technicals 33%, growth 30%, fundamentals 15%, sector-relative 10%, valuation 8%, risk 4%, sentiment 0%

## Cron Jobs (automated)

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
1. **Sentiment Disabled:** Sentiment analysis removed from scoring (weight=0 in all strategies). Was rate-limited and too naive (word counting). Calls completely bypassed in pipeline.
2. **ADX-Aware Sell Signals:** Strong trends (ADX > 40) allow higher RSI thresholds before triggering sell signals. RSI sell scores discounted by 50% when price is >10% above MA50 in strong uptrend.
3. **Relaxed Entry Thresholds:** BUY signal now triggered with 2+ conditions (was 3+) OR entry_score >= 50.
4. **Sector-Relative Scoring (10% weight):** Within-sector rank now contributes to composite score, promoting sector diversification.
5. **Growth-Adjusted Valuation:** Gradual scaling: `multiplier = 1.0 + max(0, (growth_score - 50)) / 100 * 0.5`. Stocks with PEG < 1.5 receive +15 point valuation boost.
6. **Market Regime Detection:** Detects bull/bear/sideways markets based on SPY 200MA position and slope. Bull/bear adjustments to RSI thresholds, sell scores, and category weights.
7. **Scoring Inflation Fix:** All scoring modules (fundamentals, valuation, technicals, risk, growth) use fixed `TOTAL_COMPONENTS` denominator instead of `len(valid)`, so missing metrics contribute 0 instead of inflating scores.
8. **RSI Deduplication:** Single `_rsi()` in `src/indicators.py`, imported by technicals, momentum, sell_signals, market_regime.
9. **Rank Ordering Fix:** Rankings re-sorted after smart money bonus + earnings guard applied (was assigning ranks before score adjustments).
10. **Parallel Smart Money:** Analyst revision + insider trading fetch parallelized with ThreadPoolExecutor (5 workers). ~1.6s for 20 stocks (was ~8s sequential).
11. **Async /scan:** `/scan` returns immediately, runs in background thread. Poll `/scan/status` for progress. Use `?sync=true` for blocking mode. Duplicate scan prevention built in.
12. **API Authentication:** `X-API-Key` header required for mutating endpoints (`/scan`, `/optimize/apply`, `/rebalance/*`).
13. **Full Universe Coverage:** `all_scores` in scan results covers all 486 filtered stocks (was only top 20).

## Running
```bash
# Start API server (with auto-reload)
python3 -m uvicorn src.api:app --host 0.0.0.0 --port 8000 --reload --reload-dir src

# Server managed by LaunchAgent (auto-starts on boot)
launchctl stop com.stockpicker.server   # stop
launchctl start com.stockpicker.server  # start

# Run scan (async — returns immediately)
curl -H "X-API-Key: $API_KEY" http://localhost:8000/scan
curl http://localhost:8000/scan/status   # poll until finished
curl http://localhost:8000/scan/cached   # get results

# Run scan (sync — blocks until done)
curl -H "X-API-Key: $API_KEY" "http://localhost:8000/scan?sync=true"

# Run tests
python3 -m pytest test_sell_signals.py -v
```

## Rules
- Don't tune the model for individual stocks — rules must apply universally

- OpenBB was evaluated and rejected (no advantage over direct yfinance)
- All changes must be committed and pushed to GitHub (private repo)

## Roadmap (in order)
1. ~~Sell signals~~ ✅
2. ~~Consecutive days tracking~~ ✅
3. ~~Sentiment analysis~~ ✅ (built, then disabled — too naive/rate-limited)
4. ~~Sell signals trend context (ADX awareness)~~ ✅
5. ~~Relax entry signal thresholds~~ ✅
6. ~~Sector-relative scoring into composite (10% weight)~~ ✅
7. ~~Growth-adjusted valuation~~ ✅
8. ~~Market regime detection~~ ✅
9. ~~Scoring inflation fix~~ ✅
10. ~~Parallel smart money + async scan~~ ✅
11. ~~API authentication~~ ✅
12. Better sentiment replacement (proper NLP or expand smart money signals)

14. Walk-forward optimization (auto-tune weights from accuracy data)
15. SQLite migration (replace JSON files)
16. Sector concentration cap (max N per sector in top 20)
17. Portfolio tracking / watchlist (Robinhood, manual entry)
18. Correlation check (pairwise correlation on portfolio picks)
19. Log rotation

## Owner
Zhuoran Tang (@ztang2) — using Robinhood, planning $3000 balanced portfolio (ALL, ACGL, MCK, EQT, NEM)
