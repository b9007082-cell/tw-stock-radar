export type SignalLevel = "WATCH" | "TRIAL" | "CONFIRMED";
export type EntryTimingStatus =
  | "WAIT_CONFIRMATION"
  | "WAIT_PULLBACK"
  | "TRIAL_ENTRY"
  | "READY"
  | "OVERHEATED";

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
  strategy:
    | "TREND_CONFIRMATION"
    | "PULLBACK_RESUME"
    | "CONSOLIDATION_BREAKOUT"
    | "BOTTOM_REVERSAL"
    | "LORENTZIAN_ML";
  strategy_version: string;
  level: SignalLevel;
  score: number;
  close: number;
  entry_price: number | null;
  entry_zone_low?: number | null;
  entry_zone_high?: number | null;
  trigger_price?: number | null;
  stop_price: number | null;
  risk_percent: number | null;
  timing_status?: EntryTimingStatus;
  timing_note?: string;
  overheated?: boolean;
  executable: boolean;
  validation_status: "APPROVED" | "RESEARCH";
  reasons: string[];
  metrics: Record<string, number | string | boolean>;
}

export interface RecommendationItem extends Signal {
  rank: number;
  recommendation_score: number;
  structure_risk_percent: number;
  reward_risk_ratio: number | null;
  ranking_reasons: string[];
}

export interface DailyRecommendations {
  as_of: string | null;
  ranking_version: string;
  pullback_resume: RecommendationItem[];
  consolidation_breakout: RecommendationItem[];
  bottom_reversal: RecommendationItem[];
  lorentzian_ml: RecommendationItem[];
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
  strategy: Signal["strategy"];
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
