"use client";

import { useEffect, useMemo, useState } from "react";

import { api } from "@/lib/api";
import type {
  BacktestReport,
  Bar,
  DailyRecommendations,
  EntryTimingStatus,
  RecommendationItem,
  Signal,
  SignalLevel,
  Summary,
} from "@/lib/types";
import { StockChart } from "@/components/stock-chart";

const updateWorkerUrl = process.env.NEXT_PUBLIC_UPDATE_WORKER_URL ?? "";

const levelLabel: Record<SignalLevel, string> = {
  WATCH: "觀察",
  TRIAL: "轉強",
  CONFIRMED: "確認",
};

const strategyLabel: Record<Signal["strategy"], string> = {
  TREND_CONFIRMATION: "多頭確認",
  PULLBACK_RESUME: "回後買上漲",
  CONSOLIDATION_BREAKOUT: "盤整突破",
  DISPOSITION_REVERSAL: "處置反彈",
  BOTTOM_REVERSAL: "搶反彈",
  BOLLINGER_SQUEEZE: "布林收斂",
  INTRADAY_MA60_TOUCH: "6060戰法",
  LOW_PRICE_HIGH_YIELD: "低檔高殖利率",
  LORENTZIAN_ML: "Lorentzian ML",
};

const strategyTabs = [
  ["ALL", "全部策略"],
  ["PULLBACK_RESUME", "回後買上漲"],
  ["CONSOLIDATION_BREAKOUT", "盤整突破"],
  ["DISPOSITION_REVERSAL", "處置反彈"],
  ["BOTTOM_REVERSAL", "搶反彈"],
  ["BOLLINGER_SQUEEZE", "布林收斂"],
  ["INTRADAY_MA60_TOUCH", "6060戰法"],
  ["LOW_PRICE_HIGH_YIELD", "低檔高殖利率"],
  ["LORENTZIAN_ML", "Lorentzian ML"],
] as const;

const levelOrder: Record<SignalLevel, number> = {
  CONFIRMED: 0,
  TRIAL: 1,
  WATCH: 2,
};

const timingLabel: Record<EntryTimingStatus, string> = {
  WAIT_CONFIRMATION: "等待確認",
  WAIT_PULLBACK: "回檔觀察",
  TRIAL_ENTRY: "轉強中",
  READY: "進場區",
  OVERHEATED: "過熱勿追",
};

const timingStyle: Record<EntryTimingStatus, string> = {
  WAIT_CONFIRMATION: "border-blue-400/25 bg-blue-400/5 text-blue-200",
  WAIT_PULLBACK: "border-amber-400/25 bg-amber-400/5 text-amber-100",
  TRIAL_ENTRY: "border-amber-300/30 bg-amber-300/10 text-amber-100",
  READY: "border-emerald-400/30 bg-emerald-400/10 text-emerald-100",
  OVERHEATED: "border-rose-400/30 bg-rose-400/10 text-rose-100",
};

function formatPrice(value: number | null | undefined) {
  return value == null ? "—" : value.toFixed(2);
}

function formatEntryZone(signal: Signal) {
  if (signal.entry_zone_low == null || signal.entry_zone_high == null) {
    return formatPrice(signal.entry_price);
  }
  return `${formatPrice(signal.entry_zone_low)}～${formatPrice(signal.entry_zone_high)}`;
}

function getTimingStatus(signal: Signal): EntryTimingStatus {
  return (
    signal.timing_status ??
    (signal.level === "CONFIRMED"
      ? "READY"
      : signal.level === "TRIAL"
        ? "TRIAL_ENTRY"
        : "WAIT_CONFIRMATION")
  );
}

function metricNumber(signal: Signal, key: string) {
  const value = signal.metrics[key];
  return typeof value === "number" ? value : null;
}

function formatLots(signal: Signal) {
  const lots = metricNumber(signal, "latest_volume_lots");
  return lots == null ? "—" : `${Math.round(lots).toLocaleString()}張`;
}

function TrendMetricsPanel({ signal }: { signal: Signal }) {
  if (signal.strategy === "DISPOSITION_REVERSAL") {
    const similarity = metricNumber(signal, "disposition_similarity_score");
    const drawdown = metricNumber(signal, "drawdown_percent");
    const limitLikeDays = metricNumber(signal, "limit_like_drop_days");
    const deviation = metricNumber(signal, "deviation_rate_percent");
    const stopVolumeRatio = metricNumber(signal, "stop_volume_ratio");
    const daysToRelease = metricNumber(signal, "inferred_days_to_release");
    const status = signal.metrics.inferred_disposition_status;
    const items = [
      ["相似度", similarity == null ? "—" : `${similarity.toFixed(0)}分`],
      ["高點回落", drawdown == null ? "—" : `${drawdown.toFixed(1)}%`],
      ["急跌日", limitLikeDays == null ? "—" : `${limitLikeDays.toFixed(0)}天`],
      ["偏離20MA", deviation == null ? "—" : `${deviation.toFixed(1)}%`],
      ["爆量倍數", stopVolumeRatio == null ? "—" : `${stopVolumeRatio.toFixed(2)}倍`],
      ["推估狀態", typeof status === "string" ? status : "—"],
      ["推估收斂", daysToRelease == null ? "—" : `約${daysToRelease.toFixed(0)}天`],
      ["止跌K低點", formatPrice(metricNumber(signal, "previous_stop_low"))],
    ];
    return (
      <div className="mt-4 rounded-xl border border-rose-400/20 bg-rose-400/5 p-3">
        <div className="mb-3 text-xs font-bold tracking-wider text-rose-200">
          處置反彈檢查
        </div>
        <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
          {items.map(([label, value]) => (
            <div key={label} className="rounded-lg bg-slate-950/35 p-2.5">
              <div className="text-[10px] text-slate-500">{label}</div>
              <div className="mt-1 text-sm font-semibold text-rose-100">
                {value}
              </div>
            </div>
          ))}
        </div>
        <div className="mt-3 text-[11px] leading-5 text-rose-100/65">
          目前為價量推估版；正式處置、出關日仍需以證交所／櫃買公告為準。
        </div>
      </div>
    );
  }
  if (signal.strategy === "LOW_PRICE_HIGH_YIELD") {
    const dividendYield = metricNumber(signal, "dividend_yield");
    const drawdown = metricNumber(signal, "drawdown_from_high_percent");
    const distanceFromLow = metricNumber(signal, "distance_from_low_percent");
    const pbRatio = metricNumber(signal, "pb_ratio");
    const peRatio = metricNumber(signal, "pe_ratio");
    const valuationDate = signal.metrics.valuation_date;
    const items = [
      ["殖利率", dividendYield == null ? "—" : `${dividendYield.toFixed(2)}%`],
      ["高點回落", drawdown == null ? "—" : `${drawdown.toFixed(1)}%`],
      ["距低點", distanceFromLow == null ? "—" : `${distanceFromLow.toFixed(1)}%`],
      ["P/B", pbRatio == null || pbRatio === 0 ? "—" : pbRatio.toFixed(2)],
      ["本益比", peRatio == null || peRatio === 0 ? "—" : peRatio.toFixed(2)],
      ["估值日", typeof valuationDate === "string" ? valuationDate : "—"],
    ];
    return (
      <div className="mt-4 rounded-xl border border-lime-400/20 bg-lime-400/5 p-3">
        <div className="mb-3 text-xs font-bold tracking-wider text-lime-200">
          低檔高殖利率檢查
        </div>
        <div className="grid grid-cols-2 gap-2 sm:grid-cols-3">
          {items.map(([label, value]) => (
            <div key={label} className="rounded-lg bg-slate-950/35 p-2.5">
              <div className="text-[10px] text-slate-500">{label}</div>
              <div className="mt-1 text-sm font-semibold text-lime-100">
                {value}
              </div>
            </div>
          ))}
        </div>
      </div>
    );
  }
  if (signal.strategy === "INTRADAY_MA60_TOUCH") {
    const distance = metricNumber(signal, "intraday_distance_to_ma60_percent");
    const ma60 = metricNumber(signal, "intraday_ma60");
    const slope = metricNumber(signal, "intraday_ma60_slope_percent");
    const macd = metricNumber(signal, "intraday_macd_line");
    const volumeRatio = metricNumber(signal, "intraday_volume_ratio");
    const dailyMa5 = metricNumber(signal, "daily_ma5");
    const dailyMa10 = metricNumber(signal, "daily_ma10");
    const dailyMa20 = metricNumber(signal, "daily_ma20");
    const dailyMa60 = metricNumber(signal, "daily_ma60");
    const dailyMa20Slope = metricNumber(signal, "daily_ma20_slope_percent");
    const dailyMa60Slope = metricNumber(signal, "daily_ma60_slope_percent");
    const volumeBreakout = signal.metrics.intraday_volume_breakout;
    const barTime = signal.metrics.intraday_bar_time;
    const items = [
      [
        "日線20/60MA",
        dailyMa20Slope != null && dailyMa60Slope != null
          ? `${dailyMa20Slope.toFixed(2)}% / ${dailyMa60Slope.toFixed(2)}%`
          : dailyMa5 && dailyMa10 && dailyMa20 && dailyMa60
            ? `20MA ${dailyMa20.toFixed(1)} / 60MA ${dailyMa60.toFixed(1)}`
          : "—",
      ],
      ["60分MA60", formatPrice(ma60)],
      ["距60MA", distance == null ? "—" : `${distance.toFixed(2)}%`],
      ["60MA上彎", slope == null ? "—" : `${slope.toFixed(2)}%`],
      ["MACD零軸", macd == null ? "—" : `${macd.toFixed(3)}`],
      [
        "60分量比",
        volumeRatio == null || volumeRatio === 0
          ? "資料不足"
          : `${volumeRatio.toFixed(2)}倍`,
      ],
      ["進場訊號", volumeBreakout ? "放量突破/確認" : "等待放量"],
      ["資料時間", typeof barTime === "string" ? barTime.slice(5, 16) : "—"],
    ];
    return (
      <div className="mt-4 rounded-xl border border-sky-400/20 bg-sky-400/5 p-3">
        <div className="mb-3 text-xs font-bold tracking-wider text-sky-200">
          6060戰法檢查
        </div>
        <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
          {items.map(([label, value]) => (
            <div key={label} className="rounded-lg bg-slate-950/35 p-2.5">
              <div className="text-[10px] text-slate-500">{label}</div>
              <div className="mt-1 text-sm font-semibold text-sky-100">
                {value}
              </div>
            </div>
          ))}
        </div>
      </div>
    );
  }
  if (signal.strategy === "BOLLINGER_SQUEEZE") {
    const width = metricNumber(signal, "bollinger_width_percent");
    const percentile = metricNumber(signal, "bollinger_width_percentile");
    const items = [
      ["布林寬度", width == null ? "—" : `${width.toFixed(2)}%`],
      [
        "寬度分位",
        percentile == null ? "—" : `${(percentile * 100).toFixed(0)}%`,
      ],
      ["上通道", formatPrice(metricNumber(signal, "bollinger_upper"))],
      ["下通道", formatPrice(metricNumber(signal, "bollinger_lower"))],
    ];
    return (
      <div className="mt-4 rounded-xl border border-fuchsia-400/20 bg-fuchsia-400/5 p-3">
        <div className="mb-3 text-xs font-bold tracking-wider text-fuchsia-200">
          布林通道收斂檢查
        </div>
        <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
          {items.map(([label, value]) => (
            <div key={label} className="rounded-lg bg-slate-950/35 p-2.5">
              <div className="text-[10px] text-slate-500">{label}</div>
              <div className="mt-1 text-sm font-semibold text-fuchsia-100">
                {value}
              </div>
            </div>
          ))}
        </div>
      </div>
    );
  }
  const higherHigh = signal.metrics.higher_high === true;
  const higherLow = signal.metrics.higher_low === true;
  const items = [
    ["趨勢結構", higherHigh && higherLow ? "頭頭高・底底高" : "尚未完整"],
    [
      "均線排列",
      `${formatPrice(metricNumber(signal, "ma5"))} ＞ ${formatPrice(
        metricNumber(signal, "ma10"),
      )} ＞ ${formatPrice(metricNumber(signal, "ma20"))}`,
    ],
    ["最近壓力", formatPrice(metricNumber(signal, "latest_peak"))],
    ["結構防守", formatPrice(metricNumber(signal, "latest_trough"))],
  ];
  return (
    <div className="mt-4 rounded-xl border border-cyan-400/20 bg-cyan-400/5 p-3">
      <div className="mb-3 text-xs font-bold tracking-wider text-cyan-200">
        公開原則量化檢查
      </div>
      <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
        {items.map(([label, value]) => (
          <div key={label} className="rounded-lg bg-slate-950/35 p-2.5">
            <div className="text-[10px] text-slate-500">{label}</div>
            <div className="mt-1 text-sm font-semibold text-cyan-100">{value}</div>
          </div>
        ))}
      </div>
    </div>
  );
}

function LevelBadge({ level }: { level: SignalLevel }) {
  const styles = {
    WATCH: "border-blue-400/30 bg-blue-400/10 text-blue-300",
    TRIAL: "border-amber-400/30 bg-amber-400/10 text-amber-300",
    CONFIRMED: "border-emerald-400/30 bg-emerald-400/10 text-emerald-300",
  };
  return (
    <span
      className={`rounded-full border px-2.5 py-1 text-xs font-semibold ${styles[level]}`}
    >
      {levelLabel[level]}
    </span>
  );
}

function EntryTimingPanel({ signal }: { signal: Signal }) {
  const status = getTimingStatus(signal);
  return (
    <div className={`mt-4 rounded-xl border p-3 ${timingStyle[status]}`}>
      <div className="text-xs font-bold tracking-wider">
        今日時機：{timingLabel[status]}
      </div>
      <div className="mt-1 text-xs leading-5 opacity-80">
        {signal.timing_note ?? "依最新收盤、均線與量能重新確認進場條件。"}
      </div>
    </div>
  );
}

function visibleReasons(signal: Signal) {
  return signal.reasons.filter((reason) => !reason.startsWith("多頭確認"));
}

function RecommendationBoard({
  title,
  subtitle,
  items,
  accent,
  onSelect,
}: {
  title: string;
  subtitle: string;
  items: RecommendationItem[];
  accent: "emerald" | "cyan" | "rose" | "amber" | "fuchsia" | "sky" | "lime" | "violet";
  onSelect: (item: RecommendationItem) => void;
}) {
  const accentClass =
    accent === "emerald"
      ? "text-emerald-300"
      : accent === "cyan"
        ? "text-cyan-300"
        : accent === "rose"
          ? "text-rose-300"
          : accent === "amber"
            ? "text-amber-300"
            : accent === "fuchsia"
              ? "text-fuchsia-300"
              : accent === "sky"
                ? "text-sky-300"
                : accent === "lime"
                  ? "text-lime-300"
                  : "text-violet-300";
  return (
    <article className="overflow-hidden rounded-2xl border border-slate-700/70 bg-slate-900/70 backdrop-blur">
      <div className="border-b border-slate-800 px-4 py-3">
        <div className={`text-sm font-bold ${accentClass}`}>{title}</div>
        <div className="mt-1 text-xs text-slate-500">{subtitle}</div>
      </div>
      <div className="divide-y divide-slate-800">
        {items.map((item) => {
          const volumeRatio = metricNumber(item, "volume_ratio");
          const drawdownPercent = metricNumber(item, "drawdown_percent");
          const stopVolumeRatio = metricNumber(item, "stop_volume_ratio");
          const dispositionSimilarity = metricNumber(
            item,
            "disposition_similarity_score",
          );
          const dispositionDropDays = metricNumber(item, "limit_like_drop_days");
          const mlPrediction = metricNumber(item, "ml_prediction");
          const mlConfidence = metricNumber(item, "ml_confidence");
          const bollingerWidth = metricNumber(item, "bollinger_width_percent");
          const bollingerPercentile = metricNumber(
            item,
            "bollinger_width_percentile",
          );
          const intradayDistance = metricNumber(
            item,
            "intraday_distance_to_ma60_percent",
          );
          const intradaySlope = metricNumber(
            item,
            "intraday_ma60_slope_percent",
          );
          const intradayVolumeRatio = metricNumber(item, "intraday_volume_ratio");
          const dividendYield = metricNumber(item, "dividend_yield");
          const distanceFromLow = metricNumber(
            item,
            "distance_from_low_percent",
          );
          return (
            <button
              key={`${item.strategy}-${item.symbol}`}
              type="button"
              onClick={() => onSelect(item)}
              className="grid w-full grid-cols-[32px_minmax(0,1fr)_auto] items-center gap-3 px-4 py-3 text-left transition hover:bg-slate-800/70"
            >
              <span className={`text-lg font-black ${accentClass}`}>
                {item.rank}
              </span>
              <span className="min-w-0">
                <span className="block truncate text-sm font-semibold text-white">
                  {item.symbol} {item.name}
                </span>
                <span className="mt-1 flex flex-wrap gap-x-2 text-[11px] text-slate-500">
                  <span>{levelLabel[item.level]}</span>
                  <span>風險 {item.structure_risk_percent.toFixed(1)}%</span>
                  <span>成交 {formatLots(item)}</span>
                  <span>
                    {item.strategy === "PULLBACK_RESUME"
                      ? `${item.reward_risk_ratio?.toFixed(2) ?? "—"}R`
                      : item.strategy === "DISPOSITION_REVERSAL"
                        ? `相似 ${dispositionSimilarity?.toFixed(0) ?? "—"}分`
                        : item.strategy === "BOTTOM_REVERSAL"
                        ? `跌幅 ${drawdownPercent?.toFixed(1) ?? "—"}%`
                        : item.strategy === "LORENTZIAN_ML"
                          ? `ML ${mlPrediction?.toFixed(0) ?? "—"}`
                          : item.strategy === "BOLLINGER_SQUEEZE"
                            ? `寬度 ${bollingerWidth?.toFixed(2) ?? "—"}%`
                            : item.strategy === "INTRADAY_MA60_TOUCH"
                              ? `距60MA ${intradayDistance?.toFixed(2) ?? "—"}%`
                              : item.strategy === "LOW_PRICE_HIGH_YIELD"
                                ? `殖利率 ${dividendYield?.toFixed(2) ?? "—"}%`
                                : `量比 ${volumeRatio?.toFixed(2) ?? "—"}倍`}
                  </span>
                  {item.strategy === "BOTTOM_REVERSAL" && (
                    <span>爆量 {stopVolumeRatio?.toFixed(2) ?? "—"}倍</span>
                  )}
                  {item.strategy === "DISPOSITION_REVERSAL" && (
                    <>
                      <span>急跌 {dispositionDropDays?.toFixed(0) ?? "—"}天</span>
                      <span>爆量 {stopVolumeRatio?.toFixed(2) ?? "—"}倍</span>
                    </>
                  )}
                  {item.strategy === "LORENTZIAN_ML" && (
                    <span>
                      信心 {mlConfidence == null ? "—" : `${(mlConfidence * 100).toFixed(0)}%`}
                    </span>
                  )}
                  {item.strategy === "BOLLINGER_SQUEEZE" && (
                    <span>
                      分位{" "}
                      {bollingerPercentile == null
                        ? "—"
                        : `${(bollingerPercentile * 100).toFixed(0)}%`}
                    </span>
                  )}
                  {item.strategy === "INTRADAY_MA60_TOUCH" && (
                    <>
                      <span>
                        上彎 {intradaySlope == null ? "—" : `${intradaySlope.toFixed(2)}%`}
                      </span>
                      <span>
                        量比{" "}
                        {intradayVolumeRatio == null || intradayVolumeRatio === 0
                          ? "—"
                          : `${intradayVolumeRatio.toFixed(2)}倍`}
                      </span>
                    </>
                  )}
                  {item.strategy === "LOW_PRICE_HIGH_YIELD" && (
                    <span>
                      距低點{" "}
                      {distanceFromLow == null ? "—" : `${distanceFromLow.toFixed(1)}%`}
                    </span>
                  )}
                  </span>
                </span>
              <span className="text-right">
                <span className={`block text-lg font-bold ${accentClass}`}>
                  {item.recommendation_score.toFixed(1)}
                </span>
                <span className="text-[10px] text-slate-600">推薦分</span>
              </span>
            </button>
          );
        })}
        {items.length === 0 && (
          <div className="px-4 py-8 text-center text-sm text-slate-500">
            今日沒有通過風險與獲利空間門檻的股票。
          </div>
        )}
      </div>
    </article>
  );
}

export function Dashboard() {
  const [summary, setSummary] = useState<Summary | null>(null);
  const [signals, setSignals] = useState<Signal[]>([]);
  const [recommendations, setRecommendations] =
    useState<DailyRecommendations | null>(null);
  const [selected, setSelected] = useState<Signal | null>(null);
  const [bars, setBars] = useState<Bar[]>([]);
  const [backtest, setBacktest] = useState<BacktestReport | null>(null);
  const [capital, setCapital] = useState(1_000_000);
  const [filter, setFilter] = useState<SignalLevel | "ALL">("ALL");
  const [strategyFilter, setStrategyFilter] = useState<
    Signal["strategy"] | "ALL"
  >("ALL");
  const [query, setQuery] = useState("");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    Promise.all([api.summary(), api.signals(), api.recommendations()])
      .then(([summaryData, signalData, recommendationData]) => {
        setSummary(summaryData);
        setSignals(signalData);
        setRecommendations(recommendationData);
        setSelected(signalData[0] ?? null);
      })
      .catch((reason: unknown) =>
        setError(reason instanceof Error ? reason.message : "API 連線失敗"),
      )
      .finally(() => setLoading(false));
  }, []);

  const visibleSignals = useMemo(() => {
    const needle = query.trim().toLowerCase();
    const filtered = signals.filter(
      (signal) =>
        signal.strategy !== "TREND_CONFIRMATION" &&
        (strategyFilter === "ALL" || signal.strategy === strategyFilter) &&
        (filter === "ALL" || signal.level === filter) &&
        (!needle ||
          signal.symbol.toLowerCase().includes(needle) ||
          signal.name.toLowerCase().includes(needle)),
    );
    if (strategyFilter !== "ALL") {
      filtered.sort((left, right) => {
        const stageDifference =
          levelOrder[left.level] - levelOrder[right.level];
        if (stageDifference !== 0) return stageDifference;
        return right.score - left.score || left.symbol.localeCompare(right.symbol);
      });
    }
    return filtered;
  }, [filter, query, signals, strategyFilter]);

  const activeSelected = useMemo(
    () =>
      selected &&
      visibleSignals.some((signal) => signal.id === selected.id)
        ? selected
        : (visibleSignals[0] ?? null),
    [selected, visibleSignals],
  );

  useEffect(() => {
    if (!activeSelected) return;
    Promise.all([
      api.bars(activeSelected.symbol),
      api.backtest(activeSelected.symbol, activeSelected.strategy),
    ])
      .then(([barData, report]) => {
        setBars(barData);
        setBacktest(report);
      })
      .catch(() => {
        setBars([]);
        setBacktest(null);
      });
  }, [activeSelected]);

  const cards = [
    { label: "今日候選", value: summary?.total_signals ?? 0, tone: "text-white" },
    { label: "觀察", value: summary?.watch ?? 0, tone: "text-blue-300" },
    { label: "轉強", value: summary?.trial ?? 0, tone: "text-amber-300" },
    { label: "確認", value: summary?.confirmed ?? 0, tone: "text-emerald-300" },
  ];

  const selectRecommendation = (item: RecommendationItem) => {
    setStrategyFilter(item.strategy);
    setFilter("ALL");
    setQuery("");
    setSelected(item);
  };

  const positionShares = useMemo(() => {
    if (
      !activeSelected ||
      activeSelected.entry_price === null ||
      activeSelected.stop_price === null ||
      activeSelected.level !== "CONFIRMED"
    ) {
      return 0;
    }
    const perShareRisk =
      activeSelected.entry_price - activeSelected.stop_price;
    if (perShareRisk <= 0) return 0;
    const riskRate = 0.01;
    return (
      Math.floor((capital * riskRate) / perShareRisk / 1000) * 1000
    );
  }, [activeSelected, capital]);

  return (
    <main className="mx-auto min-h-screen max-w-[1600px] px-4 py-5 sm:px-7">
      <header className="mb-7 flex flex-col justify-between gap-4 sm:flex-row sm:items-end">
        <div>
          <div className="mb-2 flex items-center gap-2 text-xs font-semibold tracking-[0.22em] text-emerald-300">
            <span className="h-2 w-2 rounded-full bg-emerald-300 shadow-[0_0_14px_#4ee0a0]" />
            AFTER-MARKET SCANNER
          </div>
          <h1 className="text-3xl font-bold tracking-tight sm:text-4xl">
            台股起漲雷達
          </h1>
          <p className="mt-2 text-sm text-slate-400">
            回後買上漲 × 盤整突破 × 處置反彈 × 搶反彈 × 布林收斂 × 6060戰法 × 低檔高殖利率 × Lorentzian ML｜依公開教學原則量化
          </p>
        </div>
        <div className="text-left text-xs leading-6 text-slate-400 sm:text-right">
          <div>資料日：{summary?.as_of ?? "尚無資料"}</div>
          <div>策略版本：{summary?.strategy_version ?? "—"}</div>
          <div>
            驗證狀態：
            {summary?.strategy_approved ? " 已核准" : " 研究版"}
          </div>
          {updateWorkerUrl && (
            <a
              href={updateWorkerUrl}
              target="_blank"
              rel="noopener noreferrer"
              className="mt-2 inline-flex items-center rounded-lg border border-emerald-300/30 bg-emerald-300/10 px-3 py-1.5 font-semibold text-emerald-200 transition hover:bg-emerald-300/20"
            >
              立即更新資料
            </a>
          )}
        </div>
      </header>

      {error && (
        <div className="mb-5 rounded-xl border border-rose-400/30 bg-rose-400/10 px-4 py-3 text-sm text-rose-200">
          無法讀取選股資料：{error}。請稍後重試；維護者可檢查資料更新流程。
        </div>
      )}

      <section className="mb-5 grid grid-cols-2 gap-3 lg:grid-cols-4">
        {cards.map((card) => (
          <article
            key={card.label}
            className="rounded-2xl border border-slate-700/70 bg-slate-900/70 p-4 shadow-[0_14px_40px_rgba(0,0,0,0.18)] backdrop-blur"
          >
            <div className="text-xs text-slate-400">{card.label}</div>
            <div className={`mt-2 text-3xl font-bold ${card.tone}`}>
              {loading ? "…" : card.value}
            </div>
          </article>
        ))}
      </section>

      <section className="mb-5 grid gap-4 xl:grid-cols-8">
        <RecommendationBoard
          title="回後買上漲 Top 10"
          subtitle="確認優先｜風險 ≤ 8%｜前高空間 ≥ 1.5R"
          items={recommendations?.pullback_resume ?? []}
          accent="emerald"
          onSelect={selectRecommendation}
        />
        <RecommendationBoard
          title="盤整突破 Top 10"
          subtitle="確認優先｜風險 ≤ 8%｜量能與突破距離排序"
          items={recommendations?.consolidation_breakout ?? []}
          accent="cyan"
          onSelect={selectRecommendation}
        />
        <RecommendationBoard
          title="處置反彈 Top 10"
          subtitle="疑似處置急跌｜爆量止跌｜突破止跌K高點"
          items={recommendations?.disposition_reversal ?? []}
          accent="rose"
          onSelect={selectRecommendation}
        />
        <RecommendationBoard
          title="搶反彈 Top 10"
          subtitle="急跌 ≥ 15%｜低檔爆量 ≥ 2倍｜突破止跌K高點"
          items={recommendations?.bottom_reversal ?? []}
          accent="amber"
          onSelect={selectRecommendation}
        />
        <RecommendationBoard
          title="布林收斂 Top 10"
          subtitle="上通道與下通道靠近｜等待突破方向"
          items={recommendations?.bollinger_squeeze ?? []}
          accent="fuchsia"
          onSelect={selectRecommendation}
        />
        <RecommendationBoard
          title="6060戰法 Top 10"
          subtitle="日線20/60MA向上｜60分60MA上彎｜MACD零軸上｜放量突破"
          items={recommendations?.intraday_ma60_touch ?? []}
          accent="sky"
          onSelect={selectRecommendation}
        />
        <RecommendationBoard
          title="低檔高殖利率 Top 10"
          subtitle="殖利率 ≥ 5%｜低位階｜成交 ≥ 2000張"
          items={recommendations?.low_price_high_yield ?? []}
          accent="lime"
          onSelect={selectRecommendation}
        />
        <RecommendationBoard
          title="Lorentzian ML Top 10"
          subtitle="近鄰投票｜Kernel趨勢｜研究輔助訊號"
          items={recommendations?.lorentzian_ml ?? []}
          accent="violet"
          onSelect={selectRecommendation}
        />
      </section>

      <section className="grid gap-5 xl:grid-cols-[minmax(0,1.25fr)_minmax(420px,0.75fr)]">
        <article className="overflow-hidden rounded-2xl border border-slate-700/70 bg-slate-900/70 backdrop-blur">
          <div className="border-b border-slate-700/70 p-4">
            <div className="mb-3 flex flex-wrap gap-2">
              {strategyTabs.map(([value, label]) => (
                <button
                  key={value}
                  onClick={() => setStrategyFilter(value)}
                  className={`rounded-lg px-3 py-2 text-xs font-semibold transition ${
                    strategyFilter === value
                      ? "bg-cyan-300 text-slate-950"
                      : "border border-slate-700 bg-slate-900 text-slate-300 hover:bg-slate-800"
                  }`}
                >
                  {label}
                </button>
              ))}
            </div>
            <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
            <div className="flex flex-wrap gap-2">
              {(["ALL", "WATCH", "TRIAL", "CONFIRMED"] as const).map(
                (item) => (
                  <button
                    key={item}
                    onClick={() => setFilter(item)}
                    className={`rounded-lg px-3 py-2 text-xs font-semibold transition ${
                      filter === item
                        ? "bg-emerald-300 text-slate-950"
                        : "bg-slate-800 text-slate-300 hover:bg-slate-700"
                    }`}
                  >
                    {item === "ALL" ? "全部" : levelLabel[item]}
                  </button>
                ),
              )}
            </div>
            <input
              value={query}
              onChange={(event) => setQuery(event.target.value)}
              placeholder="搜尋代號或名稱"
              className="rounded-lg border border-slate-700 bg-slate-950/70 px-3 py-2 text-sm outline-none placeholder:text-slate-600 focus:border-emerald-400"
            />
            </div>
          </div>
          <div className="overflow-x-auto">
            <table className="w-full min-w-[760px] text-left text-sm">
              <thead className="bg-slate-950/40 text-xs text-slate-500">
                <tr>
                  <th className="px-4 py-3">標的</th>
                  <th className="px-4 py-3">策略</th>
                  <th className="px-4 py-3">階段</th>
                  <th className="px-4 py-3 text-right">分數</th>
                  <th className="px-4 py-3 text-right">成交張數</th>
                  <th className="px-4 py-3 text-right">收盤</th>
                  <th className="px-4 py-3 text-right">建議進場區</th>
                  <th className="px-4 py-3 text-right">停損</th>
                  <th className="px-4 py-3 text-right">風險</th>
                </tr>
              </thead>
              <tbody>
                {visibleSignals.map((signal) => (
                  <tr
                    key={signal.id}
                    onClick={() => setSelected(signal)}
                    className={`border-t border-slate-800 transition hover:bg-slate-800/80 ${
                      activeSelected?.id === signal.id ? "bg-emerald-400/5" : ""
                    }`}
                  >
                    <td className="px-4 py-3">
                      <button className="text-left">
                        <div className="font-semibold text-white">
                          {signal.symbol} {signal.name}
                        </div>
                        <div className="mt-0.5 text-xs text-slate-500">
                          {signal.market}
                        </div>
                      </button>
                    </td>
                    <td className="px-4 py-3 text-slate-300">
                      <div>{strategyLabel[signal.strategy]}</div>
                      <div className="mt-1 whitespace-nowrap text-[11px] text-cyan-300/70">
                        壓力 {formatPrice(metricNumber(signal, "latest_peak"))}
                        {" · "}
                        防守 {formatPrice(metricNumber(signal, "latest_trough"))}
                      </div>
                    </td>
                    <td className="px-4 py-3">
                      <LevelBadge level={signal.level} />
                    </td>
                    <td className="px-4 py-3 text-right font-semibold">
                      {signal.score}
                    </td>
                    <td className="px-4 py-3 text-right text-cyan-200">
                      {formatLots(signal)}
                    </td>
                    <td className="px-4 py-3 text-right">{formatPrice(signal.close)}</td>
                    <td className="whitespace-nowrap px-4 py-3 text-right text-emerald-300">
                      {formatEntryZone(signal)}
                    </td>
                    <td className="px-4 py-3 text-right text-rose-300">
                      {formatPrice(signal.stop_price)}
                    </td>
                    <td className="px-4 py-3 text-right">
                      {signal.risk_percent === null
                        ? "—"
                        : `${signal.risk_percent.toFixed(1)}%`}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
            {!loading && visibleSignals.length === 0 && (
              <div className="px-4 py-14 text-center text-sm text-slate-500">
                目前沒有符合條件的訊號。
              </div>
            )}
          </div>
        </article>

        <aside className="rounded-2xl border border-slate-700/70 bg-slate-900/70 p-4 backdrop-blur">
          {activeSelected ? (
            <>
              <div className="mb-4 flex items-start justify-between gap-4">
                <div>
                  <div className="text-xl font-bold">
                    {activeSelected.symbol} {activeSelected.name}
                  </div>
                  <div className="mt-1 text-xs text-slate-500">
                    {strategyLabel[activeSelected.strategy]} ·{" "}
                    {activeSelected.signal_date}
                  </div>
                </div>
                <LevelBadge level={activeSelected.level} />
              </div>
              <div className="overflow-hidden rounded-xl border border-slate-800 bg-slate-950/35">
                <StockChart bars={bars} signal={activeSelected} />
              </div>
              <TrendMetricsPanel signal={activeSelected} />
              <EntryTimingPanel signal={activeSelected} />
              <div className="mt-4 grid grid-cols-2 gap-2 sm:grid-cols-5">
                {[
                  ["建議進場區", formatEntryZone(activeSelected)],
                  ["確認價", formatPrice(activeSelected.trigger_price)],
                  ["成交張數", formatLots(activeSelected)],
                  ["防守價", formatPrice(activeSelected.stop_price)],
                  [
                    "單筆風險",
                    activeSelected.risk_percent === null
                      ? "—"
                      : `${activeSelected.risk_percent.toFixed(1)}%`,
                  ],
                ].map(([label, value]) => (
                  <div key={label} className="rounded-xl bg-slate-800/70 p-3">
                    <div className="text-[11px] text-slate-500">{label}</div>
                    <div className="mt-1 font-semibold">{value}</div>
                  </div>
                ))}
              </div>
              <div className="mt-4 rounded-xl border border-slate-800 bg-slate-950/35 p-3">
                <div className="flex items-center justify-between gap-3">
                  <label
                    htmlFor="capital"
                    className="text-xs font-semibold text-slate-400"
                  >
                    帳戶淨值
                  </label>
                  <input
                    id="capital"
                    type="number"
                    min={100000}
                    max={1_000_000_000_000}
                    step={100000}
                    value={capital}
                    onFocus={(event) => event.currentTarget.select()}
                    onClick={(event) => event.currentTarget.select()}
                    onChange={(event) =>
                      setCapital(
                        Math.min(
                          1_000_000_000_000,
                          Math.max(0, Number(event.target.value)),
                        ),
                      )
                    }
                    className="w-40 rounded-lg border border-slate-700 bg-slate-900 px-3 py-2 text-right text-sm outline-none focus:border-emerald-400"
                  />
                </div>
                <div className="mt-3 flex items-end justify-between">
                  <div className="text-xs text-slate-500">
                    {activeSelected.level === "CONFIRMED"
                      ? "依 1% 帳戶風險試算"
                      : "觀察／轉強階段不配置部位"}
                  </div>
                  <div className="text-lg font-bold text-emerald-300">
                    {positionShares.toLocaleString()} 股
                  </div>
                </div>
              </div>
              {backtest && activeSelected.strategy !== "TREND_CONFIRMATION" && (
                <div className="mt-4 rounded-xl border border-slate-800 bg-slate-950/35 p-3">
                  <div className="flex items-center justify-between">
                    <h2 className="text-xs font-semibold tracking-wider text-slate-400">
                      回測驗證閘門
                    </h2>
                    <span
                      className={`rounded-full px-2 py-1 text-[11px] font-semibold ${
                        backtest.gate_passed
                          ? "bg-emerald-400/10 text-emerald-300"
                          : "bg-amber-400/10 text-amber-300"
                      }`}
                    >
                      {backtest.gate_passed ? "通過" : "研究中"}
                    </span>
                  </div>
                  <div className="mt-3 grid grid-cols-4 gap-2 text-center">
                    {[
                      ["樣本", `${backtest.trades}`],
                      ["勝率", `${(backtest.win_rate * 100).toFixed(1)}%`],
                      [
                        "PF",
                        backtest.profit_factor === null
                          ? "∞"
                          : backtest.profit_factor.toFixed(2),
                      ],
                      ["回撤", `${(backtest.max_drawdown * 100).toFixed(1)}%`],
                    ].map(([label, value]) => (
                      <div key={label}>
                        <div className="text-[10px] text-slate-600">{label}</div>
                        <div className="mt-1 text-sm font-semibold">{value}</div>
                      </div>
                    ))}
                  </div>
                  {!backtest.gate_passed && (
                    <div className="mt-3 text-xs leading-5 text-amber-100/65">
                      {backtest.gate_reasons.join("；")}
                    </div>
                  )}
                </div>
              )}
              <div className="mt-5">
                <h2 className="text-xs font-semibold tracking-wider text-slate-400">
                  訊號依據
                </h2>
                <ul className="mt-3 space-y-2">
                  {visibleReasons(activeSelected).map((reason) => (
                    <li
                      key={reason}
                      className="flex gap-2 text-sm leading-6 text-slate-300"
                    >
                      <span className="mt-2 h-1.5 w-1.5 shrink-0 rounded-full bg-emerald-300" />
                      {reason}
                    </li>
                  ))}
                </ul>
              </div>
              <div className="mt-5 rounded-xl border border-amber-400/20 bg-amber-400/5 p-3 text-xs leading-5 text-amber-100/75">
                {activeSelected.validation_status === "RESEARCH"
                  ? "目前策略尚未通過完整樣本外驗證，只能作為研究訊號。"
                  : "策略已通過驗證閘門；操作仍須依個人風險承受度評估。"}
              </div>
            </>
          ) : (
            <div className="flex min-h-[520px] items-center justify-center text-sm text-slate-500">
              選擇一筆訊號查看圖表與規則。
            </div>
          )}
        </aside>
      </section>
      <footer className="py-6 text-center text-xs text-slate-600">
        依公開教學原則進行平台量化轉譯，非官方授權或背書；不構成投資建議。
      </footer>
    </main>
  );
}
