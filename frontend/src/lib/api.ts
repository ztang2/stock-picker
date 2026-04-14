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
};
