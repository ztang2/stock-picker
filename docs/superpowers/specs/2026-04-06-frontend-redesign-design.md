# Stock Picker Frontend Redesign — Design Spec

## Goal

Enhance the stock-picker web app for daily-driver polish. Rebuild the frontend in React with a new Home dashboard, enhanced scanner, redesigned ticker modal, and overhauled portfolio page. Backend (FastAPI) remains unchanged.

## Motivation

The current frontend is 1,600 lines of vanilla HTML/CSS/JS. Pain points:
- Scanner table is visually overwhelming — hard to spot what matters across 903 stocks
- Ticker detail modal is crowded and unstyled
- Portfolio page lacks at-a-glance P&L, risk visibility, and actionable insights
- No hover interactions, animations, or modern design polish

## Tech Stack

| Layer | Choice | Rationale |
|-------|--------|-----------|
| Framework | React + TypeScript | Already in user's stack (React Native/Expo for LiftArc) |
| Build | Vite | Fast, minimal config, no Webpack complexity |
| Styling | Tailwind CSS | Utility-first, rapid iteration, dark mode built-in |
| Animation | Framer Motion | Polished hover/transition/mount animations |
| Charts | Recharts | Radar charts, sparklines, portfolio visualizations |
| HTTP | fetch (native) | No axios needed — FastAPI returns JSON, simple GET calls |

The React app replaces `static/index.html`. Vite builds to `static/dist/`, and FastAPI serves `static/dist/` as a static mount. A few new backend endpoints are needed for sparkline data, diversification scoring, and correlation — detailed in each section below. No changes to existing endpoints or data structures.

## Architecture

```
frontend/
├── src/
│   ├── App.tsx                    # Router, layout shell, theme provider
│   ├── main.tsx                   # Vite entry point
│   │
���   ├── components/
│   │   ├── layout/
│   │   │   ├── Sidebar.tsx        # Navigation sidebar
│   │   │   ├── Header.tsx         # Top bar (scan status, regime badge, time)
│   │   │   └── Shell.tsx          # App shell with sidebar + header + content
│   │   │
│   │   ├── common/
│   │   │   ├── RadarChart.tsx     # Reusable 5-axis radar (scanner + modal)
│   │   │   ├── ScoreBadge.tsx     # Signal pill (STRONG_BUY, BUY, HOLD, etc.)
│   │   │   ├── SparklineBar.tsx   # 7-day score trend bar chart
│   │   │   ├── MetricCard.tsx     # Key metric card (label, value, subtitle)
│   │   │   ├── ActionBadge.tsx    # URGENT / REVIEW / WATCH badge
│   │   │   └── SectorBar.tsx      # Horizontal progress bar with label
│   │   │
│   │   ├── scanner/
│   │   │   ├── ScannerTable.tsx   # Enhanced table with radar, sparklines
│   │   │   ├── ScannerRow.tsx     # Single stock row
│   │   │   └── SectorFilter.tsx   # Pill-style sector filter bar
│   │   │
│   │   ├── ticker/
│   │   │   ├── TickerModal.tsx    # Main modal container
│   │   │   ├── SynthesisBanner.tsx # Gemini AI synthesis
│   │   │   ├── KeyMetrics.tsx     # 6-card metrics grid
│   │   │   ├── EntryTiming.tsx    # Entry score, levels, position sizing
│   │   │   ├── DCFTab.tsx         # DCF valuation display
│   │   │   ├── CompsTab.tsx       # Peer comparables
│   │   │   ├── EarningsTab.tsx    # Earnings analysis
│   │   │   ├── MomentumTab.tsx    # Early momentum radar
│   │   │   └── DevilTab.tsx       # Devil's advocate review
│   │   │
│   │   ├── portfolio/
│   │   │   ├── PortfolioPage.tsx  # Full portfolio view
│   │   │   ├── ActionBanner.tsx   # Action items with priority badges
│   │   │   ├── HoldingCard.tsx    # Position card with P&L bar
│   │   │   ├── RiskDashboard.tsx  # Sector bars, risk metrics, macro flags
│   │   │   ├── DiversificationScore.tsx  # 0-100 concentration gauge
│   │   │   ├── CorrelationHeatmap.tsx    # Pairwise correlation grid
│   │   │   ├── WhatIfSimulator.tsx       # Add-stock impact preview
│   │   │   └── RebalanceSuggestions.tsx  # Smart swap recommendations
│   │   │
│   │   └── home/
│   │       ├── HomePage.tsx       # Time-aware dashboard
│   │       ├── SummaryCards.tsx    # Portfolio value, signals, alerts, win rate
│   │       ├── ActionItems.tsx    # Today's action items list
│   │       ├── NewSignals.tsx     # Signal changes today
│   │       └── MarketPulse.tsx    # SPY, VIX, 10Y, regime
│   │
│   ├── pages/
│   │   ├── Home.tsx
│   │   ├── Scanner.tsx
│   │   ├── Portfolio.tsx
│   │   ├── Backtest.tsx           # Basic migration
│   │   ├── Alerts.tsx             # Basic migration
│   │   ├── Accuracy.tsx           # Basic migration
│   │   └── Momentum.tsx           # Basic migration
│   │
│   ├── hooks/
│   │   ├── useApi.ts             # Generic fetch wrapper with loading/error states
│   │   ├── useScanStatus.ts      # Poll /scan/status during active scans
│   │   ├── useTimeOfDay.ts       # Morning/midday/evening detection
│   │   └── usePortfolio.ts       # Holdings + risk data
│   │
│   ├── lib/
│   │   ├── api.ts                # API base URL, endpoint constants
│   │   ├── types.ts              # TypeScript interfaces for API responses
│   │   └── colors.ts             # Score-to-color mapping (green/amber/red thresholds)
│   │
│   └── styles/
│       └── globals.css           # Tailwind directives, custom animations
│
├── index.html                    # Vite HTML entry
├── vite.config.ts
├── tailwind.config.ts
├── tsconfig.json
└── package.json
```

## Section 1: Home Dashboard

A context-aware landing page that surfaces what matters based on time of day.

### Time-of-Day Modes

| Mode | Hours (Pacific) | Priority Content |
|------|----------------|-----------------|
| Morning | Pre-market → 11am | Overnight changes, new signals, action items, market pulse |
| Midday | 11am → 2pm | Intraday movers, alert triggers, portfolio P&L |
| Evening | 2pm → close | End-of-day summary, next-day prep, performance review |

### Layout

Top section: 4 summary cards in a row
- Portfolio Value (total + daily P&L)
- New Signals (count + breakdown)
- Alerts (count + top alert preview)
- Win Rate (running total)

Bottom section: 2-column grid
- Left (wider): Action items list — prioritized as URGENT (red), REVIEW (amber), WATCH (green). Each item shows ticker, reason, and suggested action.
- Right: New Signals card (today's signal changes) + Market Pulse card (SPY, VIX, 10Y, regime)

### Data Sources

- Summary cards: `/scan/cached`, `/alerts`, `/portfolio`, `/accuracy`
- Action items: derived from `/risk/stop-losses`, `/profit/{ticker}`, earnings guard data in scan results
- Market pulse: `/scan/cached` (regime data is included in scan results)

All data comes from existing endpoints. No new backend routes needed.

## Section 2: Enhanced Scanner Table

The existing scanner table rebuilt with visual score indicators.

### Per-Row Enhancements

| Element | Description |
|---------|-------------|
| Radar chart | Mini 5-axis spider chart (72×72px) showing Fund/Val/Tech/Risk/Grow shape. Color: green (score >75), indigo (60-75), amber (<60). Hover tooltip shows exact scores. |
| Score + delta | Overall score in large text + ▲/▼ change vs yesterday (from daily snapshots) |
| 7-day sparkline | Bar chart showing score trend over 7 days. Bar color: green (rising), indigo (flat), amber (falling). Data from daily snapshots. |
| Signal badge | Pill-style badge: STRONG_BUY (green), BUY (light green), HOLD (gray), WAIT (amber), SELL (red) |
| Streak | Fire emoji + day count for consecutive days in top 20 (from streak_tracker.json) |
| Row hover | Background highlight + subtle translateY lift, 0.15s transition |

### Filters

- Sector pills: horizontal scrollable row of GICS sector chips. Active = indigo fill, inactive = outline.
- Signal dropdown: filter by signal type
- Strategy dropdown: switch between conservative/balanced/aggressive

### Clicking a Row

Opens the ticker detail modal (Section 3).

### Data Sources

- Table data: `/scan/cached` (all scores, signals, prices)
- Score deltas: compare current scan with previous day's snapshot from `data/daily_snapshots/`
- Sparkline data: last 7 daily snapshots
- Streaks: included in scan results (from streak_tracker)

Delta and sparkline data require a new lightweight endpoint: `GET /snapshots/recent?days=7` that returns the last N daily snapshots. This avoids loading all 47 snapshot files on the frontend.

## Section 3: Ticker Detail Modal

Redesigned modal that opens when clicking any stock row or ticker link.

### Layout (top to bottom)

**Header**: Ticker + company name + sector | Signal badge + streak | Price + daily change (right-aligned)

**AI Synthesis Banner**: 2-3 sentence Gemini-generated summary connecting all dimensions. Highlights strengths, weaknesses, and conflicts (e.g., "strong growth but expensive valuation"). Gradient border (green/indigo). Generated during scan, cached in scan results.

**Two-column section**:
- Left: Large radar chart (170×170px) with labeled axes showing exact scores. Score dots on vertices color-coded by level.
- Right: 6 key metric cards in a 3×2 grid — RSI, P/E, ML Confidence, Revenue Growth, Support Level, Analyst Target. Each card: label, large value, contextual subtitle.

**Tabbed deep dive**: 6 tabs, lazy-loaded on click:
1. **Entry Timing** — entry score (0-10 with progress bar), key price levels (resistance/current/support/MA50), suggested position sizing (conviction multiplier, allocation, stop-loss, profit targets), timing factor pills
2. **DCF Valuation** — intrinsic value, margin of safety, assumptions table
3. **Peer Comps** — comparable companies table with P/E, EV/EBITDA, P/S multiples
4. **Earnings** — beat/miss history, margin trends, quality scores
5. **Momentum** — early momentum radar (5 leading indicators with individual scores)
6. **Devil's Advocate** — Gemini risk review with flagged concerns

### Data Sources

- Header + radar + metrics: `/scan/cached` (stock data included in scan results)
- Synthesis: new field in scan results, generated by Gemini during scan pipeline
- Entry Timing: `/entry/{ticker}`
- DCF: `/dcf/{ticker}/summary`
- Comps: `/comps/{ticker}`
- Earnings: `/earnings/{ticker}/analysis`
- Momentum: `/momentum/{ticker}`
- Devil's Advocate: `/devil/{ticker}`

### New Backend Work

1. **Gemini synthesis generation**: Add to scan pipeline — for each top-20 stock, call Gemini with scores/signals/metrics to generate a 2-3 sentence synthesis. Cache in `scan_results.json` under a `synthesis` field per stock.
2. **`GET /snapshots/recent?days=7`**: Return last N daily snapshots for sparkline/delta data.

## Section 4: Portfolio Page

Full redesign with P&L visualization, risk management, and diversification tools.

### Layout (top to bottom)

**Header**: Total portfolio value (large) + daily P&L + position count + sector count + cash balance. Action buttons: Rebalance, Run Scan.

**Action Items Banner**: Horizontal card strip with priority badges:
- URGENT (red, pulsing dot): positions near stop-loss
- REVIEW (amber): profit targets hit
- WATCH (amber): earnings proximity, signal downgrades
Clickable — opens the relevant holding card.

**Two-column section**:
- Left (wider): Holdings as cards, sorted by urgency then P&L
- Right: Risk Dashboard

### Holding Cards

Each card shows:
- Ticker + signal badge | P&L amount + percentage (right)
- Share count, avg cost, current value, portfolio weight
- P&L progress bar: gradient from stop-loss to profit targets, with T1/T2/T3 markers
- Stop-loss and profit target levels as text below the bar
- Border color indicates status: red (near stop), amber (profit target hit), default (healthy)
- Hover: card lifts (translateY -1px) + border glows to accent color

### Risk Dashboard

**Sector Exposure**: Horizontal bars for each GICS sector in portfolio. Bar color shifts to amber when sector weight exceeds 35%. Shows percentage label.

Sectors use GICS classification (same as `sector.py`): Technology, Healthcare, Financials, Industrials, Energy, Consumer Discretionary, Consumer Staples, Materials, Utilities, Real Estate, Communication Services.

**Risk Metrics**: 4 small cards — Beta, Sharpe Ratio, Max Drawdown, Avg Pairwise Correlation.

**Macro Flags**: Pill badges for current regime, concentration warnings, commodity exposure.

### Diversification Features

**Diversification Score (0-100)**: Single composite score based on:
- Sector concentration (Herfindahl index on sector weights)
- Pairwise correlation (average correlation between holdings)
- Position count (more positions = more diversified, up to a point)
- Cash allocation (some cash = buffer)
Displayed as a circular gauge with color coding (green >70, amber 40-70, red <40). Below the gauge: top 2-3 factors dragging the score down.

**Correlation Heatmap**: Grid showing pairwise 90-day correlation between all holdings. Color scale: dark blue (low correlation, good) → red (high correlation, risky). Hover shows exact correlation value. Highlights clusters of highly correlated positions.

**"What If" Simulator**: Input field to type a ticker. Shows projected impact on:
- Sector balance (before/after bar comparison)
- Diversification score change
- Correlation with existing holdings
- Portfolio beta change
Helps make informed decisions before buying.

**Rebalance Suggestions**: Smart swap recommendations when:
- A sector exceeds 35% weight
- A position is near stop-loss and has low score
- Diversification score is below 60
Format: "Replace [TICKER_A] (reason) with [TICKER_B] (from top 20, different sector) to improve diversification by X points"

### Data Sources

- Holdings: `/risk/positions`, `/portfolio`
- Stop-losses: `/risk/stop-losses`
- Profit targets: `/profit/{ticker}` for each holding
- Risk metrics: `/risk/summary`
- Sector data: derived from holdings (sector field in stock data)
- Correlation: new endpoint needed (see below)

### New Backend Work

1. **`GET /portfolio/diversification`**: Returns diversification score, component breakdown, and suggestions. Computes Herfindahl index, pairwise correlations from cached price data, and generates improvement suggestions.
2. **`GET /portfolio/correlation`**: Returns pairwise correlation matrix for current holdings (90-day window from cached yfinance data).
3. **`GET /portfolio/whatif?ticker=CRWD`**: Returns projected impact of adding a stock — sector change, correlation impact, beta change, diversification score delta.

## Section 5: Other Tabs (Basic Migration)

Backtest, Alerts, Accuracy, and Momentum tabs get migrated to React components with consistent Tailwind styling but no functional changes. Same data, same layout logic, just cleaner presentation with the shared design system (dark cards, consistent typography, proper spacing).

## Navigation

Replace the current 7-tab horizontal bar with a collapsible sidebar:

| Icon | Label | Route |
|------|-------|-------|
| 🏠 | Home | `/` |
| 📊 | Scanner | `/scanner` |
| 💼 | Portfolio | `/portfolio` |
| 📈 | Backtest | `/backtest` |
| 🔔 | Alerts | `/alerts` |
| 🎯 | Accuracy | `/accuracy` |
| 🚀 | Momentum | `/momentum` |

Sidebar collapses to icon-only on smaller screens. Active page highlighted with indigo accent.

## Design System

**Theme**: Dark mode default (matching current app preference).

**Colors**:
- Background: `#0f1117` (base), `#1e293b` (cards/surfaces)
- Border: `#334155`
- Text: `#f1f5f9` (primary), `#94a3b8` (secondary), `#64748b` (muted)
- Green: `#22c55e` (positive, strong scores)
- Amber: `#f59e0b` (caution, moderate scores)
- Red: `#ef4444` (danger, weak scores, losses)
- Indigo: `#6366f1` (accent, active states, neutral data)

**Score Color Thresholds**:
- Green: score > 75
- Amber: score 50-75
- Red: score < 50

**Interactions**:
- Card hover: `translateY(-1px)` + border color change, `transition: all 0.2s`
- Row hover: background highlight, `transition: background 0.15s`
- Tab switch: Framer Motion `layoutId` for sliding indicator
- Modal open/close: Framer Motion fade + scale
- Page transitions: Framer Motion fade

**Typography**: System font stack (`system-ui, -apple-system, ...`). No custom fonts to load.

## New Backend Endpoints Summary

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `GET /snapshots/recent?days=7` | GET | Last N daily snapshots for sparklines and score deltas |
| `GET /portfolio/diversification` | GET | Diversification score, breakdown, improvement suggestions |
| `GET /portfolio/correlation` | GET | Pairwise 90-day correlation matrix for holdings |
| `GET /portfolio/whatif?ticker=X` | GET | Projected impact of adding a stock to portfolio |

Gemini synthesis is not a new endpoint — it's added to the scan pipeline and cached in `scan_results.json`.

## Out of Scope

- Light mode (dark only for now — can add later via Tailwind dark mode toggle)
- Mobile responsive (desktop-first, this is a Mac mini daily driver)
- Authentication/multi-user
- Real-time WebSocket updates (polling is fine for this use case)
- Database migration (JSON files stay)
- Changes to ML models, scoring logic, or strategy weights
