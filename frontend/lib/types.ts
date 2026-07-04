export type SignalLevel = "WATCH" | "TRIAL" | "CONFIRMED";

export interface Summary {
  as_of: string | null;
  total_signals: number;
  watch: number;
  trial: number;
  confirmed: number;
  instruments: number;
  strategy_version: string;
  strategy_approved: boolean;
}

export interface Signal {
  id: number;
  symbol: string;
  name: string;
  market: string;
  signal_date: string;
  strategy: "CONSOLIDATION_BREAKOUT" | "STRONG_PULLBACK";
  strategy_version: string;
  level: SignalLevel;
  score: number;
  close: number;
  entry_price: number | null;
  stop_price: number | null;
  risk_percent: number | null;
  executable: boolean;
  validation_status: "APPROVED" | "RESEARCH";
  reasons: string[];
  metrics: Record<string, number | string | boolean>;
}

export interface Bar {
  trade_date: string;
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number;
  turnover: number;
}

export interface BacktestReport {
  symbol: string;
  strategy_version: string;
  trades: number;
  win_rate: number;
  profit_factor: number | null;
  expectancy: number;
  total_return: number;
  max_drawdown: number;
  sharpe_like: number;
  gate_passed: boolean;
  gate_reasons: string[];
}
