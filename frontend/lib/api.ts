import type {
  BacktestReport,
  Bar,
  DailyRecommendations,
  Signal,
  Summary,
} from "@/lib/types";

const API_BASE =
  process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";
const DATA_MODE = process.env.NEXT_PUBLIC_DATA_MODE ?? "api";
const BASE_PATH = process.env.NEXT_PUBLIC_BASE_PATH ?? "";

async function getJson<T>(path: string): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, { cache: "no-store" });
  if (!response.ok) {
    throw new Error(`API ${response.status}: ${path}`);
  }
  return response.json() as Promise<T>;
}

function getStaticJson<T>(path: string): Promise<T> {
  return getJsonFromUrl<T>(`${BASE_PATH}/data/${path}`);
}

async function getJsonFromUrl<T>(url: string): Promise<T> {
  const response = await fetch(url, { cache: "no-store" });
  if (!response.ok) {
    throw new Error(`Data ${response.status}: ${url}`);
  }
  return response.json() as Promise<T>;
}

export const api = {
  summary: () =>
    DATA_MODE === "static"
      ? getStaticJson<Summary>("summary.json")
      : getJson<Summary>("/api/summary"),
  signals: () =>
    DATA_MODE === "static"
      ? getStaticJson<Signal[]>("signals.json")
      : getJson<Signal[]>("/api/signals"),
  recommendations: () =>
    DATA_MODE === "static"
      ? getStaticJson<DailyRecommendations>("recommendations.json")
      : getJson<DailyRecommendations>("/api/recommendations"),
  bars: (symbol: string) =>
    DATA_MODE === "static"
      ? getStaticJson<Bar[]>(`bars/${encodeURIComponent(symbol)}.json`)
      : getJson<Bar[]>(`/api/instruments/${encodeURIComponent(symbol)}/bars`),
  backtest: (symbol: string, strategy: Signal["strategy"]) =>
    DATA_MODE === "static"
      ? getStaticJson<BacktestReport>(
          `backtests/${encodeURIComponent(symbol)}/${encodeURIComponent(strategy)}.json`,
        )
      : getJson<BacktestReport>(
          `/api/instruments/${encodeURIComponent(symbol)}/backtest?strategy=${encodeURIComponent(strategy)}`,
        ),
};
