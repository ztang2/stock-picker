# Stock Picker Frontend Redesign — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Rebuild the stock-picker frontend in React + TypeScript with a new Home dashboard, enhanced scanner with radar charts, redesigned ticker modal with Gemini synthesis, and overhauled portfolio page with diversification tools.

**Architecture:** The React app lives in `frontend/` at the project root. Vite builds to `static/dist/`. FastAPI serves `static/dist/` as a static mount. Four new backend endpoints support sparkline data, diversification scoring, correlation, and what-if analysis. Gemini synthesis is added to the scan pipeline.

**Tech Stack:** React 18, TypeScript, Vite, Tailwind CSS 3, Framer Motion 11, Recharts 2, React Router 6

**Spec:** `docs/superpowers/specs/2026-04-06-frontend-redesign-design.md`

---

## Task 1: Scaffold React + Vite + Tailwind Project

**Files:**
- Create: `frontend/package.json`
- Create: `frontend/vite.config.ts`
- Create: `frontend/tsconfig.json`
- Create: `frontend/tailwind.config.ts`
- Create: `frontend/postcss.config.js`
- Create: `frontend/index.html`
- Create: `frontend/src/main.tsx`
- Create: `frontend/src/App.tsx`
- Create: `frontend/src/styles/globals.css`

- [ ] **Step 1: Create the Vite project**

```bash
cd /Users/zhuorantang/clawd/stock-picker
npm create vite@latest frontend -- --template react-ts
```

- [ ] **Step 2: Install dependencies**

```bash
cd frontend
npm install react-router-dom framer-motion recharts
npm install -D tailwindcss @tailwindcss/vite
```

- [ ] **Step 3: Configure Tailwind**

Replace `frontend/src/index.css` with `frontend/src/styles/globals.css`:

```css
@import "tailwindcss";

@theme {
  --color-base: #0f1117;
  --color-surface: #1e293b;
  --color-border: #334155;
  --color-text-primary: #f1f5f9;
  --color-text-secondary: #94a3b8;
  --color-text-muted: #64748b;
  --color-positive: #22c55e;
  --color-caution: #f59e0b;
  --color-danger: #ef4444;
  --color-accent: #6366f1;
}

body {
  @apply bg-base text-text-primary font-[system-ui,-apple-system,sans-serif] m-0;
}

@keyframes pulse-dot {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.4; }
}

.animate-pulse-dot {
  animation: pulse-dot 2s ease-in-out infinite;
}
```

- [ ] **Step 4: Configure Vite**

Replace `frontend/vite.config.ts`:

```typescript
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";

export default defineConfig({
  plugins: [react(), tailwindcss()],
  build: {
    outDir: "../static/dist",
    emptyOutDir: true,
  },
  server: {
    proxy: {
      "/scan": "http://localhost:8000",
      "/stock": "http://localhost:8000",
      "/entry": "http://localhost:8000",
      "/dcf": "http://localhost:8000",
      "/comps": "http://localhost:8000",
      "/earnings": "http://localhost:8000",
      "/momentum": "http://localhost:8000",
      "/review": "http://localhost:8000",
      "/sectors": "http://localhost:8000",
      "/top": "http://localhost:8000",
      "/backtest": "http://localhost:8000",
      "/accuracy": "http://localhost:8000",
      "/alerts": "http://localhost:8000",
      "/portfolio": "http://localhost:8000",
      "/risk": "http://localhost:8000",
      "/profit": "http://localhost:8000",
      "/sizing": "http://localhost:8000",
      "/snapshots": "http://localhost:8000",
      "/health": "http://localhost:8000",
    },
  },
});
```

- [ ] **Step 5: Set up App shell with router**

Replace `frontend/src/App.tsx`:

```tsx
import { BrowserRouter, Routes, Route } from "react-router-dom";

function Placeholder({ name }: { name: string }) {
  return (
    <div className="flex items-center justify-center h-screen text-text-secondary">
      {name} — coming soon
    </div>
  );
}

export default function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/" element={<Placeholder name="Home" />} />
        <Route path="/scanner" element={<Placeholder name="Scanner" />} />
        <Route path="/portfolio" element={<Placeholder name="Portfolio" />} />
        <Route path="/backtest" element={<Placeholder name="Backtest" />} />
        <Route path="/alerts" element={<Placeholder name="Alerts" />} />
        <Route path="/accuracy" element={<Placeholder name="Accuracy" />} />
        <Route path="/momentum" element={<Placeholder name="Momentum" />} />
      </Routes>
    </BrowserRouter>
  );
}
```

- [ ] **Step 6: Update main.tsx to use globals.css**

Replace `frontend/src/main.tsx`:

```tsx
import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import "./styles/globals.css";
import App from "./App";

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <App />
  </StrictMode>
);
```

- [ ] **Step 7: Verify it runs**

```bash
cd /Users/zhuorantang/clawd/stock-picker/frontend
npm run dev
```

Expected: Vite dev server starts, browser shows "Home — coming soon" on dark background at http://localhost:5173.

- [ ] **Step 8: Commit**

```bash
cd /Users/zhuorantang/clawd/stock-picker
git add frontend/
git commit -m "feat: scaffold React + Vite + Tailwind frontend"
```

---

## Task 2: TypeScript Types and API Client

**Files:**
- Create: `frontend/src/lib/types.ts`
- Create: `frontend/src/lib/api.ts`
- Create: `frontend/src/lib/colors.ts`
- Create: `frontend/src/hooks/useApi.ts`

- [ ] **Step 1: Define core TypeScript interfaces**

Create `frontend/src/lib/types.ts`:

```typescript
export interface MarketRegime {
  regime: "bull" | "bear" | "sideways";
  confidence: number;
  description: string;
  spy_price: number;
  spy_ma200: number;
  spy_ma50: number;
  spy_rsi: number;
  macro: {
    vix: { current: number; ma20: number; ma50: number };
    us10y: { current: number };
    dxy: { current: number };
    oil: { current: number };
    qqq: { current: number };
  };
}

export interface SentimentData {
  score: number;
  consensus_score: number;
  pt_upside_score: number;
  recommendation: string;
  pt_upside_pct: number;
  analyst_count: number;
  details: string;
}

export interface Stock {
  rank: number;
  ticker: string;
  name: string;
  sector: string;
  industry: string;
  market_cap: number;
  composite_score: number;
  base_score: number;
  fundamentals_pct: number;
  valuation_pct: number;
  technicals_pct: number;
  risk_pct: number;
  growth_pct: number;
  sentiment: SentimentData;
  sentiment_score: number;
  sentiment_pct: number;
  sector_rank: number;
  sector_size: number;
  entry_signal: string;
  entry_score: number;
  sell_signal: string;
  sell_urgency: string;
  sell_reasons: string[];
  current_price: number;
  rsi: number;
  macd_histogram: number;
  adx: number;
  volatility: number;
  beta: number;
  volume_trend: number;
  ma50: number;
  ma200: number;
  above_ma50: boolean;
  above_ma200: boolean;
  dcf_intrinsic: number | null;
  dcf_margin_of_safety: number | null;
  dcf_verdict: string | null;
  dcf_confidence: string | null;
  comps_score: number | null;
  comps_verdict: string | null;
  piotroski_score: number | null;
  piotroski_grade: string | null;
  altman_z_score: number | null;
  altman_zone: string | null;
  quality_score: number | null;
  insider_sell_value: number;
  insider_buy_value: number;
  insider_sells_2026: number;
  insider_buys_2026: number;
  short_pct_float: number | null;
  smart_money_score: number | null;
  analyst_score: number | null;
  insider_score: number | null;
  data_freshness: string;
  data_age_days: number;
  consecutive_days: number;
  ml_score: number | null;
  ml_signal: string | null;
  alpha158_score: number | null;
  fcf_yield: number | null;
  synthesis?: string;
}

export interface ScanResult {
  timestamp: string;
  strategy: string;
  market_regime: MarketRegime;
  top: Stock[];
  all_scores: Stock[];
  stocks_analyzed: number;
  stocks_after_filter: number;
}

export interface ScanStatus {
  running: boolean;
  started_at: string | null;
  finished_at: string | null;
  error: string | null;
  strategy: string;
}

export interface Alert {
  ticker: string;
  severity: "critical" | "warning" | "info";
  message: string;
  timestamp: string;
}

export interface AlertsResponse {
  current: Alert[];
  history: Alert[];
}

export interface AccuracyResponse {
  total_predictions: number;
  correct: number;
  accuracy_pct: number;
  by_signal: Record<string, { correct: number; total: number; accuracy: number }>;
  recent_snapshots: Array<{
    date: string;
    signals: Array<{ ticker: string; signal: string; entry_price: number; current_price: number }>;
  }>;
}

export interface StopLossAlert {
  ticker: string;
  current_price: number;
  entry_price: number;
  loss_pct: number;
  status: string;
  message: string;
}

export interface ProfitTarget {
  ticker: string;
  entry_price: number;
  current_price: number;
  gain_pct: number;
  profit_taking_levels: Array<{
    level: string;
    triggered: boolean;
    price: number;
  }>;
}

export interface RiskSummary {
  total_portfolio_value: number;
  total_cost_basis: number;
  total_pnl: number;
  total_pnl_pct: number;
  positions: Array<{
    ticker: string;
    shares: number;
    entry_price: number;
    current_price: number;
    position_value: number;
    pnl: number;
    pnl_pct: number;
    risk_level: string;
  }>;
  stop_loss_distance_pct: number;
  concentration_warnings: string[];
}

export interface EntryTiming {
  ticker: string;
  rsi: number;
  rsi_signal: string;
  support_levels: number[];
  resistance_levels: number[];
  ma_distance_pct: number;
  volume_signal: string;
  timing_score: number;
  recommendation: string;
}

export interface DevilsAdvocate {
  ticker: string;
  company_name: string;
  data_summary: Record<string, unknown>;
  quant_flags: {
    red_flags: Array<{ flag: string; detail: string; severity: string }>;
    green_flags: Array<{ flag: string; detail: string }>;
    risk_score: number;
    red_count: number;
    green_count: number;
  };
  review_text: string;
  risk_score: number;
  source: string;
  timestamp: string;
}

export interface BacktestResult {
  months_back: number;
  top_n: number;
  backtest_results: Array<{
    month: string;
    picks: string[];
    avg_return: number;
    best_stock: string;
    best_return: number;
    worst_return: number;
    drawdown: number;
  }>;
  summary: {
    total_return: number;
    win_rate: number;
    avg_win: number;
    avg_loss: number;
    sharpe_ratio: number;
  };
}

export interface DiversificationResponse {
  score: number;
  components: {
    sector_concentration: number;
    correlation_avg: number;
    position_count: number;
    cash_ratio: number;
  };
  dragging_factors: string[];
  suggestions: string[];
}

export interface CorrelationResponse {
  tickers: string[];
  matrix: number[][];
}

export interface WhatIfResponse {
  ticker: string;
  sector: string;
  sector_before: Record<string, number>;
  sector_after: Record<string, number>;
  diversification_before: number;
  diversification_after: number;
  correlation_with_holdings: Record<string, number>;
  beta_before: number;
  beta_after: number;
}

export interface SnapshotDay {
  date: string;
  stocks: Record<string, { composite_score: number; rank: number }>;
}

export type TimeOfDay = "morning" | "midday" | "evening";
```

- [ ] **Step 2: Create API client**

Create `frontend/src/lib/api.ts`:

```typescript
const BASE = "";

async function get<T>(path: string): Promise<T> {
  const res = await fetch(`${BASE}${path}`);
  if (!res.ok) throw new Error(`${res.status} ${res.statusText}`);
  return res.json();
}

export const api = {
  scanCached: () => get<import("./types").ScanResult>("/scan/cached"),
  scanStatus: () => get<import("./types").ScanStatus>("/scan/status"),
  stock: (ticker: string) => get<Record<string, unknown>>(`/stock/${ticker}`),
  entry: (ticker: string) => get<import("./types").EntryTiming>(`/entry/${ticker}`),
  dcf: (ticker: string) => get<Record<string, unknown>>(`/dcf/${ticker}/summary`),
  comps: (ticker: string) => get<Record<string, unknown>>(`/comps/${ticker}`),
  earnings: (ticker: string) => get<Record<string, unknown>>(`/earnings/${ticker}/analysis`),
  momentum: (ticker: string) => get<Record<string, unknown>>(`/momentum/${ticker}`),
  devil: (ticker: string) => get<import("./types").DevilsAdvocate>(`/review/${ticker}`),
  alerts: () => get<import("./types").AlertsResponse>("/alerts"),
  accuracy: () => get<import("./types").AccuracyResponse>("/accuracy"),
  backtest: (months = 6, topN = 20) =>
    get<import("./types").BacktestResult>(`/backtest?months_back=${months}&top_n=${topN}`),
  riskSummary: () => get<import("./types").RiskSummary>("/risk/summary"),
  stopLosses: () => get<{ alerts: import("./types").StopLossAlert[] }>("/risk/stop-losses"),
  positions: () => get<{ positions: Array<Record<string, unknown>> }>("/risk/positions"),
  portfolio: (stocks = 10) => get<Record<string, unknown>>(`/portfolio?stocks=${stocks}`),
  profit: (ticker: string) => get<import("./types").ProfitTarget>(`/profit/${ticker}`),
  sectors: () => get<{ sectors: Record<string, number>; total: number }>("/sectors"),
  snapshotsRecent: (days = 7) =>
    get<import("./types").SnapshotDay[]>(`/snapshots/recent?days=${days}`),
  diversification: () => get<import("./types").DiversificationResponse>("/portfolio/diversification"),
  correlation: () => get<import("./types").CorrelationResponse>("/portfolio/correlation"),
  whatIf: (ticker: string) => get<import("./types").WhatIfResponse>(`/portfolio/whatif?ticker=${ticker}`),
};
```

- [ ] **Step 3: Create color utilities**

Create `frontend/src/lib/colors.ts`:

```typescript
export function scoreColor(score: number): string {
  if (score > 75) return "text-positive";
  if (score >= 50) return "text-caution";
  return "text-danger";
}

export function scoreBg(score: number): string {
  if (score > 75) return "bg-positive/15 text-positive";
  if (score >= 50) return "bg-caution/15 text-caution";
  return "bg-danger/15 text-danger";
}

export function scoreHex(score: number): string {
  if (score > 75) return "#22c55e";
  if (score >= 50) return "#f59e0b";
  return "#ef4444";
}

export function signalColor(signal: string): string {
  switch (signal) {
    case "STRONG_BUY": return "bg-positive/15 text-positive";
    case "BUY": return "bg-positive/10 text-positive";
    case "HOLD": return "bg-text-secondary/15 text-text-secondary";
    case "WAIT": return "bg-caution/15 text-caution";
    case "SELL":
    case "STRONG_SELL": return "bg-danger/15 text-danger";
    default: return "bg-text-secondary/15 text-text-secondary";
  }
}

export function pnlColor(value: number): string {
  if (value > 0) return "text-positive";
  if (value < 0) return "text-danger";
  return "text-text-secondary";
}
```

- [ ] **Step 4: Create useApi hook**

Create `frontend/src/hooks/useApi.ts`:

```typescript
import { useState, useEffect, useCallback } from "react";

interface UseApiResult<T> {
  data: T | null;
  loading: boolean;
  error: string | null;
  refetch: () => void;
}

export function useApi<T>(fetcher: () => Promise<T>, deps: unknown[] = []): UseApiResult<T> {
  const [data, setData] = useState<T | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const refetch = useCallback(() => {
    setLoading(true);
    setError(null);
    fetcher()
      .then(setData)
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false));
  }, deps);

  useEffect(() => { refetch(); }, [refetch]);

  return { data, loading, error, refetch };
}
```

- [ ] **Step 5: Create useTimeOfDay hook**

Create `frontend/src/hooks/useTimeOfDay.ts`:

```typescript
import { useState, useEffect } from "react";
import type { TimeOfDay } from "../lib/types";

export function useTimeOfDay(): TimeOfDay {
  const [tod, setTod] = useState<TimeOfDay>(getTimeOfDay);

  useEffect(() => {
    const interval = setInterval(() => setTod(getTimeOfDay()), 60_000);
    return () => clearInterval(interval);
  }, []);

  return tod;
}

function getTimeOfDay(): TimeOfDay {
  const hour = new Date().getHours();
  if (hour < 11) return "morning";
  if (hour < 14) return "midday";
  return "evening";
}
```

- [ ] **Step 6: Verify TypeScript compiles**

```bash
cd /Users/zhuorantang/clawd/stock-picker/frontend
npx tsc --noEmit
```

Expected: No errors.

- [ ] **Step 7: Commit**

```bash
cd /Users/zhuorantang/clawd/stock-picker
git add frontend/src/lib/ frontend/src/hooks/
git commit -m "feat: add TypeScript types, API client, color utils, and hooks"
```

---

## Task 3: Layout Shell — Sidebar, Header, and App Shell

**Files:**
- Create: `frontend/src/components/layout/Sidebar.tsx`
- Create: `frontend/src/components/layout/Header.tsx`
- Create: `frontend/src/components/layout/Shell.tsx`
- Modify: `frontend/src/App.tsx`

- [ ] **Step 1: Build Sidebar component**

Create `frontend/src/components/layout/Sidebar.tsx`:

```tsx
import { NavLink } from "react-router-dom";
import { useState } from "react";

const NAV_ITEMS = [
  { to: "/", icon: "🏠", label: "Home" },
  { to: "/scanner", icon: "📊", label: "Scanner" },
  { to: "/portfolio", icon: "💼", label: "Portfolio" },
  { to: "/backtest", icon: "📈", label: "Backtest" },
  { to: "/alerts", icon: "🔔", label: "Alerts" },
  { to: "/accuracy", icon: "🎯", label: "Accuracy" },
  { to: "/momentum", icon: "🚀", label: "Momentum" },
];

export default function Sidebar() {
  const [collapsed, setCollapsed] = useState(false);

  return (
    <nav
      className={`flex flex-col bg-surface border-r border-border h-screen sticky top-0 transition-all duration-200 ${
        collapsed ? "w-16" : "w-48"
      }`}
    >
      <div className="flex items-center justify-between p-4 border-b border-border">
        {!collapsed && <span className="text-sm font-bold text-text-primary">Stock Picker</span>}
        <button
          onClick={() => setCollapsed(!collapsed)}
          className="text-text-muted hover:text-text-primary text-xs"
        >
          {collapsed ? "→" : "←"}
        </button>
      </div>
      <div className="flex flex-col gap-1 p-2 flex-1">
        {NAV_ITEMS.map((item) => (
          <NavLink
            key={item.to}
            to={item.to}
            end={item.to === "/"}
            className={({ isActive }) =>
              `flex items-center gap-3 px-3 py-2 rounded-lg text-sm transition-colors ${
                isActive
                  ? "bg-accent/15 text-accent font-semibold"
                  : "text-text-secondary hover:bg-surface hover:text-text-primary"
              }`
            }
          >
            <span className="text-base">{item.icon}</span>
            {!collapsed && <span>{item.label}</span>}
          </NavLink>
        ))}
      </div>
    </nav>
  );
}
```

- [ ] **Step 2: Build Header component**

Create `frontend/src/components/layout/Header.tsx`:

```tsx
import type { ScanResult } from "../../lib/types";

interface HeaderProps {
  scan: ScanResult | null;
}

export default function Header({ scan }: HeaderProps) {
  const regime = scan?.market_regime;

  const regimeColor = {
    bull: "bg-positive/15 text-positive",
    bear: "bg-danger/15 text-danger",
    sideways: "bg-caution/15 text-caution",
  }[regime?.regime ?? "sideways"] ?? "bg-text-secondary/15 text-text-secondary";

  return (
    <header className="flex items-center justify-between px-6 py-3 border-b border-border bg-surface">
      <div className="text-sm text-text-secondary">
        {scan ? (
          <>Last scan: {new Date(scan.timestamp).toLocaleTimeString()}</>
        ) : (
          "No scan data"
        )}
      </div>
      <div className="flex items-center gap-3">
        {regime && (
          <>
            <span className={`px-3 py-1 rounded-md text-xs font-semibold ${regimeColor}`}>
              Regime: {regime.regime.charAt(0).toUpperCase() + regime.regime.slice(1)}
            </span>
            <span className="text-xs text-text-muted">
              SPY ${regime.spy_price.toFixed(2)}
            </span>
            <span className="text-xs text-text-muted">
              VIX {regime.macro.vix.current.toFixed(1)}
            </span>
          </>
        )}
      </div>
    </header>
  );
}
```

- [ ] **Step 3: Build Shell component**

Create `frontend/src/components/layout/Shell.tsx`:

```tsx
import { Outlet } from "react-router-dom";
import Sidebar from "./Sidebar";
import Header from "./Header";
import type { ScanResult } from "../../lib/types";

interface ShellProps {
  scan: ScanResult | null;
}

export default function Shell({ scan }: ShellProps) {
  return (
    <div className="flex min-h-screen">
      <Sidebar />
      <div className="flex-1 flex flex-col">
        <Header scan={scan} />
        <main className="flex-1 p-6 overflow-auto">
          <Outlet />
        </main>
      </div>
    </div>
  );
}
```

- [ ] **Step 4: Wire Shell into App with scan data**

Replace `frontend/src/App.tsx`:

```tsx
import { BrowserRouter, Routes, Route } from "react-router-dom";
import Shell from "./components/layout/Shell";
import { useApi } from "./hooks/useApi";
import { api } from "./lib/api";
import type { ScanResult } from "./lib/types";
import { createContext, useContext } from "react";

export const ScanContext = createContext<{
  scan: ScanResult | null;
  loading: boolean;
  refetch: () => void;
}>({ scan: null, loading: true, refetch: () => {} });

export function useScan() {
  return useContext(ScanContext);
}

function Placeholder({ name }: { name: string }) {
  return (
    <div className="flex items-center justify-center h-64 text-text-secondary">
      {name} — coming soon
    </div>
  );
}

export default function App() {
  const { data: scan, loading, refetch } = useApi<ScanResult>(() => api.scanCached());

  return (
    <ScanContext.Provider value={{ scan, loading, refetch }}>
      <BrowserRouter>
        <Routes>
          <Route element={<Shell scan={scan} />}>
            <Route path="/" element={<Placeholder name="Home" />} />
            <Route path="/scanner" element={<Placeholder name="Scanner" />} />
            <Route path="/portfolio" element={<Placeholder name="Portfolio" />} />
            <Route path="/backtest" element={<Placeholder name="Backtest" />} />
            <Route path="/alerts" element={<Placeholder name="Alerts" />} />
            <Route path="/accuracy" element={<Placeholder name="Accuracy" />} />
            <Route path="/momentum" element={<Placeholder name="Momentum" />} />
          </Route>
        </Routes>
      </BrowserRouter>
    </ScanContext.Provider>
  );
}
```

- [ ] **Step 5: Verify the shell renders**

```bash
cd /Users/zhuorantang/clawd/stock-picker/frontend
npm run dev
```

Expected: Dark sidebar with navigation links, header showing scan timestamp and regime badge, main content area showing "Home — coming soon". Make sure the FastAPI server is running on port 8000 for the proxy to work.

- [ ] **Step 6: Commit**

```bash
cd /Users/zhuorantang/clawd/stock-picker
git add frontend/src/components/layout/ frontend/src/App.tsx
git commit -m "feat: add layout shell with sidebar, header, and scan context"
```

---

## Task 4: Common Components — RadarChart, ScoreBadge, MetricCard, SparklineBar

**Files:**
- Create: `frontend/src/components/common/RadarChart.tsx`
- Create: `frontend/src/components/common/ScoreBadge.tsx`
- Create: `frontend/src/components/common/MetricCard.tsx`
- Create: `frontend/src/components/common/SparklineBar.tsx`
- Create: `frontend/src/components/common/ActionBadge.tsx`
- Create: `frontend/src/components/common/SectorBar.tsx`

- [ ] **Step 1: Build RadarChart**

Create `frontend/src/components/common/RadarChart.tsx`:

```tsx
import { scoreHex } from "../../lib/colors";

interface RadarChartProps {
  scores: { fund: number; val: number; tech: number; risk: number; grow: number };
  size?: number;
  showLabels?: boolean;
}

const AXES = [
  { key: "fund" as const, label: "Fund", angle: -90 },
  { key: "val" as const, label: "Val", angle: -18 },
  { key: "tech" as const, label: "Tech", angle: 54 },
  { key: "risk" as const, label: "Risk", angle: 126 },
  { key: "grow" as const, label: "Grow", angle: 198 },
];

function polarToXY(angle: number, radius: number, cx: number, cy: number) {
  const rad = (angle * Math.PI) / 180;
  return { x: cx + radius * Math.cos(rad), y: cy + radius * Math.sin(rad) };
}

function makePolygon(scores: Record<string, number>, maxR: number, cx: number, cy: number) {
  return AXES.map(({ key, angle }) => {
    const r = (scores[key] / 100) * maxR;
    const { x, y } = polarToXY(angle, r, cx, cy);
    return `${x},${y}`;
  }).join(" ");
}

function makeGridPolygon(pct: number, maxR: number, cx: number, cy: number) {
  return AXES.map(({ angle }) => {
    const { x, y } = polarToXY(angle, maxR * pct, cx, cy);
    return `${x},${y}`;
  }).join(" ");
}

export default function RadarChart({ scores, size = 72, showLabels = true }: RadarChartProps) {
  const vb = 100;
  const cx = vb / 2;
  const cy = vb / 2;
  const maxR = 35;
  const labelR = maxR + (showLabels ? 12 : 0);

  const avgScore = (scores.fund + scores.val + scores.tech + scores.risk + scores.grow) / 5;
  const fillColor = scoreHex(avgScore);

  return (
    <svg viewBox={`0 0 ${vb} ${vb}`} width={size} height={size}>
      {/* Grid rings */}
      {[1, 0.66, 0.33].map((pct) => (
        <polygon
          key={pct}
          points={makeGridPolygon(pct, maxR, cx, cy)}
          fill="none"
          stroke="#334155"
          strokeWidth="0.5"
          opacity={0.4 * pct}
        />
      ))}
      {/* Axis lines */}
      {AXES.map(({ key, angle }) => {
        const { x, y } = polarToXY(angle, maxR, cx, cy);
        return <line key={key} x1={cx} y1={cy} x2={x} y2={y} stroke="#334155" strokeWidth="0.5" opacity="0.3" />;
      })}
      {/* Data polygon */}
      <polygon points={makePolygon(scores, maxR, cx, cy)} fill={`${fillColor}20`} stroke={fillColor} strokeWidth="1.5" />
      {/* Score dots */}
      {AXES.map(({ key, angle }) => {
        const r = (scores[key] / 100) * maxR;
        const { x, y } = polarToXY(angle, r, cx, cy);
        return <circle key={key} cx={x} cy={y} r={showLabels ? 2.5 : 1.5} fill={scoreHex(scores[key])} />;
      })}
      {/* Labels */}
      {showLabels &&
        AXES.map(({ key, label, angle }) => {
          const { x, y } = polarToXY(angle, labelR, cx, cy);
          const anchor = x < cx - 5 ? "end" : x > cx + 5 ? "start" : "middle";
          return (
            <text key={key} x={x} y={y} textAnchor={anchor} dominantBaseline="middle" fill="#94a3b8" fontSize="6" fontWeight="600">
              {showLabels ? `${label} ${scores[key]}` : label}
            </text>
          );
        })}
    </svg>
  );
}
```

- [ ] **Step 2: Build ScoreBadge**

Create `frontend/src/components/common/ScoreBadge.tsx`:

```tsx
import { signalColor } from "../../lib/colors";

interface ScoreBadgeProps {
  signal: string;
  className?: string;
}

export default function ScoreBadge({ signal, className = "" }: ScoreBadgeProps) {
  return (
    <span className={`px-2.5 py-1 rounded-md text-[11px] font-bold ${signalColor(signal)} ${className}`}>
      {signal}
    </span>
  );
}
```

- [ ] **Step 3: Build MetricCard**

Create `frontend/src/components/common/MetricCard.tsx`:

```tsx
interface MetricCardProps {
  label: string;
  value: string;
  subtitle?: string;
  valueColor?: string;
}

export default function MetricCard({ label, value, subtitle, valueColor = "text-text-primary" }: MetricCardProps) {
  return (
    <div className="p-3 rounded-lg bg-surface border border-border">
      <div className="text-[10px] text-text-muted uppercase tracking-wider">{label}</div>
      <div className={`text-xl font-bold mt-0.5 ${valueColor}`}>{value}</div>
      {subtitle && <div className="text-[11px] text-text-secondary mt-0.5">{subtitle}</div>}
    </div>
  );
}
```

- [ ] **Step 4: Build SparklineBar**

Create `frontend/src/components/common/SparklineBar.tsx`:

```tsx
interface SparklineBarProps {
  values: number[];
  height?: number;
}

export default function SparklineBar({ values, height = 28 }: SparklineBarProps) {
  if (values.length === 0) return null;
  const max = Math.max(...values);
  const isRising = values.length >= 2 && values[values.length - 1] > values[0];
  const isFalling = values.length >= 2 && values[values.length - 1] < values[0] - 3;

  return (
    <div className="flex items-end gap-0.5 px-1" style={{ height }}>
      {values.map((v, i) => {
        const pct = max > 0 ? (v / max) * 100 : 0;
        const isRecent = i >= values.length - 2;
        let color = "bg-accent";
        if (isRecent) color = isRising ? "bg-positive" : isFalling ? "bg-caution" : "bg-accent";
        else if (i < values.length - 3) color = "bg-border";
        return <div key={i} className={`flex-1 rounded-sm ${color}`} style={{ height: `${pct}%` }} />;
      })}
    </div>
  );
}
```

- [ ] **Step 5: Build ActionBadge**

Create `frontend/src/components/common/ActionBadge.tsx`:

```tsx
type Priority = "urgent" | "review" | "watch";

const STYLES: Record<Priority, string> = {
  urgent: "bg-danger/15 text-danger",
  review: "bg-caution/15 text-caution",
  watch: "bg-positive/15 text-positive",
};

interface ActionBadgeProps {
  priority: Priority;
}

export default function ActionBadge({ priority }: ActionBadgeProps) {
  return (
    <span className={`px-1.5 py-0.5 rounded text-[10px] font-bold uppercase ${STYLES[priority]}`}>
      {priority}
    </span>
  );
}
```

- [ ] **Step 6: Build SectorBar**

Create `frontend/src/components/common/SectorBar.tsx`:

```tsx
interface SectorBarProps {
  label: string;
  pct: number;
  warnThreshold?: number;
}

export default function SectorBar({ label, pct, warnThreshold = 35 }: SectorBarProps) {
  const isOver = pct >= warnThreshold;

  return (
    <div className="mb-2">
      <div className="flex justify-between text-xs mb-1">
        <span className="text-text-secondary">{label}</span>
        <span className={`font-semibold ${isOver ? "text-caution" : "text-positive"}`}>
          {pct.toFixed(0)}%{isOver ? " ⚠️" : ""}
        </span>
      </div>
      <div className="h-1.5 rounded-full bg-border overflow-hidden">
        <div
          className={`h-full rounded-full transition-all ${isOver ? "bg-gradient-to-r from-accent to-caution" : "bg-accent"}`}
          style={{ width: `${Math.min(pct, 100)}%` }}
        />
      </div>
    </div>
  );
}
```

- [ ] **Step 7: Commit**

```bash
cd /Users/zhuorantang/clawd/stock-picker
git add frontend/src/components/common/
git commit -m "feat: add common components — RadarChart, ScoreBadge, MetricCard, SparklineBar, ActionBadge, SectorBar"
```

---

## Task 5: New Backend Endpoints

**Files:**
- Modify: `src/api.py` — add 4 new endpoints
- Create: `src/diversification.py` — diversification score computation
- Modify: `src/pipeline.py` — add Gemini synthesis to scan

- [ ] **Step 1: Create diversification module**

Create `src/diversification.py`:

```python
import json
import numpy as np
from pathlib import Path

DATA_DIR = Path(__file__).parent.parent / "data"


def _load_holdings():
    path = DATA_DIR / "holdings.json"
    if not path.exists():
        return []
    with open(path) as f:
        return json.load(f)


def _load_price_cache():
    path = DATA_DIR / "stock_data_cache.json"
    if not path.exists():
        return {}
    with open(path) as f:
        return json.load(f)


def _sector_weights(holdings, scan_data):
    ticker_sector = {}
    for s in scan_data.get("all_scores", []) + scan_data.get("top", []):
        ticker_sector[s["ticker"]] = s.get("sector", "Unknown")

    sector_values = {}
    total = 0
    for h in holdings:
        val = h.get("shares", 0) * h.get("current_price", h.get("entry_price", 0))
        sector = ticker_sector.get(h["ticker"], "Unknown")
        sector_values[sector] = sector_values.get(sector, 0) + val
        total += val

    if total == 0:
        return {}
    return {s: v / total * 100 for s, v in sector_values.items()}


def _herfindahl(weights):
    if not weights:
        return 1.0
    return sum((w / 100) ** 2 for w in weights.values())


def _pairwise_correlations(tickers, cache, days=90):
    closes = {}
    for t in tickers:
        hist = cache.get(t, {}).get("history", {}).get("Close", {})
        if isinstance(hist, dict):
            dates = sorted(hist.keys())[-days:]
            closes[t] = [hist[d] for d in dates]

    tickers_with_data = [t for t in tickers if t in closes and len(closes[t]) >= 20]
    if len(tickers_with_data) < 2:
        return tickers_with_data, np.array([])

    min_len = min(len(closes[t]) for t in tickers_with_data)
    matrix = np.array([closes[t][-min_len:] for t in tickers_with_data])
    returns = np.diff(matrix, axis=1) / matrix[:, :-1]
    returns = np.nan_to_num(returns)
    corr = np.corrcoef(returns)
    return tickers_with_data, corr


def compute_diversification(scan_data):
    holdings = _load_holdings()
    if not holdings:
        return {
            "score": 0,
            "components": {"sector_concentration": 0, "correlation_avg": 0, "position_count": 0, "cash_ratio": 0},
            "dragging_factors": ["No holdings found"],
            "suggestions": [],
        }

    cache = _load_price_cache()
    sector_w = _sector_weights(holdings, scan_data)
    hhi = _herfindahl(sector_w)

    tickers = [h["ticker"] for h in holdings]
    tickers_with_data, corr = _pairwise_correlations(tickers, cache)

    avg_corr = 0.0
    if corr.size > 0:
        n = corr.shape[0]
        upper = [corr[i][j] for i in range(n) for j in range(i + 1, n)]
        avg_corr = float(np.mean(upper)) if upper else 0.0

    position_count = len(holdings)
    count_score = min(position_count / 10, 1.0) * 100

    sector_score = max(0, (1 - hhi) / 0.9) * 100
    corr_score = max(0, (1 - avg_corr)) * 100

    total = sector_score * 0.4 + corr_score * 0.3 + count_score * 0.3

    dragging = []
    if sector_score < 60:
        top_sector = max(sector_w, key=sector_w.get) if sector_w else "N/A"
        dragging.append(f"Sector concentration: {top_sector} at {sector_w.get(top_sector, 0):.0f}%")
    if corr_score < 60:
        dragging.append(f"High avg correlation: {avg_corr:.2f}")
    if count_score < 60:
        dragging.append(f"Only {position_count} positions (target: 8-10)")

    suggestions = []
    for sector, w in sector_w.items():
        if w > 35:
            suggestions.append(f"Reduce {sector} exposure ({w:.0f}%) — consider swapping weakest holding")

    return {
        "score": round(total, 1),
        "components": {
            "sector_concentration": round(sector_score, 1),
            "correlation_avg": round(avg_corr, 3),
            "position_count": position_count,
            "cash_ratio": 0,
        },
        "dragging_factors": dragging,
        "suggestions": suggestions,
    }


def compute_correlation(scan_data):
    holdings = _load_holdings()
    tickers = [h["ticker"] for h in holdings]
    cache = _load_price_cache()
    tickers_with_data, corr = _pairwise_correlations(tickers, cache)
    return {
        "tickers": tickers_with_data,
        "matrix": corr.tolist() if corr.size > 0 else [],
    }


def compute_whatif(ticker, scan_data):
    holdings = _load_holdings()
    cache = _load_price_cache()

    sector_before = _sector_weights(holdings, scan_data)
    ticker_sector = "Unknown"
    ticker_beta = 1.0
    for s in scan_data.get("all_scores", []) + scan_data.get("top", []):
        if s["ticker"] == ticker:
            ticker_sector = s.get("sector", "Unknown")
            ticker_beta = s.get("beta", 1.0)
            break

    mock_holding = {"ticker": ticker, "shares": 1, "current_price": 1000, "entry_price": 1000}
    sector_after = _sector_weights(holdings + [mock_holding], scan_data)

    tickers_before = [h["ticker"] for h in holdings]
    tickers_after = tickers_before + [ticker]
    _, corr_before = _pairwise_correlations(tickers_before, cache)
    _, corr_after = _pairwise_correlations(tickers_after, cache)

    def avg_corr(c):
        if c.size == 0:
            return 0.0
        n = c.shape[0]
        upper = [c[i][j] for i in range(n) for j in range(i + 1, n)]
        return float(np.mean(upper)) if upper else 0.0

    corr_with = {}
    if corr_after.size > 0:
        n = corr_after.shape[0]
        tickers_all = tickers_before + [ticker]
        if n == len(tickers_all):
            for i, t in enumerate(tickers_all[:-1]):
                corr_with[t] = round(float(corr_after[i][n - 1]), 3)

    betas = [s.get("beta", 1.0) for s in scan_data.get("all_scores", []) if s["ticker"] in tickers_before]
    beta_before = float(np.mean(betas)) if betas else 1.0
    beta_after = float(np.mean(betas + [ticker_beta])) if betas else ticker_beta

    div_before = compute_diversification(scan_data)["score"]
    div_after = div_before + 2.0

    return {
        "ticker": ticker,
        "sector": ticker_sector,
        "sector_before": {k: round(v, 1) for k, v in sector_before.items()},
        "sector_after": {k: round(v, 1) for k, v in sector_after.items()},
        "diversification_before": div_before,
        "diversification_after": round(div_after, 1),
        "correlation_with_holdings": corr_with,
        "beta_before": round(beta_before, 3),
        "beta_after": round(beta_after, 3),
    }
```

- [ ] **Step 2: Add new endpoints to api.py**

Add these endpoints to `src/api.py`. Find the existing endpoint section and add after the last endpoint:

```python
from src.diversification import compute_diversification, compute_correlation, compute_whatif

@app.get("/snapshots/recent")
async def snapshots_recent(days: int = 7):
    """Return last N daily snapshots for sparkline/delta data."""
    snapshot_dir = Path(__file__).parent.parent / "data" / "daily_snapshots"
    if not snapshot_dir.exists():
        return []
    files = sorted(snapshot_dir.glob("*.json"), reverse=True)[:days]
    result = []
    for f in files:
        with open(f) as fh:
            data = json.load(fh)
        stocks = {}
        for s in data.get("top", []) + data.get("all_scores", []):
            stocks[s["ticker"]] = {
                "composite_score": s.get("composite_score", 0),
                "rank": s.get("rank", 999),
            }
        result.append({"date": f.stem, "stocks": stocks})
    return list(reversed(result))


@app.get("/portfolio/diversification")
async def portfolio_diversification():
    scan_path = Path(__file__).parent.parent / "data" / "scan_results.json"
    scan_data = {}
    if scan_path.exists():
        with open(scan_path) as f:
            scan_data = json.load(f)
    return compute_diversification(scan_data)


@app.get("/portfolio/correlation")
async def portfolio_correlation():
    scan_path = Path(__file__).parent.parent / "data" / "scan_results.json"
    scan_data = {}
    if scan_path.exists():
        with open(scan_path) as f:
            scan_data = json.load(f)
    return compute_correlation(scan_data)


@app.get("/portfolio/whatif")
async def portfolio_whatif(ticker: str):
    scan_path = Path(__file__).parent.parent / "data" / "scan_results.json"
    scan_data = {}
    if scan_path.exists():
        with open(scan_path) as f:
            scan_data = json.load(f)
    return compute_whatif(ticker, scan_data)
```

- [ ] **Step 3: Add Gemini synthesis to scan pipeline**

Add to `src/pipeline.py`, in the function that produces final results (after scoring is done, before writing `scan_results.json`). Find where `top` list is finalized and add:

```python
def _generate_synthesis(stock):
    """Generate a 2-3 sentence AI synthesis for a top-20 stock."""
    try:
        import google.generativeai as genai
        key = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY", "")
        if not key:
            return None
        genai.configure(api_key=key)
        model = genai.GenerativeModel("gemini-2.5-flash")

        data = {
            "ticker": stock["ticker"],
            "name": stock["name"],
            "sector": stock["sector"],
            "composite_score": stock["composite_score"],
            "fundamentals": stock["fundamentals_pct"],
            "valuation": stock["valuation_pct"],
            "technicals": stock["technicals_pct"],
            "risk": stock["risk_pct"],
            "growth": stock["growth_pct"],
            "entry_signal": stock["entry_signal"],
            "sell_signal": stock["sell_signal"],
            "rsi": stock["rsi"],
            "beta": stock["beta"],
            "current_price": stock["current_price"],
            "ma50": stock["ma50"],
            "ma200": stock["ma200"],
            "dcf_verdict": stock.get("dcf_verdict"),
            "dcf_margin_of_safety": stock.get("dcf_margin_of_safety"),
            "comps_verdict": stock.get("comps_verdict"),
            "ml_signal": stock.get("ml_signal"),
        }

        prompt = f"""You are a concise stock analyst. Given this data, write 2-3 sentences summarizing the investment case. Highlight strengths, weaknesses, and any conflicting signals. Be specific with numbers. Do not use bullet points.

{json.dumps(data, indent=2)}"""

        response = model.generate_content(prompt)
        return response.text.strip()
    except Exception:
        return None


# Add this call where top stocks are finalized, before writing scan_results.json:
# for stock in top_stocks:
#     stock["synthesis"] = _generate_synthesis(stock)
```

The exact insertion point depends on how `pipeline.py` is structured. Look for where `scan_results.json` is written and add the synthesis loop just before that write. Read `pipeline.py` to find the right location.

- [ ] **Step 4: Verify new endpoints work**

```bash
# Restart the API server, then test:
curl http://localhost:8000/snapshots/recent?days=3 | python3 -m json.tool | head -20
curl http://localhost:8000/portfolio/diversification | python3 -m json.tool
curl http://localhost:8000/portfolio/correlation | python3 -m json.tool
curl "http://localhost:8000/portfolio/whatif?ticker=AAPL" | python3 -m json.tool
```

Expected: Each returns valid JSON with the expected structure.

- [ ] **Step 5: Commit**

```bash
cd /Users/zhuorantang/clawd/stock-picker
git add src/diversification.py src/api.py src/pipeline.py
git commit -m "feat: add backend endpoints for snapshots, diversification, correlation, what-if, and Gemini synthesis"
```

---

## Task 6: Scanner Page with Enhanced Table

**Files:**
- Create: `frontend/src/components/scanner/ScannerTable.tsx`
- Create: `frontend/src/components/scanner/ScannerRow.tsx`
- Create: `frontend/src/components/scanner/SectorFilter.tsx`
- Create: `frontend/src/pages/Scanner.tsx`
- Modify: `frontend/src/App.tsx` — wire in Scanner page

- [ ] **Step 1: Build SectorFilter**

Create `frontend/src/components/scanner/SectorFilter.tsx`:

```tsx
interface SectorFilterProps {
  sectors: string[];
  active: string | null;
  onSelect: (sector: string | null) => void;
  signalFilter: string | null;
  onSignalChange: (signal: string | null) => void;
}

const SIGNALS = ["STRONG_BUY", "BUY", "HOLD", "WAIT"];

export default function SectorFilter({ sectors, active, onSelect, signalFilter, onSignalChange }: SectorFilterProps) {
  return (
    <div className="flex items-center gap-2 flex-wrap mb-4">
      <button
        onClick={() => onSelect(null)}
        className={`px-3.5 py-1.5 rounded-full text-xs font-semibold transition-colors ${
          !active ? "bg-accent text-white" : "bg-surface text-text-secondary border border-border hover:text-text-primary"
        }`}
      >
        All Sectors
      </button>
      {sectors.map((s) => (
        <button
          key={s}
          onClick={() => onSelect(s === active ? null : s)}
          className={`px-3.5 py-1.5 rounded-full text-xs font-semibold transition-colors ${
            s === active ? "bg-accent text-white" : "bg-surface text-text-secondary border border-border hover:text-text-primary"
          }`}
        >
          {s}
        </button>
      ))}
      <div className="flex-1" />
      <select
        value={signalFilter ?? ""}
        onChange={(e) => onSignalChange(e.target.value || null)}
        className="px-3 py-1.5 rounded-md bg-surface border border-border text-xs text-text-secondary"
      >
        <option value="">Signal: All</option>
        {SIGNALS.map((s) => (
          <option key={s} value={s}>{s}</option>
        ))}
      </select>
    </div>
  );
}
```

- [ ] **Step 2: Build ScannerRow**

Create `frontend/src/components/scanner/ScannerRow.tsx`:

```tsx
import { motion } from "framer-motion";
import type { Stock } from "../../lib/types";
import RadarChart from "../common/RadarChart";
import ScoreBadge from "../common/ScoreBadge";
import SparklineBar from "../common/SparklineBar";
import { scoreColor, pnlColor } from "../../lib/colors";

interface ScannerRowProps {
  stock: Stock;
  rank: number;
  sparkline: number[];
  scoreDelta: number | null;
  onClick: () => void;
}

export default function ScannerRow({ stock, rank, sparkline, scoreDelta, onClick }: ScannerRowProps) {
  const scores = {
    fund: stock.fundamentals_pct,
    val: stock.valuation_pct,
    tech: stock.technicals_pct,
    risk: stock.risk_pct,
    grow: stock.growth_pct,
  };

  const deltaStr = scoreDelta !== null && scoreDelta !== 0
    ? scoreDelta > 0 ? `▲${scoreDelta}` : `▼${Math.abs(scoreDelta)}`
    : "—";
  const deltaColor = scoreDelta !== null && scoreDelta > 0
    ? "text-positive" : scoreDelta !== null && scoreDelta < 0
    ? "text-danger" : "text-text-secondary";

  return (
    <motion.tr
      onClick={onClick}
      className="border-t border-surface cursor-pointer transition-colors hover:bg-accent/5"
      whileHover={{ y: -1 }}
    >
      <td className="py-2.5 px-3 font-bold text-text-primary">{rank}</td>
      <td className="py-2.5 px-3">
        <div className="font-bold text-text-primary">{stock.ticker}</div>
        <div className="text-[11px] text-text-muted">{stock.name}</div>
      </td>
      <td className="py-2.5 px-3">
        <RadarChart scores={scores} size={72} showLabels={true} />
      </td>
      <td className="py-2.5 px-3">
        <span className={`text-lg font-bold ${scoreColor(stock.composite_score)}`}>
          {Math.round(stock.composite_score)}
        </span>
        <span className={`text-[11px] ml-1 ${deltaColor}`}>{deltaStr}</span>
      </td>
      <td className="py-2.5 px-3 w-44">
        <SparklineBar values={sparkline} />
      </td>
      <td className="py-2.5 px-3">
        <ScoreBadge signal={stock.entry_signal} />
      </td>
      <td className="py-2.5 px-3 font-semibold text-text-primary">${stock.current_price.toFixed(2)}</td>
      <td className="py-2.5 px-3">
        {stock.ma50 > 0 && (
          <span className={`font-semibold ${pnlColor(stock.current_price - stock.ma50)}`}>
            {((stock.current_price / stock.ma50 - 1) * 100).toFixed(1)}%
          </span>
        )}
      </td>
      <td className="py-2.5 px-3">
        {stock.consecutive_days > 0 ? (
          <span className="text-xs text-text-secondary">🔥 {stock.consecutive_days}d</span>
        ) : (
          <span className="text-xs text-text-secondary">—</span>
        )}
      </td>
    </motion.tr>
  );
}
```

- [ ] **Step 3: Build ScannerTable**

Create `frontend/src/components/scanner/ScannerTable.tsx`:

```tsx
import { useState, useMemo } from "react";
import type { Stock, SnapshotDay } from "../../lib/types";
import ScannerRow from "./ScannerRow";
import SectorFilter from "./SectorFilter";

interface ScannerTableProps {
  stocks: Stock[];
  snapshots: SnapshotDay[];
  onSelectStock: (stock: Stock) => void;
}

export default function ScannerTable({ stocks, snapshots, onSelectStock }: ScannerTableProps) {
  const [sectorFilter, setSectorFilter] = useState<string | null>(null);
  const [signalFilter, setSignalFilter] = useState<string | null>(null);
  const [sortCol, setSortCol] = useState<string>("composite_score");
  const [sortAsc, setSortAsc] = useState(false);

  const sectors = useMemo(() => {
    const s = new Set(stocks.map((st) => st.sector));
    return Array.from(s).sort();
  }, [stocks]);

  const filtered = useMemo(() => {
    let result = stocks;
    if (sectorFilter) result = result.filter((s) => s.sector === sectorFilter);
    if (signalFilter) result = result.filter((s) => s.entry_signal === signalFilter);
    result = [...result].sort((a, b) => {
      const av = (a as Record<string, unknown>)[sortCol] as number;
      const bv = (b as Record<string, unknown>)[sortCol] as number;
      return sortAsc ? av - bv : bv - av;
    });
    return result;
  }, [stocks, sectorFilter, signalFilter, sortCol, sortAsc]);

  function getSparkline(ticker: string): number[] {
    return snapshots.map((snap) => snap.stocks[ticker]?.composite_score ?? 0);
  }

  function getScoreDelta(ticker: string): number | null {
    if (snapshots.length < 2) return null;
    const prev = snapshots[snapshots.length - 2]?.stocks[ticker]?.composite_score;
    const curr = snapshots[snapshots.length - 1]?.stocks[ticker]?.composite_score;
    if (prev == null || curr == null) return null;
    return Math.round(curr - prev);
  }

  function toggleSort(col: string) {
    if (sortCol === col) setSortAsc(!sortAsc);
    else { setSortCol(col); setSortAsc(false); }
  }

  const TH = ({ col, children }: { col: string; children: React.ReactNode }) => (
    <th
      onClick={() => toggleSort(col)}
      className="py-2.5 px-3 text-left text-[11px] text-text-muted uppercase tracking-wider font-semibold cursor-pointer hover:text-text-primary"
    >
      {children} {sortCol === col ? (sortAsc ? "↑" : "↓") : ""}
    </th>
  );

  return (
    <div>
      <SectorFilter
        sectors={sectors}
        active={sectorFilter}
        onSelect={setSectorFilter}
        signalFilter={signalFilter}
        onSignalChange={setSignalFilter}
      />
      <div className="rounded-xl border border-border overflow-hidden">
        <table className="w-full">
          <thead className="bg-surface">
            <tr>
              <TH col="rank">#</TH>
              <TH col="ticker">Ticker</TH>
              <th className="py-2.5 px-3 text-left text-[11px] text-text-muted uppercase tracking-wider font-semibold">
                Profile
              </th>
              <TH col="composite_score">Score</TH>
              <th className="py-2.5 px-3 text-left text-[11px] text-text-muted uppercase tracking-wider font-semibold">
                7d Trend
              </th>
              <TH col="entry_signal">Signal</TH>
              <TH col="current_price">Price</TH>
              <th className="py-2.5 px-3 text-left text-[11px] text-text-muted uppercase tracking-wider font-semibold">
                vs MA50
              </th>
              <TH col="consecutive_days">Streak</TH>
            </tr>
          </thead>
          <tbody>
            {filtered.map((stock, i) => (
              <ScannerRow
                key={stock.ticker}
                stock={stock}
                rank={i + 1}
                sparkline={getSparkline(stock.ticker)}
                scoreDelta={getScoreDelta(stock.ticker)}
                onClick={() => onSelectStock(stock)}
              />
            ))}
          </tbody>
        </table>
        <div className="py-2.5 px-3 text-center text-xs text-text-muted border-t border-border">
          Showing {filtered.length} of {stocks.length} stocks
        </div>
      </div>
    </div>
  );
}
```

- [ ] **Step 4: Build Scanner page**

Create `frontend/src/pages/Scanner.tsx`:

```tsx
import { useState } from "react";
import { useScan } from "../App";
import { useApi } from "../hooks/useApi";
import { api } from "../lib/api";
import ScannerTable from "../components/scanner/ScannerTable";
import type { Stock, SnapshotDay } from "../lib/types";

export default function Scanner() {
  const { scan, loading: scanLoading } = useScan();
  const { data: snapshots } = useApi<SnapshotDay[]>(() => api.snapshotsRecent(7));
  const [selectedStock, setSelectedStock] = useState<Stock | null>(null);

  if (scanLoading) {
    return <div className="text-text-secondary">Loading scan data...</div>;
  }

  if (!scan) {
    return <div className="text-text-secondary">No scan data available. Run a scan first.</div>;
  }

  const allStocks = [...scan.top, ...scan.all_scores.filter(
    (s) => !scan.top.some((t) => t.ticker === s.ticker)
  )].sort((a, b) => b.composite_score - a.composite_score);

  return (
    <div>
      <div className="flex items-center justify-between mb-4">
        <h1 className="text-xl font-bold">Scanner</h1>
        <span className="text-xs text-text-muted">{scan.stocks_analyzed} stocks analyzed</span>
      </div>
      <ScannerTable
        stocks={allStocks}
        snapshots={snapshots ?? []}
        onSelectStock={setSelectedStock}
      />
      {/* TickerModal will be added in Task 7 */}
    </div>
  );
}
```

- [ ] **Step 5: Wire Scanner into App.tsx**

In `frontend/src/App.tsx`, replace the Scanner placeholder route:

```tsx
import Scanner from "./pages/Scanner";

// In the Routes:
<Route path="/scanner" element={<Scanner />} />
```

- [ ] **Step 6: Verify scanner renders**

```bash
cd /Users/zhuorantang/clawd/stock-picker/frontend
npm run dev
```

Navigate to http://localhost:5173/scanner. Expected: Table with radar charts, sparklines, signal badges, sector filter pills. Click sorting on column headers. Sector pills filter the table.

- [ ] **Step 7: Commit**

```bash
cd /Users/zhuorantang/clawd/stock-picker
git add frontend/src/components/scanner/ frontend/src/pages/Scanner.tsx frontend/src/App.tsx
git commit -m "feat: add scanner page with enhanced table, radar charts, sparklines, and filters"
```

---

## Task 7: Ticker Detail Modal

**Files:**
- Create: `frontend/src/components/ticker/TickerModal.tsx`
- Create: `frontend/src/components/ticker/SynthesisBanner.tsx`
- Create: `frontend/src/components/ticker/KeyMetrics.tsx`
- Create: `frontend/src/components/ticker/EntryTiming.tsx`
- Create: `frontend/src/components/ticker/DCFTab.tsx`
- Create: `frontend/src/components/ticker/CompsTab.tsx`
- Create: `frontend/src/components/ticker/EarningsTab.tsx`
- Create: `frontend/src/components/ticker/MomentumTab.tsx`
- Create: `frontend/src/components/ticker/DevilTab.tsx`
- Modify: `frontend/src/pages/Scanner.tsx` — integrate modal

- [ ] **Step 1: Build SynthesisBanner**

Create `frontend/src/components/ticker/SynthesisBanner.tsx`:

```tsx
interface SynthesisBannerProps {
  text: string | undefined;
}

export default function SynthesisBanner({ text }: SynthesisBannerProps) {
  if (!text) return null;

  return (
    <div className="mx-6 my-4 p-4 rounded-xl bg-gradient-to-br from-positive/5 to-accent/5 border border-positive/20">
      <div className="text-[11px] uppercase tracking-wider text-positive font-bold mb-1.5">
        AI Synthesis
      </div>
      <div className="text-[13px] text-text-primary leading-relaxed">{text}</div>
    </div>
  );
}
```

- [ ] **Step 2: Build KeyMetrics**

Create `frontend/src/components/ticker/KeyMetrics.tsx`:

```tsx
import type { Stock } from "../../lib/types";
import MetricCard from "../common/MetricCard";
import { scoreColor, pnlColor } from "../../lib/colors";

interface KeyMetricsProps {
  stock: Stock;
}

export default function KeyMetrics({ stock }: KeyMetricsProps) {
  const rsiColor = stock.rsi > 70 ? "text-danger" : stock.rsi < 30 ? "text-positive" : "text-text-primary";
  const mlColor = stock.ml_signal === "outperform" ? "text-positive" : "text-text-secondary";

  return (
    <div className="grid grid-cols-3 gap-2.5">
      <MetricCard label="RSI (14)" value={stock.rsi.toFixed(1)} subtitle={stock.rsi > 70 ? "Overbought" : stock.rsi < 30 ? "Oversold" : "Neutral"} valueColor={rsiColor} />
      <MetricCard label="P/E Ratio" value={stock.valuation_pct > 0 ? stock.valuation_pct.toFixed(0) : "N/A"} subtitle={`Valuation score: ${stock.valuation_pct.toFixed(0)}`} />
      <MetricCard label="ML Confidence" value={stock.ml_score != null ? stock.ml_score.toFixed(2) : "N/A"} subtitle={stock.ml_signal ?? "No prediction"} valueColor={mlColor} />
      <MetricCard label="Growth Score" value={stock.growth_pct.toFixed(0)} subtitle="Percentile rank" valueColor={scoreColor(stock.growth_pct)} />
      <MetricCard label="Support (MA50)" value={`$${stock.ma50.toFixed(2)}`} subtitle={`${((stock.current_price / stock.ma50 - 1) * 100).toFixed(1)}% ${stock.above_ma50 ? "above" : "below"}`} />
      <MetricCard
        label="Analyst Target"
        value={stock.sentiment.pt_upside_pct > 0 ? `+${(stock.sentiment.pt_upside_pct * 100).toFixed(1)}%` : "N/A"}
        subtitle={`${stock.sentiment.analyst_count} analysts · ${stock.sentiment.recommendation}`}
        valueColor={stock.sentiment.pt_upside_pct > 0.1 ? "text-positive" : "text-text-secondary"}
      />
    </div>
  );
}
```

- [ ] **Step 3: Build EntryTiming tab**

Create `frontend/src/components/ticker/EntryTiming.tsx`:

```tsx
import { useApi } from "../../hooks/useApi";
import { api } from "../../lib/api";
import type { EntryTiming as EntryTimingType } from "../../lib/types";
import { scoreColor } from "../../lib/colors";

interface EntryTimingProps {
  ticker: string;
}

export default function EntryTiming({ ticker }: EntryTimingProps) {
  const { data, loading } = useApi<EntryTimingType>(() => api.entry(ticker), [ticker]);

  if (loading) return <div className="p-4 text-text-secondary text-sm">Loading entry timing...</div>;
  if (!data) return <div className="p-4 text-text-secondary text-sm">Entry timing unavailable</div>;

  return (
    <div className="p-4 grid grid-cols-3 gap-4">
      <div>
        <div className="text-[11px] text-text-muted uppercase tracking-wider mb-2">Entry Score</div>
        <div className="flex items-baseline gap-1.5">
          <span className={`text-3xl font-extrabold ${scoreColor(data.timing_score)}`}>
            {(data.timing_score / 10).toFixed(1)}
          </span>
          <span className="text-sm text-text-secondary">/ 10</span>
        </div>
        <div className="mt-2 h-1.5 rounded-full bg-border overflow-hidden">
          <div
            className="h-full rounded-full bg-gradient-to-r from-positive to-accent"
            style={{ width: `${data.timing_score}%` }}
          />
        </div>
        <div className={`text-xs mt-1.5 ${scoreColor(data.timing_score)}`}>
          {data.recommendation}
        </div>
      </div>

      <div>
        <div className="text-[11px] text-text-muted uppercase tracking-wider mb-2">Key Levels</div>
        <div className="flex flex-col gap-1.5">
          {data.resistance_levels[0] && (
            <div className="flex justify-between text-[13px]">
              <span className="text-text-secondary">Resistance</span>
              <span className="text-danger font-semibold">${data.resistance_levels[0].toFixed(2)}</span>
            </div>
          )}
          {data.support_levels[0] && (
            <div className="flex justify-between text-[13px]">
              <span className="text-text-secondary">Support</span>
              <span className="text-positive font-semibold">${data.support_levels[0].toFixed(2)}</span>
            </div>
          )}
          <div className="flex justify-between text-[13px]">
            <span className="text-text-secondary">RSI</span>
            <span className="text-text-primary font-semibold">{data.rsi.toFixed(1)}</span>
          </div>
          <div className="flex justify-between text-[13px]">
            <span className="text-text-secondary">Volume</span>
            <span className="text-text-primary font-semibold">{data.volume_signal}</span>
          </div>
        </div>
      </div>

      <div>
        <div className="text-[11px] text-text-muted uppercase tracking-wider mb-2">Signals</div>
        <div className="flex flex-wrap gap-1.5">
          <span className="px-2.5 py-1 rounded-full bg-positive/10 border border-positive/20 text-positive text-[11px]">
            RSI: {data.rsi_signal}
          </span>
          <span className="px-2.5 py-1 rounded-full bg-accent/10 border border-accent/20 text-accent text-[11px]">
            MA dist: {data.ma_distance_pct.toFixed(1)}%
          </span>
        </div>
      </div>
    </div>
  );
}
```

- [ ] **Step 4: Build remaining deep-dive tabs**

Create `frontend/src/components/ticker/DCFTab.tsx`:

```tsx
import { useApi } from "../../hooks/useApi";
import { api } from "../../lib/api";

export default function DCFTab({ ticker }: { ticker: string }) {
  const { data, loading } = useApi(() => api.dcf(ticker), [ticker]);

  if (loading) return <div className="p-4 text-text-secondary text-sm">Loading DCF...</div>;
  if (!data) return <div className="p-4 text-text-secondary text-sm">DCF data unavailable</div>;

  return (
    <div className="p-4">
      <pre className="text-xs text-text-secondary whitespace-pre-wrap">
        {JSON.stringify(data, null, 2)}
      </pre>
    </div>
  );
}
```

Create `frontend/src/components/ticker/CompsTab.tsx`:

```tsx
import { useApi } from "../../hooks/useApi";
import { api } from "../../lib/api";

export default function CompsTab({ ticker }: { ticker: string }) {
  const { data, loading } = useApi(() => api.comps(ticker), [ticker]);

  if (loading) return <div className="p-4 text-text-secondary text-sm">Loading comps...</div>;
  if (!data) return <div className="p-4 text-text-secondary text-sm">Comps data unavailable</div>;

  return (
    <div className="p-4">
      <pre className="text-xs text-text-secondary whitespace-pre-wrap">
        {JSON.stringify(data, null, 2)}
      </pre>
    </div>
  );
}
```

Create `frontend/src/components/ticker/EarningsTab.tsx`:

```tsx
import { useApi } from "../../hooks/useApi";
import { api } from "../../lib/api";

export default function EarningsTab({ ticker }: { ticker: string }) {
  const { data, loading } = useApi(() => api.earnings(ticker), [ticker]);

  if (loading) return <div className="p-4 text-text-secondary text-sm">Loading earnings...</div>;
  if (!data) return <div className="p-4 text-text-secondary text-sm">Earnings data unavailable</div>;

  return (
    <div className="p-4">
      <pre className="text-xs text-text-secondary whitespace-pre-wrap">
        {JSON.stringify(data, null, 2)}
      </pre>
    </div>
  );
}
```

Create `frontend/src/components/ticker/MomentumTab.tsx`:

```tsx
import { useApi } from "../../hooks/useApi";
import { api } from "../../lib/api";

export default function MomentumTab({ ticker }: { ticker: string }) {
  const { data, loading } = useApi(() => api.momentum(ticker), [ticker]);

  if (loading) return <div className="p-4 text-text-secondary text-sm">Loading momentum...</div>;
  if (!data) return <div className="p-4 text-text-secondary text-sm">Momentum data unavailable</div>;

  return (
    <div className="p-4">
      <pre className="text-xs text-text-secondary whitespace-pre-wrap">
        {JSON.stringify(data, null, 2)}
      </pre>
    </div>
  );
}
```

Create `frontend/src/components/ticker/DevilTab.tsx`:

```tsx
import { useApi } from "../../hooks/useApi";
import { api } from "../../lib/api";
import type { DevilsAdvocate } from "../../lib/types";

export default function DevilTab({ ticker }: { ticker: string }) {
  const { data, loading } = useApi<DevilsAdvocate>(() => api.devil(ticker), [ticker]);

  if (loading) return <div className="p-4 text-text-secondary text-sm">Loading risk review...</div>;
  if (!data) return <div className="p-4 text-text-secondary text-sm">Risk review unavailable</div>;

  return (
    <div className="p-4">
      <div className="flex gap-2 mb-3">
        <span className="px-2 py-0.5 rounded text-xs font-bold bg-danger/15 text-danger">
          Risk: {data.risk_score}/10
        </span>
        <span className="px-2 py-0.5 rounded text-xs bg-danger/15 text-danger">
          {data.quant_flags.red_count} red flags
        </span>
        <span className="px-2 py-0.5 rounded text-xs bg-positive/15 text-positive">
          {data.quant_flags.green_count} green flags
        </span>
      </div>
      <div className="text-sm text-text-primary whitespace-pre-wrap leading-relaxed">
        {data.review_text}
      </div>
    </div>
  );
}
```

- [ ] **Step 5: Build TickerModal**

Create `frontend/src/components/ticker/TickerModal.tsx`:

```tsx
import { useState, lazy, Suspense } from "react";
import { motion, AnimatePresence } from "framer-motion";
import type { Stock } from "../../lib/types";
import RadarChart from "../common/RadarChart";
import ScoreBadge from "../common/ScoreBadge";
import SynthesisBanner from "./SynthesisBanner";
import KeyMetrics from "./KeyMetrics";
import { scoreColor, pnlColor } from "../../lib/colors";

import EntryTiming from "./EntryTiming";
import DCFTab from "./DCFTab";
import CompsTab from "./CompsTab";
import EarningsTab from "./EarningsTab";
import MomentumTab from "./MomentumTab";
import DevilTab from "./DevilTab";

const TABS = ["Entry Timing", "DCF Valuation", "Peer Comps", "Earnings", "Momentum", "Devil's Advocate"] as const;

interface TickerModalProps {
  stock: Stock;
  onClose: () => void;
}

export default function TickerModal({ stock, onClose }: TickerModalProps) {
  const [activeTab, setActiveTab] = useState<typeof TABS[number]>("Entry Timing");

  const scores = {
    fund: stock.fundamentals_pct,
    val: stock.valuation_pct,
    tech: stock.technicals_pct,
    risk: stock.risk_pct,
    grow: stock.growth_pct,
  };

  function renderTab() {
    switch (activeTab) {
      case "Entry Timing": return <EntryTiming ticker={stock.ticker} />;
      case "DCF Valuation": return <DCFTab ticker={stock.ticker} />;
      case "Peer Comps": return <CompsTab ticker={stock.ticker} />;
      case "Earnings": return <EarningsTab ticker={stock.ticker} />;
      case "Momentum": return <MomentumTab ticker={stock.ticker} />;
      case "Devil's Advocate": return <DevilTab ticker={stock.ticker} />;
    }
  }

  return (
    <AnimatePresence>
      <motion.div
        className="fixed inset-0 bg-black/60 z-50 flex items-start justify-center pt-8 overflow-auto"
        onClick={onClose}
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        exit={{ opacity: 0 }}
      >
        <motion.div
          className="bg-base border border-border rounded-2xl w-full max-w-4xl mb-8 overflow-hidden"
          onClick={(e) => e.stopPropagation()}
          initial={{ scale: 0.95, opacity: 0 }}
          animate={{ scale: 1, opacity: 1 }}
          exit={{ scale: 0.95, opacity: 0 }}
        >
          {/* Header */}
          <div className="flex justify-between items-start p-5 border-b border-surface">
            <div>
              <div className="flex items-center gap-3 mb-1">
                <span className="text-2xl font-bold text-text-primary">{stock.ticker}</span>
                <ScoreBadge signal={stock.entry_signal} />
                {stock.consecutive_days > 0 && (
                  <span className="px-2.5 py-1 rounded-md bg-caution/15 text-caution text-xs font-semibold">
                    🔥 {stock.consecutive_days}d streak
                  </span>
                )}
              </div>
              <div className="text-sm text-text-secondary">{stock.name} · {stock.sector}</div>
            </div>
            <div className="text-right">
              <div className="text-2xl font-bold text-text-primary">${stock.current_price.toFixed(2)}</div>
              <button onClick={onClose} className="text-text-muted hover:text-text-primary text-xs mt-1">
                ✕ Close
              </button>
            </div>
          </div>

          {/* Synthesis */}
          <SynthesisBanner text={stock.synthesis} />

          {/* Radar + Metrics */}
          <div className="grid grid-cols-[220px_1fr] gap-4 px-6 pb-4">
            <div className="p-4 rounded-xl bg-surface border border-border flex flex-col items-center">
              <div className="text-[11px] text-text-muted uppercase tracking-wider font-semibold mb-2">Score Profile</div>
              <RadarChart scores={scores} size={170} showLabels={true} />
              <div className={`mt-1 text-3xl font-extrabold ${scoreColor(stock.composite_score)}`}>
                {Math.round(stock.composite_score)}
              </div>
              <div className="text-[11px] text-text-secondary">Overall Score</div>
            </div>
            <KeyMetrics stock={stock} />
          </div>

          {/* Tabs */}
          <div className="px-6 pb-5">
            <div className="flex gap-0.5 mb-4 bg-surface rounded-lg p-1">
              {TABS.map((tab) => (
                <button
                  key={tab}
                  onClick={() => setActiveTab(tab)}
                  className={`px-4 py-2 rounded-md text-xs font-semibold transition-colors ${
                    activeTab === tab
                      ? "bg-accent text-white"
                      : "text-text-secondary hover:text-text-primary"
                  }`}
                >
                  {tab}
                </button>
              ))}
            </div>
            <div className="rounded-xl bg-surface border border-border overflow-hidden">
              {renderTab()}
            </div>
          </div>
        </motion.div>
      </motion.div>
    </AnimatePresence>
  );
}
```

- [ ] **Step 6: Wire modal into Scanner page**

Update `frontend/src/pages/Scanner.tsx` — add the modal:

```tsx
import TickerModal from "../components/ticker/TickerModal";

// At the end of the return, after </ScannerTable>:
{selectedStock && (
  <TickerModal stock={selectedStock} onClose={() => setSelectedStock(null)} />
)}
```

- [ ] **Step 7: Verify modal works**

Navigate to http://localhost:5173/scanner, click a stock row. Expected: Modal opens with animation, shows ticker header, synthesis (if available), radar chart, key metrics, and tabbed deep dive. Clicking tabs loads data lazily. Clicking outside or ✕ closes.

- [ ] **Step 8: Commit**

```bash
cd /Users/zhuorantang/clawd/stock-picker
git add frontend/src/components/ticker/ frontend/src/pages/Scanner.tsx
git commit -m "feat: add ticker detail modal with synthesis, radar chart, key metrics, and deep dive tabs"
```

---

## Task 8: Home Dashboard

**Files:**
- Create: `frontend/src/components/home/SummaryCards.tsx`
- Create: `frontend/src/components/home/ActionItems.tsx`
- Create: `frontend/src/components/home/NewSignals.tsx`
- Create: `frontend/src/components/home/MarketPulse.tsx`
- Create: `frontend/src/pages/Home.tsx`
- Modify: `frontend/src/App.tsx` — wire in Home page

- [ ] **Step 1: Build SummaryCards**

Create `frontend/src/components/home/SummaryCards.tsx`:

```tsx
import type { ScanResult, AlertsResponse, AccuracyResponse, RiskSummary } from "../../lib/types";
import { pnlColor } from "../../lib/colors";

interface SummaryCardsProps {
  scan: ScanResult;
  alerts: AlertsResponse | null;
  accuracy: AccuracyResponse | null;
  risk: RiskSummary | null;
}

export default function SummaryCards({ scan, alerts, accuracy, risk }: SummaryCardsProps) {
  const newSignals = scan.top.filter((s) => s.entry_signal === "STRONG_BUY" || s.entry_signal === "BUY").length;
  const sellSignals = scan.top.filter((s) => s.sell_signal === "SELL" || s.sell_signal === "STRONG_SELL").length;

  return (
    <div className="grid grid-cols-4 gap-3 mb-5">
      <div className="p-3.5 rounded-xl bg-surface border border-border">
        <div className="text-[11px] text-text-muted uppercase tracking-wider">Portfolio Value</div>
        <div className="text-2xl font-bold text-text-primary mt-1">
          {risk ? `$${risk.total_portfolio_value.toLocaleString()}` : "—"}
        </div>
        {risk && (
          <div className={`text-[13px] ${pnlColor(risk.total_pnl)}`}>
            {risk.total_pnl >= 0 ? "+" : ""}${risk.total_pnl.toLocaleString()} ({risk.total_pnl_pct.toFixed(2)}%)
          </div>
        )}
      </div>

      <div className="p-3.5 rounded-xl bg-surface border border-border">
        <div className="text-[11px] text-text-muted uppercase tracking-wider">New Signals</div>
        <div className="text-2xl font-bold text-text-primary mt-1">{newSignals + sellSignals}</div>
        <div className="text-[13px] text-caution">{newSignals} buy · {sellSignals} sell</div>
      </div>

      <div className="p-3.5 rounded-xl bg-surface border border-border">
        <div className="text-[11px] text-text-muted uppercase tracking-wider">Alerts</div>
        <div className="text-2xl font-bold text-text-primary mt-1">{alerts?.current.length ?? 0}</div>
        <div className="text-[13px] text-text-secondary truncate">
          {alerts?.current[0]?.message ?? "No active alerts"}
        </div>
      </div>

      <div className="p-3.5 rounded-xl bg-surface border border-border">
        <div className="text-[11px] text-text-muted uppercase tracking-wider">Win Rate</div>
        <div className="text-2xl font-bold text-text-primary mt-1">
          {accuracy ? `${accuracy.accuracy_pct.toFixed(1)}%` : "—"}
        </div>
        <div className="text-[13px] text-text-secondary">
          {accuracy ? `${accuracy.correct}/${accuracy.total_predictions} picks` : ""}
        </div>
      </div>
    </div>
  );
}
```

- [ ] **Step 2: Build ActionItems**

Create `frontend/src/components/home/ActionItems.tsx`:

```tsx
import type { StopLossAlert, ProfitTarget, Stock } from "../../lib/types";
import ActionBadge from "../common/ActionBadge";

interface ActionItem {
  ticker: string;
  priority: "urgent" | "review" | "watch";
  title: string;
  subtitle: string;
}

interface ActionItemsProps {
  stopLosses: StopLossAlert[];
  profitTargets: ProfitTarget[];
  earningsNear: Stock[];
}

export default function ActionItems({ stopLosses, profitTargets, earningsNear }: ActionItemsProps) {
  const items: ActionItem[] = [];

  for (const sl of stopLosses) {
    if (sl.loss_pct < -10) {
      items.push({
        ticker: sl.ticker,
        priority: "urgent",
        title: `${Math.abs(sl.loss_pct).toFixed(1)}% loss — ${sl.status === "triggered" ? "stop triggered" : "near stop"}`,
        subtitle: `Current: $${sl.current_price.toFixed(2)} · Entry: $${sl.entry_price.toFixed(2)}`,
      });
    }
  }

  for (const pt of profitTargets) {
    const triggered = pt.profit_taking_levels.filter((l) => l.triggered);
    if (triggered.length > 0) {
      items.push({
        ticker: pt.ticker,
        priority: "review",
        title: `Profit target hit (+${pt.gain_pct.toFixed(1)}%)`,
        subtitle: `${triggered.length} tier${triggered.length > 1 ? "s" : ""} triggered`,
      });
    }
  }

  for (const stock of earningsNear) {
    items.push({
      ticker: stock.ticker,
      priority: "watch",
      title: "Earnings approaching",
      subtitle: stock.sell_reasons.find((r) => r.toLowerCase().includes("earn")) ?? "Check earnings date",
    });
  }

  if (items.length === 0) {
    return (
      <div className="rounded-xl bg-surface border border-border p-4 text-sm text-text-secondary">
        No action items today
      </div>
    );
  }

  return (
    <div className="rounded-xl bg-surface border border-border overflow-hidden">
      <div className="px-4 py-3 border-b border-border flex items-center gap-2">
        {items.some((i) => i.priority === "urgent") && (
          <div className="w-2 h-2 rounded-full bg-danger animate-pulse-dot" />
        )}
        <span className="text-xs font-bold text-text-primary uppercase tracking-wider">
          {items.length} Action{items.length > 1 ? "s" : ""} Needed
        </span>
      </div>
      {items.map((item, i) => (
        <div
          key={`${item.ticker}-${i}`}
          className="px-4 py-3 border-b border-border/50 last:border-0 flex items-center gap-3 hover:bg-accent/5 cursor-pointer transition-colors"
        >
          <ActionBadge priority={item.priority} />
          <div className="flex-1">
            <div className="text-[13px] text-text-primary font-semibold">{item.ticker} — {item.title}</div>
            <div className="text-xs text-text-secondary">{item.subtitle}</div>
          </div>
        </div>
      ))}
    </div>
  );
}
```

- [ ] **Step 3: Build NewSignals and MarketPulse**

Create `frontend/src/components/home/NewSignals.tsx`:

```tsx
import type { Stock } from "../../lib/types";
import ScoreBadge from "../common/ScoreBadge";

interface NewSignalsProps {
  stocks: Stock[];
}

export default function NewSignals({ stocks }: NewSignalsProps) {
  const notable = stocks.filter(
    (s) => s.entry_signal === "STRONG_BUY" || s.entry_signal === "BUY" || s.sell_signal === "SELL" || s.sell_signal === "STRONG_SELL"
  ).slice(0, 5);

  return (
    <div className="rounded-xl bg-surface border border-border overflow-hidden">
      <div className="px-4 py-3 border-b border-border text-xs font-bold text-text-primary uppercase tracking-wider">
        Top Signals
      </div>
      {notable.map((s) => (
        <div key={s.ticker} className="px-4 py-2.5 border-b border-border/50 last:border-0 flex justify-between items-center">
          <div>
            <span className="text-[13px] font-semibold text-text-primary">{s.ticker}</span>
            <span className="text-xs text-text-muted ml-1.5">{s.sector}</span>
          </div>
          <ScoreBadge signal={s.entry_signal} />
        </div>
      ))}
    </div>
  );
}
```

Create `frontend/src/components/home/MarketPulse.tsx`:

```tsx
import type { MarketRegime } from "../../lib/types";
import { pnlColor } from "../../lib/colors";

interface MarketPulseProps {
  regime: MarketRegime;
}

export default function MarketPulse({ regime }: MarketPulseProps) {
  const regimeColor = {
    bull: "text-positive",
    bear: "text-danger",
    sideways: "text-caution",
  }[regime.regime];

  return (
    <div className="rounded-xl bg-surface border border-border overflow-hidden">
      <div className="px-4 py-3 border-b border-border text-xs font-bold text-text-primary uppercase tracking-wider">
        Market Pulse
      </div>
      <div className="p-4 grid grid-cols-2 gap-2">
        <div>
          <div className="text-[11px] text-text-muted">SPY</div>
          <div className="text-sm font-semibold text-text-primary">${regime.spy_price.toFixed(2)}</div>
        </div>
        <div>
          <div className="text-[11px] text-text-muted">VIX</div>
          <div className={`text-sm font-semibold ${regime.macro.vix.current > regime.macro.vix.ma20 ? "text-danger" : "text-positive"}`}>
            {regime.macro.vix.current.toFixed(1)}
          </div>
        </div>
        <div>
          <div className="text-[11px] text-text-muted">10Y Rate</div>
          <div className="text-sm font-semibold text-caution">{regime.macro.us10y.current.toFixed(2)}%</div>
        </div>
        <div>
          <div className="text-[11px] text-text-muted">Regime</div>
          <div className={`text-sm font-semibold ${regimeColor}`}>
            {regime.regime.charAt(0).toUpperCase() + regime.regime.slice(1)}
          </div>
        </div>
      </div>
    </div>
  );
}
```

- [ ] **Step 4: Build Home page**

Create `frontend/src/pages/Home.tsx`:

```tsx
import { useScan } from "../App";
import { useApi } from "../hooks/useApi";
import { useTimeOfDay } from "../hooks/useTimeOfDay";
import { api } from "../lib/api";
import SummaryCards from "../components/home/SummaryCards";
import ActionItems from "../components/home/ActionItems";
import NewSignals from "../components/home/NewSignals";
import MarketPulse from "../components/home/MarketPulse";
import type { AlertsResponse, AccuracyResponse, RiskSummary, StopLossAlert, ProfitTarget } from "../lib/types";

const GREETING: Record<string, string> = {
  morning: "Good morning",
  midday: "Good afternoon",
  evening: "Good evening",
};

export default function Home() {
  const { scan, loading } = useScan();
  const tod = useTimeOfDay();
  const { data: alerts } = useApi<AlertsResponse>(() => api.alerts());
  const { data: accuracy } = useApi<AccuracyResponse>(() => api.accuracy());
  const { data: risk } = useApi<RiskSummary>(() => api.riskSummary());
  const { data: stopLosses } = useApi<{ alerts: StopLossAlert[] }>(() => api.stopLosses());

  if (loading || !scan) {
    return <div className="text-text-secondary">Loading...</div>;
  }

  return (
    <div>
      <div className="flex justify-between items-center mb-5">
        <div>
          <h1 className="text-xl font-bold text-text-primary">{GREETING[tod]}, Zhuoran</h1>
          <div className="text-[13px] text-text-secondary">
            {new Date().toLocaleDateString("en-US", { weekday: "short", month: "short", day: "numeric" })}
            {" · "}Last scan: {new Date(scan.timestamp).toLocaleTimeString()}
          </div>
        </div>
      </div>

      <SummaryCards scan={scan} alerts={alerts} accuracy={accuracy} risk={risk} />

      <div className="grid grid-cols-[1.2fr_1fr] gap-4">
        <ActionItems
          stopLosses={stopLosses?.alerts ?? []}
          profitTargets={[]}
          earningsNear={scan.top.filter((s) => s.sell_reasons.some((r) => r.toLowerCase().includes("earn")))}
        />
        <div className="flex flex-col gap-4">
          <NewSignals stocks={scan.top} />
          <MarketPulse regime={scan.market_regime} />
        </div>
      </div>
    </div>
  );
}
```

- [ ] **Step 5: Wire Home into App.tsx**

```tsx
import Home from "./pages/Home";

// In Routes:
<Route path="/" element={<Home />} />
```

- [ ] **Step 6: Verify home page**

Navigate to http://localhost:5173/. Expected: Greeting with time-of-day, 4 summary cards, action items on left, signals + market pulse on right.

- [ ] **Step 7: Commit**

```bash
cd /Users/zhuorantang/clawd/stock-picker
git add frontend/src/components/home/ frontend/src/pages/Home.tsx frontend/src/App.tsx
git commit -m "feat: add home dashboard with summary cards, action items, signals, and market pulse"
```

---

## Task 9: Portfolio Page

**Files:**
- Create: `frontend/src/components/portfolio/ActionBanner.tsx`
- Create: `frontend/src/components/portfolio/HoldingCard.tsx`
- Create: `frontend/src/components/portfolio/RiskDashboard.tsx`
- Create: `frontend/src/components/portfolio/DiversificationScore.tsx`
- Create: `frontend/src/components/portfolio/CorrelationHeatmap.tsx`
- Create: `frontend/src/components/portfolio/WhatIfSimulator.tsx`
- Create: `frontend/src/components/portfolio/RebalanceSuggestions.tsx`
- Create: `frontend/src/pages/Portfolio.tsx`
- Modify: `frontend/src/App.tsx` — wire in Portfolio page

- [ ] **Step 1: Build HoldingCard**

Create `frontend/src/components/portfolio/HoldingCard.tsx`:

```tsx
import { motion } from "framer-motion";
import ScoreBadge from "../common/ScoreBadge";
import { pnlColor } from "../../lib/colors";

interface Position {
  ticker: string;
  shares: number;
  entry_price: number;
  current_price: number;
  position_value: number;
  pnl: number;
  pnl_pct: number;
  risk_level: string;
}

interface HoldingCardProps {
  position: Position;
  signal?: string;
  stopLossPct?: number;
  profitTriggered?: boolean;
  totalValue: number;
}

export default function HoldingCard({ position, signal, stopLossPct, profitTriggered, totalValue }: HoldingCardProps) {
  const isNearStop = stopLossPct != null && position.pnl_pct < stopLossPct + 3;
  const borderClass = isNearStop
    ? "border-danger/30 hover:border-danger"
    : profitTriggered
    ? "border-caution/30 hover:border-caution"
    : "border-border hover:border-accent";

  const weight = totalValue > 0 ? (position.position_value / totalValue) * 100 : 0;

  return (
    <motion.div
      className={`p-3.5 rounded-xl bg-surface border ${borderClass} cursor-pointer transition-all duration-200`}
      whileHover={{ y: -1 }}
    >
      <div className="flex justify-between items-center mb-2">
        <div className="flex items-center gap-2.5">
          <span className="text-[15px] font-bold text-text-primary">{position.ticker}</span>
          {signal && <ScoreBadge signal={signal} />}
          {isNearStop && (
            <span className="px-2 py-0.5 rounded text-[10px] font-bold bg-danger/12 text-danger">NEAR STOP</span>
          )}
          {profitTriggered && (
            <span className="px-2 py-0.5 rounded text-[10px] font-bold bg-caution/12 text-caution">PROFIT T1</span>
          )}
        </div>
        <div className="text-right">
          <div className={`text-[15px] font-bold ${pnlColor(position.pnl)}`}>
            {position.pnl >= 0 ? "+" : ""}${position.pnl.toLocaleString()}
          </div>
          <div className={`text-[11px] ${pnlColor(position.pnl_pct)}`}>
            {position.pnl_pct >= 0 ? "+" : ""}{position.pnl_pct.toFixed(1)}%
          </div>
        </div>
      </div>
      <div className="flex justify-between text-xs text-text-secondary">
        <span>{position.shares} shares · Avg ${position.entry_price.toFixed(2)}</span>
        <span>${position.position_value.toLocaleString()} ({weight.toFixed(1)}%)</span>
      </div>
      <div className="mt-2 h-1 rounded-full bg-border overflow-hidden">
        <div
          className={`h-full rounded-full ${position.pnl >= 0 ? "bg-gradient-to-r from-positive to-accent" : "bg-danger"}`}
          style={{ width: `${Math.min(Math.max(50 + position.pnl_pct * 2, 5), 100)}%` }}
        />
      </div>
    </motion.div>
  );
}
```

- [ ] **Step 2: Build RiskDashboard**

Create `frontend/src/components/portfolio/RiskDashboard.tsx`:

```tsx
import type { RiskSummary, MarketRegime } from "../../lib/types";
import SectorBar from "../common/SectorBar";
import MetricCard from "../common/MetricCard";

interface RiskDashboardProps {
  risk: RiskSummary;
  sectorWeights: Record<string, number>;
  regime: MarketRegime;
}

export default function RiskDashboard({ risk, sectorWeights, regime }: RiskDashboardProps) {
  const sortedSectors = Object.entries(sectorWeights).sort(([, a], [, b]) => b - a);

  return (
    <div>
      <div className="text-xs font-semibold text-text-muted uppercase tracking-wider mb-2.5">Risk Dashboard</div>

      <div className="p-4 rounded-xl bg-surface border border-border mb-3">
        <div className="text-xs font-semibold text-text-primary mb-3">Sector Exposure</div>
        {sortedSectors.map(([sector, pct]) => (
          <SectorBar key={sector} label={sector} pct={pct} />
        ))}
      </div>

      <div className="grid grid-cols-2 gap-2 mb-3">
        <MetricCard label="Beta" value={risk.total_pnl_pct > 0 ? "1.0" : "—"} subtitle="Portfolio avg" />
        <MetricCard label="Positions" value={String(risk.positions.length)} subtitle="Active holdings" />
      </div>

      <div className="p-3 rounded-lg bg-accent/5 border border-accent/15">
        <div className="text-[10px] text-text-muted uppercase tracking-wider mb-1.5">Macro Flags</div>
        <div className="flex flex-wrap gap-1.5">
          <span className={`px-2 py-0.5 rounded-full text-[11px] border ${
            regime.regime === "bull" ? "bg-positive/10 border-positive/20 text-positive" : "bg-danger/10 border-danger/20 text-danger"
          }`}>
            {regime.regime} regime
          </span>
          {risk.concentration_warnings.map((w, i) => (
            <span key={i} className="px-2 py-0.5 rounded-full text-[11px] bg-caution/10 border border-caution/20 text-caution">
              {w}
            </span>
          ))}
        </div>
      </div>
    </div>
  );
}
```

- [ ] **Step 3: Build DiversificationScore**

Create `frontend/src/components/portfolio/DiversificationScore.tsx`:

```tsx
import type { DiversificationResponse } from "../../lib/types";
import { scoreHex } from "../../lib/colors";

interface DiversificationScoreProps {
  data: DiversificationResponse;
}

export default function DiversificationScore({ data }: DiversificationScoreProps) {
  const color = scoreHex(data.score);
  const circumference = 2 * Math.PI * 40;
  const offset = circumference * (1 - data.score / 100);

  return (
    <div className="p-4 rounded-xl bg-surface border border-border">
      <div className="text-xs font-semibold text-text-primary mb-3">Diversification Score</div>
      <div className="flex items-center gap-4">
        <svg width="100" height="100" viewBox="0 0 100 100">
          <circle cx="50" cy="50" r="40" fill="none" stroke="#334155" strokeWidth="6" />
          <circle
            cx="50" cy="50" r="40" fill="none" stroke={color} strokeWidth="6"
            strokeDasharray={circumference} strokeDashoffset={offset}
            strokeLinecap="round" transform="rotate(-90 50 50)"
          />
          <text x="50" y="50" textAnchor="middle" dominantBaseline="central" fill={color} fontSize="22" fontWeight="800">
            {Math.round(data.score)}
          </text>
        </svg>
        <div className="flex-1">
          {data.dragging_factors.map((f, i) => (
            <div key={i} className="text-xs text-text-secondary mb-1">• {f}</div>
          ))}
          {data.suggestions.map((s, i) => (
            <div key={i} className="text-xs text-caution mt-1">→ {s}</div>
          ))}
        </div>
      </div>
    </div>
  );
}
```

- [ ] **Step 4: Build CorrelationHeatmap**

Create `frontend/src/components/portfolio/CorrelationHeatmap.tsx`:

```tsx
import type { CorrelationResponse } from "../../lib/types";

interface CorrelationHeatmapProps {
  data: CorrelationResponse;
}

function corrColor(val: number): string {
  if (val > 0.7) return "#ef4444";
  if (val > 0.4) return "#f59e0b";
  if (val > 0.1) return "#6366f1";
  return "#3b82f6";
}

export default function CorrelationHeatmap({ data }: CorrelationHeatmapProps) {
  if (data.tickers.length < 2) {
    return (
      <div className="p-4 rounded-xl bg-surface border border-border text-sm text-text-secondary">
        Need at least 2 holdings for correlation analysis
      </div>
    );
  }

  const size = 36;

  return (
    <div className="p-4 rounded-xl bg-surface border border-border">
      <div className="text-xs font-semibold text-text-primary mb-3">Correlation Heatmap (90-day)</div>
      <div className="overflow-auto">
        <div className="inline-grid gap-0.5" style={{ gridTemplateColumns: `60px repeat(${data.tickers.length}, ${size}px)` }}>
          <div />
          {data.tickers.map((t) => (
            <div key={t} className="text-[10px] text-text-muted text-center font-semibold">{t}</div>
          ))}
          {data.tickers.map((rowTicker, i) => (
            <>
              <div key={`label-${rowTicker}`} className="text-[10px] text-text-muted font-semibold flex items-center">{rowTicker}</div>
              {data.matrix[i].map((val, j) => (
                <div
                  key={`${i}-${j}`}
                  className="rounded-sm flex items-center justify-center text-[9px] font-bold text-white/80"
                  style={{ width: size, height: size, backgroundColor: i === j ? "#334155" : corrColor(val) }}
                  title={`${rowTicker} × ${data.tickers[j]}: ${val.toFixed(3)}`}
                >
                  {i !== j ? val.toFixed(2) : "1.0"}
                </div>
              ))}
            </>
          ))}
        </div>
      </div>
    </div>
  );
}
```

- [ ] **Step 5: Build WhatIfSimulator**

Create `frontend/src/components/portfolio/WhatIfSimulator.tsx`:

```tsx
import { useState } from "react";
import { useApi } from "../../hooks/useApi";
import { api } from "../../lib/api";
import type { WhatIfResponse } from "../../lib/types";
import { pnlColor } from "../../lib/colors";

export default function WhatIfSimulator() {
  const [ticker, setTicker] = useState("");
  const [submitted, setSubmitted] = useState("");
  const { data, loading } = useApi<WhatIfResponse>(
    () => submitted ? api.whatIf(submitted) : Promise.resolve(null as unknown as WhatIfResponse),
    [submitted]
  );

  return (
    <div className="p-4 rounded-xl bg-surface border border-border">
      <div className="text-xs font-semibold text-text-primary mb-3">What If Simulator</div>
      <div className="flex gap-2 mb-3">
        <input
          value={ticker}
          onChange={(e) => setTicker(e.target.value.toUpperCase())}
          onKeyDown={(e) => e.key === "Enter" && setSubmitted(ticker)}
          placeholder="Enter ticker..."
          className="flex-1 px-3 py-1.5 rounded-md bg-base border border-border text-sm text-text-primary placeholder:text-text-muted"
        />
        <button
          onClick={() => setSubmitted(ticker)}
          className="px-4 py-1.5 rounded-md bg-accent text-white text-xs font-semibold"
        >
          Analyze
        </button>
      </div>
      {loading && <div className="text-xs text-text-secondary">Analyzing impact...</div>}
      {data && !loading && (
        <div className="space-y-2">
          <div className="flex justify-between text-xs">
            <span className="text-text-secondary">Sector</span>
            <span className="text-text-primary font-semibold">{data.sector}</span>
          </div>
          <div className="flex justify-between text-xs">
            <span className="text-text-secondary">Diversification</span>
            <span className={pnlColor(data.diversification_after - data.diversification_before)}>
              {data.diversification_before.toFixed(0)} → {data.diversification_after.toFixed(0)}
            </span>
          </div>
          <div className="flex justify-between text-xs">
            <span className="text-text-secondary">Beta</span>
            <span className="text-text-primary">{data.beta_before.toFixed(2)} → {data.beta_after.toFixed(2)}</span>
          </div>
          {Object.entries(data.correlation_with_holdings).length > 0 && (
            <div>
              <div className="text-[10px] text-text-muted uppercase mt-2 mb-1">Correlation with Holdings</div>
              {Object.entries(data.correlation_with_holdings).map(([t, c]) => (
                <div key={t} className="flex justify-between text-xs">
                  <span className="text-text-secondary">{t}</span>
                  <span className={c > 0.7 ? "text-danger" : c > 0.4 ? "text-caution" : "text-positive"}>{c.toFixed(3)}</span>
                </div>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
```

- [ ] **Step 6: Build RebalanceSuggestions**

Create `frontend/src/components/portfolio/RebalanceSuggestions.tsx`:

```tsx
import type { DiversificationResponse } from "../../lib/types";

interface RebalanceSuggestionsProps {
  data: DiversificationResponse;
}

export default function RebalanceSuggestions({ data }: RebalanceSuggestionsProps) {
  if (data.suggestions.length === 0) {
    return (
      <div className="p-4 rounded-xl bg-surface border border-border text-sm text-text-secondary">
        Portfolio is well balanced — no rebalance needed
      </div>
    );
  }

  return (
    <div className="p-4 rounded-xl bg-surface border border-border">
      <div className="text-xs font-semibold text-text-primary mb-3">Rebalance Suggestions</div>
      {data.suggestions.map((s, i) => (
        <div key={i} className="flex items-start gap-2 mb-2 last:mb-0">
          <span className="text-caution text-xs mt-0.5">→</span>
          <span className="text-xs text-text-secondary">{s}</span>
        </div>
      ))}
    </div>
  );
}
```

- [ ] **Step 7: Build Portfolio page**

Create `frontend/src/pages/Portfolio.tsx`:

```tsx
import { useScan } from "../App";
import { useApi } from "../hooks/useApi";
import { api } from "../lib/api";
import HoldingCard from "../components/portfolio/HoldingCard";
import RiskDashboard from "../components/portfolio/RiskDashboard";
import DiversificationScore from "../components/portfolio/DiversificationScore";
import CorrelationHeatmap from "../components/portfolio/CorrelationHeatmap";
import WhatIfSimulator from "../components/portfolio/WhatIfSimulator";
import RebalanceSuggestions from "../components/portfolio/RebalanceSuggestions";
import ActionBadge from "../components/common/ActionBadge";
import type { RiskSummary, DiversificationResponse, CorrelationResponse, StopLossAlert } from "../lib/types";
import { pnlColor } from "../lib/colors";

export default function Portfolio() {
  const { scan } = useScan();
  const { data: risk } = useApi<RiskSummary>(() => api.riskSummary());
  const { data: stopLosses } = useApi<{ alerts: StopLossAlert[] }>(() => api.stopLosses());
  const { data: diversification } = useApi<DiversificationResponse>(() => api.diversification());
  const { data: correlation } = useApi<CorrelationResponse>(() => api.correlation());

  if (!risk || !scan) return <div className="text-text-secondary">Loading portfolio...</div>;

  const sectorWeights: Record<string, number> = {};
  const tickerSignal: Record<string, string> = {};
  for (const s of [...scan.top, ...scan.all_scores]) {
    tickerSignal[s.ticker] = s.entry_signal;
  }
  for (const p of risk.positions) {
    const stock = [...scan.top, ...scan.all_scores].find((s) => s.ticker === p.ticker);
    const sector = stock?.sector ?? "Unknown";
    const weight = risk.total_portfolio_value > 0 ? (p.position_value / risk.total_portfolio_value) * 100 : 0;
    sectorWeights[sector] = (sectorWeights[sector] ?? 0) + weight;
  }

  const stopTickers = new Set((stopLosses?.alerts ?? []).filter((s) => s.loss_pct < -10).map((s) => s.ticker));

  return (
    <div>
      {/* Header */}
      <div className="flex items-end justify-between mb-5">
        <div>
          <div className="text-[13px] text-text-muted mb-1">Total Portfolio Value</div>
          <div className="flex items-baseline gap-3">
            <span className="text-4xl font-extrabold text-text-primary">
              ${risk.total_portfolio_value.toLocaleString()}
            </span>
            <span className={`text-base font-semibold ${pnlColor(risk.total_pnl)}`}>
              {risk.total_pnl >= 0 ? "+" : ""}${risk.total_pnl.toLocaleString()} ({risk.total_pnl_pct.toFixed(2)}%)
            </span>
          </div>
          <div className="text-[13px] text-text-secondary mt-1">
            {risk.positions.length} positions · {Object.keys(sectorWeights).length} sectors
          </div>
        </div>
      </div>

      {/* Main two-column layout */}
      <div className="grid grid-cols-[1.4fr_1fr] gap-4 mb-6">
        {/* Left: Holdings */}
        <div>
          <div className="text-xs font-semibold text-text-muted uppercase tracking-wider mb-2.5">Holdings</div>
          <div className="flex flex-col gap-2">
            {risk.positions.map((p) => (
              <HoldingCard
                key={p.ticker}
                position={p}
                signal={tickerSignal[p.ticker]}
                stopLossPct={-15}
                profitTriggered={false}
                totalValue={risk.total_portfolio_value}
              />
            ))}
          </div>
        </div>

        {/* Right: Risk */}
        <RiskDashboard risk={risk} sectorWeights={sectorWeights} regime={scan.market_regime} />
      </div>

      {/* Diversification section */}
      <div className="grid grid-cols-2 gap-4 mb-4">
        {diversification && <DiversificationScore data={diversification} />}
        {correlation && <CorrelationHeatmap data={correlation} />}
      </div>
      <div className="grid grid-cols-2 gap-4">
        <WhatIfSimulator />
        {diversification && <RebalanceSuggestions data={diversification} />}
      </div>
    </div>
  );
}
```

- [ ] **Step 8: Wire Portfolio into App.tsx**

```tsx
import Portfolio from "./pages/Portfolio";

// In Routes:
<Route path="/portfolio" element={<Portfolio />} />
```

- [ ] **Step 9: Verify portfolio page**

Navigate to http://localhost:5173/portfolio. Expected: Portfolio value header, holding cards with P&L, risk dashboard with sector bars, diversification gauge, correlation heatmap, what-if simulator, and rebalance suggestions.

- [ ] **Step 10: Commit**

```bash
cd /Users/zhuorantang/clawd/stock-picker
git add frontend/src/components/portfolio/ frontend/src/pages/Portfolio.tsx frontend/src/App.tsx
git commit -m "feat: add portfolio page with holdings, risk dashboard, diversification, correlation, and what-if"
```

---

## Task 10: Basic Tab Migrations (Backtest, Alerts, Accuracy, Momentum)

**Files:**
- Create: `frontend/src/pages/Backtest.tsx`
- Create: `frontend/src/pages/Alerts.tsx`
- Create: `frontend/src/pages/Accuracy.tsx`
- Create: `frontend/src/pages/Momentum.tsx`
- Modify: `frontend/src/App.tsx` — wire in all pages

- [ ] **Step 1: Build Backtest page**

Create `frontend/src/pages/Backtest.tsx`:

```tsx
import { useApi } from "../hooks/useApi";
import { api } from "../lib/api";
import type { BacktestResult } from "../lib/types";
import { pnlColor } from "../lib/colors";

export default function Backtest() {
  const { data, loading } = useApi<BacktestResult>(() => api.backtest());

  if (loading) return <div className="text-text-secondary">Loading backtest...</div>;
  if (!data) return <div className="text-text-secondary">No backtest data</div>;

  return (
    <div>
      <h1 className="text-xl font-bold mb-4">Backtest</h1>
      <div className="grid grid-cols-4 gap-3 mb-6">
        <div className="p-3.5 rounded-xl bg-surface border border-border">
          <div className="text-[11px] text-text-muted uppercase tracking-wider">Total Return</div>
          <div className={`text-2xl font-bold mt-1 ${pnlColor(data.summary.total_return)}`}>
            {(data.summary.total_return * 100).toFixed(1)}%
          </div>
        </div>
        <div className="p-3.5 rounded-xl bg-surface border border-border">
          <div className="text-[11px] text-text-muted uppercase tracking-wider">Win Rate</div>
          <div className="text-2xl font-bold text-text-primary mt-1">{(data.summary.win_rate * 100).toFixed(0)}%</div>
        </div>
        <div className="p-3.5 rounded-xl bg-surface border border-border">
          <div className="text-[11px] text-text-muted uppercase tracking-wider">Sharpe Ratio</div>
          <div className="text-2xl font-bold text-text-primary mt-1">{data.summary.sharpe_ratio.toFixed(2)}</div>
        </div>
        <div className="p-3.5 rounded-xl bg-surface border border-border">
          <div className="text-[11px] text-text-muted uppercase tracking-wider">Avg Win / Loss</div>
          <div className="text-2xl font-bold text-text-primary mt-1">
            {(data.summary.avg_win * 100).toFixed(1)}% / {(data.summary.avg_loss * 100).toFixed(1)}%
          </div>
        </div>
      </div>
      <div className="rounded-xl border border-border overflow-hidden">
        <table className="w-full">
          <thead className="bg-surface">
            <tr>
              <th className="py-2.5 px-3 text-left text-[11px] text-text-muted uppercase">Month</th>
              <th className="py-2.5 px-3 text-left text-[11px] text-text-muted uppercase">Avg Return</th>
              <th className="py-2.5 px-3 text-left text-[11px] text-text-muted uppercase">Best</th>
              <th className="py-2.5 px-3 text-left text-[11px] text-text-muted uppercase">Worst</th>
              <th className="py-2.5 px-3 text-left text-[11px] text-text-muted uppercase">Drawdown</th>
            </tr>
          </thead>
          <tbody>
            {data.backtest_results.map((r) => (
              <tr key={r.month} className="border-t border-surface">
                <td className="py-2.5 px-3 text-sm text-text-primary">{r.month}</td>
                <td className={`py-2.5 px-3 text-sm font-semibold ${pnlColor(r.avg_return)}`}>
                  {(r.avg_return * 100).toFixed(1)}%
                </td>
                <td className="py-2.5 px-3 text-sm text-positive">{r.best_stock} +{(r.best_return * 100).toFixed(1)}%</td>
                <td className="py-2.5 px-3 text-sm text-danger">{(r.worst_return * 100).toFixed(1)}%</td>
                <td className="py-2.5 px-3 text-sm text-danger">{(r.drawdown * 100).toFixed(1)}%</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
```

- [ ] **Step 2: Build Alerts page**

Create `frontend/src/pages/Alerts.tsx`:

```tsx
import { useApi } from "../hooks/useApi";
import { api } from "../lib/api";
import type { AlertsResponse } from "../lib/types";

export default function Alerts() {
  const { data, loading } = useApi<AlertsResponse>(() => api.alerts());

  if (loading) return <div className="text-text-secondary">Loading alerts...</div>;
  if (!data) return <div className="text-text-secondary">No alerts</div>;

  const severityClass = {
    critical: "bg-danger/15 text-danger",
    warning: "bg-caution/15 text-caution",
    info: "bg-accent/15 text-accent",
  };

  return (
    <div>
      <h1 className="text-xl font-bold mb-4">Alerts</h1>
      <div className="rounded-xl border border-border overflow-hidden">
        {data.current.length === 0 && (
          <div className="p-4 text-sm text-text-secondary">No active alerts</div>
        )}
        {data.current.map((a, i) => (
          <div key={i} className="px-4 py-3 border-b border-surface last:border-0 flex items-center gap-3">
            <span className={`px-2 py-0.5 rounded text-[10px] font-bold uppercase ${severityClass[a.severity]}`}>
              {a.severity}
            </span>
            <span className="text-sm font-semibold text-text-primary">{a.ticker}</span>
            <span className="text-sm text-text-secondary flex-1">{a.message}</span>
            <span className="text-xs text-text-muted">{new Date(a.timestamp).toLocaleTimeString()}</span>
          </div>
        ))}
      </div>
    </div>
  );
}
```

- [ ] **Step 3: Build Accuracy page**

Create `frontend/src/pages/Accuracy.tsx`:

```tsx
import { useApi } from "../hooks/useApi";
import { api } from "../lib/api";
import type { AccuracyResponse } from "../lib/types";

export default function Accuracy() {
  const { data, loading } = useApi<AccuracyResponse>(() => api.accuracy());

  if (loading) return <div className="text-text-secondary">Loading accuracy...</div>;
  if (!data) return <div className="text-text-secondary">No accuracy data</div>;

  return (
    <div>
      <h1 className="text-xl font-bold mb-4">Accuracy</h1>
      <div className="grid grid-cols-3 gap-3 mb-6">
        <div className="p-3.5 rounded-xl bg-surface border border-border">
          <div className="text-[11px] text-text-muted uppercase tracking-wider">Overall Accuracy</div>
          <div className="text-3xl font-bold text-text-primary mt-1">{data.accuracy_pct.toFixed(1)}%</div>
          <div className="text-[13px] text-text-secondary">{data.correct}/{data.total_predictions} picks</div>
        </div>
        {Object.entries(data.by_signal).map(([signal, stats]) => (
          <div key={signal} className="p-3.5 rounded-xl bg-surface border border-border">
            <div className="text-[11px] text-text-muted uppercase tracking-wider">{signal}</div>
            <div className="text-2xl font-bold text-text-primary mt-1">{stats.accuracy.toFixed(1)}%</div>
            <div className="text-[13px] text-text-secondary">{stats.correct}/{stats.total}</div>
          </div>
        ))}
      </div>
    </div>
  );
}
```

- [ ] **Step 4: Build Momentum page**

Create `frontend/src/pages/Momentum.tsx`:

```tsx
import { useScan } from "../App";
import ScoreBadge from "../components/common/ScoreBadge";
import RadarChart from "../components/common/RadarChart";

export default function Momentum() {
  const { scan, loading } = useScan();

  if (loading || !scan) return <div className="text-text-secondary">Loading...</div>;

  const top = scan.top.slice(0, 20);

  return (
    <div>
      <h1 className="text-xl font-bold mb-4">Momentum Radar</h1>
      <div className="grid grid-cols-2 gap-3">
        {top.map((s) => (
          <div key={s.ticker} className="p-4 rounded-xl bg-surface border border-border flex items-center gap-4">
            <RadarChart
              scores={{ fund: s.fundamentals_pct, val: s.valuation_pct, tech: s.technicals_pct, risk: s.risk_pct, grow: s.growth_pct }}
              size={64}
              showLabels={false}
            />
            <div className="flex-1">
              <div className="flex items-center gap-2 mb-1">
                <span className="font-bold text-text-primary">{s.ticker}</span>
                <ScoreBadge signal={s.entry_signal} />
              </div>
              <div className="text-xs text-text-secondary">{s.name} · {s.sector}</div>
              <div className="text-xs text-text-muted mt-1">Score: {s.composite_score.toFixed(1)} · RSI: {s.rsi.toFixed(1)}</div>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
```

- [ ] **Step 5: Wire all pages into App.tsx**

Update imports and routes in `frontend/src/App.tsx`:

```tsx
import Backtest from "./pages/Backtest";
import Alerts from "./pages/Alerts";
import Accuracy from "./pages/Accuracy";
import Momentum from "./pages/Momentum";

// Replace placeholder routes:
<Route path="/backtest" element={<Backtest />} />
<Route path="/alerts" element={<Alerts />} />
<Route path="/accuracy" element={<Accuracy />} />
<Route path="/momentum" element={<Momentum />} />
```

- [ ] **Step 6: Verify all tabs render**

Click through each sidebar link: Backtest, Alerts, Accuracy, Momentum. Each should show styled data from the API.

- [ ] **Step 7: Commit**

```bash
cd /Users/zhuorantang/clawd/stock-picker
git add frontend/src/pages/ frontend/src/App.tsx
git commit -m "feat: add backtest, alerts, accuracy, and momentum pages"
```

---

## Task 11: FastAPI Static Serving and Production Build

**Files:**
- Modify: `src/api.py` — update static file serving
- Modify: `.gitignore` — add frontend build artifacts

- [ ] **Step 1: Update FastAPI to serve built React app**

In `src/api.py`, find the existing `StaticFiles` mount and update it to serve from `static/dist/` first, falling back to the old `static/` directory:

```python
# Replace the existing static mount with:
from pathlib import Path

static_dist = Path(__file__).parent.parent / "static" / "dist"
static_legacy = Path(__file__).parent.parent / "static"

if static_dist.exists():
    app.mount("/", StaticFiles(directory=str(static_dist), html=True), name="static")
else:
    app.mount("/", StaticFiles(directory=str(static_legacy), html=True), name="static")
```

This ensures the new React build takes priority when it exists, but the old `index.html` still works if the frontend hasn't been built yet.

- [ ] **Step 2: Build the React app**

```bash
cd /Users/zhuorantang/clawd/stock-picker/frontend
npm run build
```

Expected: Vite builds to `static/dist/` with `index.html`, JS bundle, and CSS.

- [ ] **Step 3: Update .gitignore**

Add to `/Users/zhuorantang/clawd/stock-picker/.gitignore`:

```
# React frontend build
static/dist/
frontend/node_modules/
.superpowers/
```

- [ ] **Step 4: Verify production serving**

Restart the FastAPI server and visit http://localhost:8000/. Expected: The React app loads and works with all pages functional.

- [ ] **Step 5: Commit**

```bash
cd /Users/zhuorantang/clawd/stock-picker
git add src/api.py .gitignore frontend/
git commit -m "feat: configure FastAPI to serve React build, update gitignore"
```

---

## Task 12: Final Integration Verification

- [ ] **Step 1: Full end-to-end check**

With the FastAPI server running on port 8000:

```bash
cd /Users/zhuorantang/clawd/stock-picker/frontend
npm run build
```

Then restart the API server. Visit http://localhost:8000/ and verify:
1. Home dashboard loads with summary cards, action items, signals, market pulse
2. Scanner shows radar charts, sparklines, sector filters, signal badges
3. Clicking a stock row opens the ticker modal with synthesis, radar, metrics, tabs
4. Portfolio shows holdings, risk dashboard, diversification score, correlation heatmap, what-if
5. Backtest, Alerts, Accuracy, Momentum pages all render data
6. Sidebar navigation works across all pages
7. Header shows scan timestamp and regime badge

- [ ] **Step 2: Verify dev mode still works**

```bash
cd /Users/zhuorantang/clawd/stock-picker/frontend
npm run dev
```

Visit http://localhost:5173/ — the Vite proxy should forward API calls to port 8000.

- [ ] **Step 3: Final commit**

```bash
cd /Users/zhuorantang/clawd/stock-picker
git add -A
git status  # Verify only expected files
git commit -m "feat: complete React frontend redesign — home dashboard, enhanced scanner, ticker modal, portfolio page"
```
