"use client";

import { useEffect, useMemo, useState } from "react";

import { api } from "@/lib/api";
import type {
  BacktestReport,
  Bar,
  EntryTimingStatus,
  Signal,
  SignalLevel,
  Summary,
} from "@/lib/types";
import { StockChart } from "@/components/stock-chart";

const updateWorkerUrl = process.env.NEXT_PUBLIC_UPDATE_WORKER_URL ?? "";

const levelLabel: Record<SignalLevel, string> = {
  WATCH: "觀察",
  TRIAL: "試單",
  CONFIRMED: "確認",
};

const strategyLabel: Record<Signal["strategy"], string> = {
  MA_CONVERGENCE: "均線糾結",
  CONSOLIDATION_BREAKOUT: "盤整突破",
  STRONG_PULLBACK: "強勢回檔",
};

const strategyTabs = [
  ["ALL", "全部策略"],
  ["MA_CONVERGENCE", "均線糾結"],
  ["CONSOLIDATION_BREAKOUT", "盤整突破"],
  ["STRONG_PULLBACK", "強勢回檔"],
] as const;

const levelOrder: Record<SignalLevel, number> = {
  CONFIRMED: 0,
  TRIAL: 1,
  WATCH: 2,
};

const timingLabel: Record<EntryTimingStatus, string> = {
  WAIT_CONFIRMATION: "等待確認",
  WAIT_PULLBACK: "等待回測",
  TRIAL_ENTRY: "可試單",
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

function formatPercent(value: number | null, digits = 1) {
  return value == null ? "—" : `${(value * 100).toFixed(digits)}%`;
}

function formatBreakoutDistance(signal: Signal) {
  const distance = metricNumber(signal, "distance_to_breakout");
  if (distance == null) return "—";
  return distance >= 0
    ? `尚差 ${formatPercent(distance)}`
    : `已突破 ${formatPercent(Math.abs(distance))}`;
}

function ConvergenceMetricsPanel({ signal }: { signal: Signal }) {
  if (signal.strategy !== "MA_CONVERGENCE") return null;
  const items = [
    ["均線差距", formatPercent(metricNumber(signal, "ma_spread"))],
    ["距突破價", formatBreakoutDistance(signal)],
    ["量縮程度", formatPercent(metricNumber(signal, "volume_contraction"), 0)],
    ["確認價", formatPrice(signal.trigger_price)],
  ];
  return (
    <div className="mt-4 rounded-xl border border-cyan-400/20 bg-cyan-400/5 p-3">
      <div className="mb-3 text-xs font-bold tracking-wider text-cyan-200">
        均線糾結監測
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

export function Dashboard() {
  const [summary, setSummary] = useState<Summary | null>(null);
  const [signals, setSignals] = useState<Signal[]>([]);
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
    Promise.all([api.summary(), api.signals()])
      .then(([summaryData, signalData]) => {
        setSummary(summaryData);
        setSignals(signalData);
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
        (strategyFilter === "ALL" || signal.strategy === strategyFilter) &&
        (filter === "ALL" || signal.level === filter) &&
        (!needle ||
          signal.symbol.toLowerCase().includes(needle) ||
          signal.name.toLowerCase().includes(needle)),
    );
    if (strategyFilter === "MA_CONVERGENCE") {
      filtered.sort((left, right) => {
        const stageDifference =
          levelOrder[left.level] - levelOrder[right.level];
        if (stageDifference !== 0) return stageDifference;
        const leftDistance = Math.abs(
          metricNumber(left, "distance_to_breakout") ?? Number.POSITIVE_INFINITY,
        );
        const rightDistance = Math.abs(
          metricNumber(right, "distance_to_breakout") ?? Number.POSITIVE_INFINITY,
        );
        return leftDistance - rightDistance || right.score - left.score;
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
    { label: "試單", value: summary?.trial ?? 0, tone: "text-amber-300" },
    { label: "確認", value: summary?.confirmed ?? 0, tone: "text-emerald-300" },
  ];

  const positionShares = useMemo(() => {
    if (
      !activeSelected ||
      activeSelected.entry_price === null ||
      activeSelected.stop_price === null ||
      activeSelected.level === "WATCH"
    ) {
      return 0;
    }
    const perShareRisk =
      activeSelected.entry_price - activeSelected.stop_price;
    if (perShareRisk <= 0) return 0;
    const riskRate = activeSelected.level === "TRIAL" ? 0.005 : 0.01;
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
            均線糾結 × 盤整突破 × 強勢回檔｜規則透明、訊號可回測
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
                      {signal.strategy === "MA_CONVERGENCE" && (
                        <div className="mt-1 whitespace-nowrap text-[11px] text-cyan-300/70">
                          差距 {formatPercent(metricNumber(signal, "ma_spread"))}
                          {" · "}
                          {formatBreakoutDistance(signal)}
                          {" · "}
                          量縮{" "}
                          {formatPercent(
                            metricNumber(signal, "volume_contraction"),
                            0,
                          )}
                        </div>
                      )}
                    </td>
                    <td className="px-4 py-3">
                      <LevelBadge level={signal.level} />
                    </td>
                    <td className="px-4 py-3 text-right font-semibold">
                      {signal.score}
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
                <StockChart bars={bars} />
              </div>
              <ConvergenceMetricsPanel signal={activeSelected} />
              <EntryTimingPanel signal={activeSelected} />
              <div className="mt-4 grid grid-cols-2 gap-2 sm:grid-cols-4">
                {[
                  ["建議進場區", formatEntryZone(activeSelected)],
                  ["確認價", formatPrice(activeSelected.trigger_price)],
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
                    {activeSelected.level === "TRIAL"
                      ? "依 0.5% 風險試算"
                      : activeSelected.level === "CONFIRMED"
                        ? "依 1% 風險試算"
                        : "觀察階段不配置部位"}
                  </div>
                  <div className="text-lg font-bold text-emerald-300">
                    {positionShares.toLocaleString()} 股
                  </div>
                </div>
              </div>
              {backtest && (
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
                  {activeSelected.reasons.map((reason) => (
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
        技術面研究工具，不構成投資建議。所有平台自訂門檻均需以樣本外回測驗證。
      </footer>
    </main>
  );
}
