"use client";

import { useEffect, useMemo, useState } from "react";

import { api } from "@/lib/api";
import type {
  BacktestReport,
  Bar,
  Signal,
  SignalLevel,
  Summary,
} from "@/lib/types";
import { StockChart } from "@/components/stock-chart";

const levelLabel: Record<SignalLevel, string> = {
  WATCH: "觀察",
  TRIAL: "試單",
  CONFIRMED: "確認",
};

const strategyLabel: Record<Signal["strategy"], string> = {
  CONSOLIDATION_BREAKOUT: "盤整突破",
  STRONG_PULLBACK: "強勢回檔",
};

function formatPrice(value: number | null) {
  return value === null ? "—" : value.toFixed(2);
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

export function Dashboard() {
  const [summary, setSummary] = useState<Summary | null>(null);
  const [signals, setSignals] = useState<Signal[]>([]);
  const [selected, setSelected] = useState<Signal | null>(null);
  const [bars, setBars] = useState<Bar[]>([]);
  const [backtest, setBacktest] = useState<BacktestReport | null>(null);
  const [capital, setCapital] = useState(1_000_000);
  const [filter, setFilter] = useState<SignalLevel | "ALL">("ALL");
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

  useEffect(() => {
    if (!selected) return;
    Promise.all([api.bars(selected.symbol), api.backtest(selected.symbol)])
      .then(([barData, report]) => {
        setBars(barData);
        setBacktest(report);
      })
      .catch(() => {
        setBars([]);
        setBacktest(null);
      });
  }, [selected]);

  const visibleSignals = useMemo(() => {
    const needle = query.trim().toLowerCase();
    return signals.filter(
      (signal) =>
        (filter === "ALL" || signal.level === filter) &&
        (!needle ||
          signal.symbol.toLowerCase().includes(needle) ||
          signal.name.toLowerCase().includes(needle)),
    );
  }, [filter, query, signals]);

  const cards = [
    { label: "今日候選", value: summary?.total_signals ?? 0, tone: "text-white" },
    { label: "觀察", value: summary?.watch ?? 0, tone: "text-blue-300" },
    { label: "試單", value: summary?.trial ?? 0, tone: "text-amber-300" },
    { label: "確認", value: summary?.confirmed ?? 0, tone: "text-emerald-300" },
  ];

  const positionShares = useMemo(() => {
    if (
      !selected ||
      selected.entry_price === null ||
      selected.stop_price === null ||
      selected.level === "WATCH"
    ) {
      return 0;
    }
    const perShareRisk = selected.entry_price - selected.stop_price;
    if (perShareRisk <= 0) return 0;
    const riskRate = selected.level === "TRIAL" ? 0.005 : 0.01;
    return (
      Math.floor((capital * riskRate) / perShareRisk / 1000) * 1000
    );
  }, [capital, selected]);

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
            盤整突破 × 強勢回檔｜規則透明、訊號可回測
          </p>
        </div>
        <div className="text-left text-xs leading-6 text-slate-400 sm:text-right">
          <div>資料日：{summary?.as_of ?? "尚無資料"}</div>
          <div>策略版本：{summary?.strategy_version ?? "—"}</div>
          <div>
            驗證狀態：
            {summary?.strategy_approved ? " 已核准" : " 研究版"}
          </div>
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
          <div className="flex flex-col gap-3 border-b border-slate-700/70 p-4 sm:flex-row sm:items-center sm:justify-between">
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
          <div className="overflow-x-auto">
            <table className="w-full min-w-[760px] text-left text-sm">
              <thead className="bg-slate-950/40 text-xs text-slate-500">
                <tr>
                  <th className="px-4 py-3">標的</th>
                  <th className="px-4 py-3">策略</th>
                  <th className="px-4 py-3">階段</th>
                  <th className="px-4 py-3 text-right">分數</th>
                  <th className="px-4 py-3 text-right">收盤</th>
                  <th className="px-4 py-3 text-right">進場</th>
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
                      selected?.id === signal.id ? "bg-emerald-400/5" : ""
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
                      {strategyLabel[signal.strategy]}
                    </td>
                    <td className="px-4 py-3">
                      <LevelBadge level={signal.level} />
                    </td>
                    <td className="px-4 py-3 text-right font-semibold">
                      {signal.score}
                    </td>
                    <td className="px-4 py-3 text-right">{formatPrice(signal.close)}</td>
                    <td className="px-4 py-3 text-right text-emerald-300">
                      {formatPrice(signal.entry_price)}
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
          {selected ? (
            <>
              <div className="mb-4 flex items-start justify-between gap-4">
                <div>
                  <div className="text-xl font-bold">
                    {selected.symbol} {selected.name}
                  </div>
                  <div className="mt-1 text-xs text-slate-500">
                    {strategyLabel[selected.strategy]} · {selected.signal_date}
                  </div>
                </div>
                <LevelBadge level={selected.level} />
              </div>
              <div className="overflow-hidden rounded-xl border border-slate-800 bg-slate-950/35">
                <StockChart bars={bars} />
              </div>
              <div className="mt-4 grid grid-cols-3 gap-2">
                {[
                  ["參考進場", formatPrice(selected.entry_price)],
                  ["防守價", formatPrice(selected.stop_price)],
                  [
                    "單筆風險",
                    selected.risk_percent === null
                      ? "—"
                      : `${selected.risk_percent.toFixed(1)}%`,
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
                    {selected.level === "TRIAL"
                      ? "依 0.5% 風險試算"
                      : selected.level === "CONFIRMED"
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
                  {selected.reasons.map((reason) => (
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
                {selected.validation_status === "RESEARCH"
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
