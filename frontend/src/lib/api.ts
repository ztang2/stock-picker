const BASE = "";

async function get<T>(path: string): Promise<T> {
  const res = await fetch(`${BASE}${path}`);
  if (!res.ok) throw new Error(`${res.status} ${res.statusText}`);
  return res.json();
}

export const api = {
  scanCached: () => get<import("./types").ScanResult>("/scan/cached"),
  scanStatus: () => get<import("./types").ScanStatus>("/scan/status"),
  stock: (ticker: string) => get<import("./types").StockDetail>(`/stock/${ticker}`),
  entry: (ticker: string) => get<import("./types").EntryTiming>(`/entry/${ticker}`),
  dcf: (ticker: string) => get<import("./types").DCFSummary>(`/dcf/${ticker}/summary`),
  comps: (ticker: string) => get<import("./types").CompsResult>(`/comps/${ticker}`),
  earnings: (ticker: string) => get<import("./types").EarningsAnalysis>(`/earnings/${ticker}/analysis`),
  momentum: (ticker: string) => get<import("./types").MomentumScore>(`/momentum/${ticker}`),
  devil: (ticker: string) => get<import("./types").DevilsAdvocate>(`/review/${ticker}`),
  alerts: () => get<import("./types").AlertsResponse>("/alerts"),
  accuracy: () => get<import("./types").AccuracyResponse>("/accuracy"),
  backtest: (months = 6, topN = 20) =>
    get<import("./types").BacktestResult>(`/backtest?months_back=${months}&top_n=${topN}`),
  riskSummary: () => get<import("./types").RiskSummary>("/risk/summary"),
  stopLosses: () => get<{ alerts: import("./types").StopLossAlert[] }>("/risk/stop-losses"),
  positions: () => get<{ positions: import("./types").PositionAlert[] }>("/risk/positions"),
  portfolio: (stocks = 10) => get<import("./types").PortfolioResult>(`/portfolio?stocks=${stocks}`),
  profit: (ticker: string) => get<import("./types").ProfitTarget>(`/profit/${ticker}`),
  sectors: () => get<{ sectors: Record<string, number>; total: number }>("/sectors"),
  snapshotsRecent: (days = 7) =>
    get<import("./types").SnapshotDay[]>(`/snapshots/recent?days=${days}`),
  diversification: () => get<import("./types").DiversificationResponse>("/portfolio/diversification"),
  correlation: () => get<import("./types").CorrelationResponse>("/portfolio/correlation"),
  whatIf: (ticker: string) => get<import("./types").WhatIfResponse>(`/portfolio/whatif?ticker=${ticker}`),
  chart: (ticker: string, period = "3mo") =>
    get<import("./types").ChartData>(`/chart/${ticker}?period=${period}`),
  watchlist: () => get<import("./types").WatchlistResponse>("/watchlist"),
  addToWatchlist: (ticker: string) =>
    fetch(`/watchlist/${ticker}`, { method: "POST" }).then((r) => r.json()),
  removeFromWatchlist: (ticker: string) =>
    fetch(`/watchlist/${ticker}`, { method: "DELETE" }).then((r) => r.json()),
  thesis: (ticker: string) =>
    get<import("./types").ThesisResponse>(`/thesis/${ticker}/gemini`),
  listHoldings: () => get<{ holdings: Record<string, HoldingRecord> }>("/portfolio/holdings"),
  createHolding: (ticker: string, body: HoldingPayload) =>
    mutate("POST", `/portfolio/holdings/${ticker}`, body),
  updateHolding: (ticker: string, body: HoldingPayload) =>
    mutate("PATCH", `/portfolio/holdings/${ticker}`, body),
  addSharesToHolding: (ticker: string, body: { added_shares: number; added_price: number; added_date?: string; note?: string }) =>
    mutate("POST", `/portfolio/holdings/${ticker}/add`, body),
  deleteHolding: (ticker: string) =>
    mutate("DELETE", `/portfolio/holdings/${ticker}`),
  closeHolding: (ticker: string, body: { exit_price: number; exit_date: string; note?: string }) =>
    mutate("POST", `/portfolio/holdings/${ticker}/close`, body),
  closedHoldings: () =>
    get<{ closed: ClosedHolding[] }>("/closed-holdings"),
  closedStats: () =>
    get<ClosedStats>("/closed-holdings/stats"),
};

export interface ClosedHolding {
  ticker: string;
  shares: number;
  entry_price: number;
  entry_date?: string;
  exit_price: number;
  exit_date: string;
  realized_pnl: number;
  realized_pnl_pct: number;
  hold_days: number | null;
  entry_score?: number;
  entry_note?: string;
  close_note?: string;
}

export interface ClosedStats {
  count: number;
  total_realized_pnl: number;
  win_rate: number | null;
  avg_hold_days: number | null;
  avg_return_pct: number | null;
  best_trade: { ticker: string; pnl_pct: number; pnl: number } | null;
  worst_trade: { ticker: string; pnl_pct: number; pnl: number } | null;
}

export interface HoldingRecord {
  shares: number;
  entry_price: number;
  entry_date?: string;
  entry_score?: number;
  note?: string;
}

export interface HoldingPayload {
  shares?: number;
  entry_price?: number;
  entry_date?: string;
  entry_score?: number;
  note?: string;
}

async function mutate(method: string, path: string, body?: unknown) {
  const res = await fetch(`${BASE}${path}`, {
    method,
    headers: {
      "Content-Type": "application/json",
      "X-API-Key": "stock-picker",
    },
    body: body ? JSON.stringify(body) : undefined,
  });
  if (!res.ok) {
    const text = await res.text();
    throw new Error(`${res.status}: ${text}`);
  }
  return res.json();
}
