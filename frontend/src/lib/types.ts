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
  type?: string;
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
  total_signals: number;
  buy_signals: number;
  evaluated: number;
  win_rate: number;
  avg_return: number;
  avg_alpha: number;
  best_pick: { ticker: string; return_pct: number; alpha_pct: number } | null;
  worst_pick: { ticker: string; return_pct: number } | null;
}

export interface StopLossAlert {
  ticker: string;
  current_price: number;
  entry_price: number;
  pnl_pct: number;
  pnl_dollar: number;
  shares: number;
  entry_date: string;
  stop_loss_threshold: number;
  status: string;
  urgency: string;
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

export interface TrailingStopAlert {
  ticker: string;
  entry_price: number;
  current_price: number;
  high_price: number;
  drop_from_high_pct: number;
  trailing_stop_pct: number;
  is_energy: boolean;
  status: string;
  urgency: string;
  message: string;
}

export interface PositionAlert {
  ticker: string;
  shares: number;
  current_price: number;
  value: number;
  entry_price: number;
  portfolio_pct: number;
  max_allowed_pct: number;
  status: string;
  message?: string;
  sector?: string;
  sector_pct?: number;
  sector_warning?: string;
}

export interface RiskSummary {
  timestamp: string;
  portfolio_value: number;
  total_invested: number;
  total_pnl: number;
  total_pnl_pct: number;
  num_positions: number;
  winners: number;
  losers: number;
  win_rate: number;
  avg_win_pct: number;
  avg_loss_pct: number;
  risk_score: number;
  stop_loss_alerts: StopLossAlert[];
  trailing_stop_alerts?: TrailingStopAlert[];
  position_alerts?: PositionAlert[];
  profit_alerts?: Array<Record<string, unknown>>;
  warnings?: Record<string, unknown>;
  concentration_warnings?: string[];
  geopolitical_risks?: string[];
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

export interface BacktestPeriod {
  spy_return: number;
  portfolio_return: number;
  pick_return?: number;
  alpha: number;
  win_rate: number;
  max_drawdown?: number;
  stocks_measured?: number;
}

export interface BacktestResult {
  months_back: number;
  top_picks: string[];
  periods: Record<string, BacktestPeriod>;
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

export interface ChartPoint {
  date: string;
  open: number | null;
  high: number | null;
  low: number | null;
  close: number;
}

export interface ChartData {
  ticker: string;
  ohlc: ChartPoint[];
  support: number | null;
  resistance: number | null;
  ma50: number | null;
}

export interface WatchlistEntry {
  added: string;
  price_at_add: number | null;
  current_price?: number;
  change_pct?: number;
}

export interface WatchlistResponse {
  tickers: Record<string, WatchlistEntry>;
}

export interface ThesisResponse {
  ticker: string;
  thesis: string | null;
  source: string;
}
