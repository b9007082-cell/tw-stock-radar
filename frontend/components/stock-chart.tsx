"use client";

import {
  CandlestickSeries,
  ColorType,
  createChart,
  createSeriesMarkers,
  LineSeries,
  type Time,
} from "lightweight-charts";
import { useEffect, useRef } from "react";

import type { Bar, Signal } from "@/lib/types";

type GannLevel = {
  key: string;
  label: string;
  value: number;
  color: string;
  lineWidth: 1 | 2;
};

type GannAngleLine = {
  key: string;
  label: string;
  color: string;
  lineWidth: 1 | 2;
  data: { time: Time; value: number }[];
};

type GannLineGroup = {
  startIndex: number;
  endIndex: number;
  high?: number;
  low?: number;
  position?: number;
  anchor?: number;
  anchorLabel?: string;
  priceBarRatio?: number;
  levels: GannLevel[];
  angleLines?: GannAngleLine[];
};

type GannSquareGroup = GannLineGroup & {
  anchorLabel: string;
  priceBarRatio: number;
  angleLines: GannAngleLine[];
};

function movingAverage(bars: Bar[], period: number) {
  return bars.flatMap((bar, index) => {
    if (index < period - 1) return [];
    const slice = bars.slice(index - period + 1, index + 1);
    return [
      {
        time: bar.trade_date as Time,
        value: slice.reduce((sum, item) => sum + item.close, 0) / period,
      },
    ];
  });
}

function signalMarker(signal: Signal) {
  if (signal.level === "CONFIRMED") {
    return {
      time: signal.signal_date as Time,
      position: "belowBar" as const,
      color: "#4ee0a0",
      shape: "arrowUp" as const,
      text: "買",
    };
  }
  if (signal.level === "TRIAL") {
    return {
      time: signal.signal_date as Time,
      position: "belowBar" as const,
      color: "#f5b942",
      shape: "circle" as const,
      text: "試",
    };
  }
  return {
    time: signal.signal_date as Time,
    position: "belowBar" as const,
    color: "#6ea8fe",
    shape: "circle" as const,
    text: "等",
  };
}

function metricNumber(signal: Signal | null | undefined, key: string) {
  const value = signal?.metrics[key];
  return typeof value === "number" ? value : null;
}

function formatPrice(value: number) {
  return value.toFixed(2);
}

function buildGannBox(bars: Bar[], signal?: Signal | null): GannLineGroup | null {
  if (bars.length < 2) return null;
  const metricPeak = metricNumber(signal, "latest_peak");
  const metricTrough = metricNumber(signal, "latest_trough");
  const metricPeakIndex = metricNumber(signal, "latest_peak_index");
  const metricTroughIndex = metricNumber(signal, "latest_trough_index");
  const fallbackStart = Math.max(0, bars.length - 60);
  const fallbackBars = bars.slice(fallbackStart);
  const fallbackHigh = Math.max(...fallbackBars.map((bar) => bar.high));
  const fallbackLow = Math.min(...fallbackBars.map((bar) => bar.low));

  const high =
    metricPeak != null && metricTrough != null && metricPeak > metricTrough
      ? metricPeak
      : fallbackHigh;
  const low =
    metricPeak != null && metricTrough != null && metricPeak > metricTrough
      ? metricTrough
      : fallbackLow;
  const range = high - low;
  if (range <= 0) return null;

  const anchorIndex =
    metricPeakIndex != null && metricTroughIndex != null
      ? Math.max(0, Math.min(metricPeakIndex, metricTroughIndex))
      : fallbackStart;
  const startIndex = Math.min(Math.floor(anchorIndex), bars.length - 1);
  const latestClose = bars[bars.length - 1].close;
  const position = ((latestClose - low) / range) * 100;
  const endIndex = bars.length - 1;
  const windowLength = Math.max(8, endIndex - startIndex);
  const priceBarRatio = range / windowLength;
  const anchorIsLow = latestClose >= low;
  const anchor = anchorIsLow ? low : high;
  const directionalRatio = anchorIsLow ? priceBarRatio : -priceBarRatio;
  const makeAngleData = (slope: number) =>
    bars.slice(startIndex, endIndex + 1).map((bar, offset) => ({
      time: bar.trade_date as Time,
      value: anchor + slope * offset,
    }));
  const levels: GannLevel[] = [
    {
      key: "gann-100",
      label: "上緣 100%",
      value: high,
      color: "#a78bfa",
      lineWidth: 2,
    },
    {
      key: "gann-75",
      label: "75%",
      value: low + range * 0.75,
      color: "#818cf8",
      lineWidth: 1,
    },
    {
      key: "gann-50",
      label: "中線 50%",
      value: low + range * 0.5,
      color: "#fbbf24",
      lineWidth: 2,
    },
    {
      key: "gann-25",
      label: "25%",
      value: low + range * 0.25,
      color: "#38bdf8",
      lineWidth: 1,
    },
    {
      key: "gann-0",
      label: "下緣 0%",
      value: low,
      color: "#a78bfa",
      lineWidth: 2,
    },
  ];
  const rawAngleLines: GannAngleLine[] = [
    {
      key: "box-1x1",
      label: "箱體 1x1 主線",
      color: "#fb7185",
      lineWidth: 2,
      data: makeAngleData(directionalRatio),
    },
    {
      key: "box-2x1",
      label: "箱體 2x1 快線",
      color: "#f97316",
      lineWidth: 1,
      data: makeAngleData(directionalRatio * 2),
    },
    {
      key: "box-1x2",
      label: "箱體 1x2 慢線",
      color: "#38bdf8",
      lineWidth: 1,
      data: makeAngleData(directionalRatio * 0.5),
    },
  ];
  const angleLines: GannAngleLine[] = rawAngleLines.map((line) => ({
    ...line,
    data: line.data.filter((point) => point.value > 0),
  }));

  return {
    startIndex,
    endIndex,
    high,
    low,
    position,
    anchor,
    anchorLabel: anchorIsLow ? "低點起算" : "高點起算",
    priceBarRatio,
    levels,
    angleLines,
  };
}

function buildGannSquare(bars: Bar[], signal?: Signal | null): GannSquareGroup | null {
  if (bars.length < 12) return null;
  const metricPeak = metricNumber(signal, "latest_peak");
  const metricTrough = metricNumber(signal, "latest_trough");
  const metricPeakIndex = metricNumber(signal, "latest_peak_index");
  const metricTroughIndex = metricNumber(signal, "latest_trough_index");
  const fallbackStart = Math.max(0, bars.length - 60);
  const fallbackBars = bars.slice(fallbackStart);
  const fallbackHigh = Math.max(...fallbackBars.map((bar) => bar.high));
  const fallbackLow = Math.min(...fallbackBars.map((bar) => bar.low));

  const high =
    metricPeak != null && metricTrough != null && metricPeak > metricTrough
      ? metricPeak
      : fallbackHigh;
  const low =
    metricPeak != null && metricTrough != null && metricPeak > metricTrough
      ? metricTrough
      : fallbackLow;
  const range = high - low;
  if (range <= 0) return null;

  const hasMetricAnchors =
    metricPeakIndex != null &&
    metricTroughIndex != null &&
    metricPeak != null &&
    metricTrough != null &&
    metricPeak > metricTrough;
  const anchorIndex = hasMetricAnchors
    ? Math.max(0, Math.min(Math.floor(metricPeakIndex), Math.floor(metricTroughIndex)))
    : fallbackStart;
  const endIndex = bars.length - 1;
  const startIndex = Math.min(anchorIndex, Math.max(0, endIndex - 8));
  const windowLength = Math.max(8, endIndex - startIndex);
  const priceBarRatio = range / windowLength;
  const latestClose = bars[endIndex].close;
  const anchorIsLow = latestClose >= low;
  const anchor = anchorIsLow ? low : high;
  const anchorLabel = anchorIsLow ? "低點起算" : "高點起算";

  const makeAngleData = (slope: number) =>
    bars.slice(startIndex, endIndex + 1).map((bar, offset) => ({
      time: bar.trade_date as Time,
      value: anchor + slope * offset,
    }));
  const levels: GannLevel[] = [
    {
      key: "square-top",
      label: "正方上緣",
      value: high,
      color: "#f0abfc",
      lineWidth: 2,
    },
    {
      key: "square-75",
      label: "75%",
      value: low + range * 0.75,
      color: "#e879f9",
      lineWidth: 1,
    },
    {
      key: "square-mid",
      label: "50%",
      value: low + range * 0.5,
      color: "#fbbf24",
      lineWidth: 2,
    },
    {
      key: "square-25",
      label: "25%",
      value: low + range * 0.25,
      color: "#67e8f9",
      lineWidth: 1,
    },
    {
      key: "square-bottom",
      label: "正方下緣",
      value: low,
      color: "#22d3ee",
      lineWidth: 2,
    },
  ];
  const directionalRatio = anchorIsLow ? priceBarRatio : -priceBarRatio;
  const rawAngleLines: GannAngleLine[] = [
    {
      key: "square-1x1",
      label: "1x1 主角度線",
      color: "#fb7185",
      lineWidth: 2,
      data: makeAngleData(directionalRatio),
    },
    {
      key: "square-2x1",
      label: "2x1 快線",
      color: "#f97316",
      lineWidth: 1,
      data: makeAngleData(directionalRatio * 2),
    },
    {
      key: "square-1x2",
      label: "1x2 慢線",
      color: "#38bdf8",
      lineWidth: 1,
      data: makeAngleData(directionalRatio * 0.5),
    },
    {
      key: "square-reverse-1x1",
      label: "反向 1x1",
      color: "#a78bfa",
      lineWidth: 1,
      data: makeAngleData(-directionalRatio),
    },
  ];
  const angleLines: GannAngleLine[] = rawAngleLines.map((line) => ({
    ...line,
    data: line.data.filter((point) => point.value > 0),
  }));

  return {
    startIndex,
    endIndex,
    high,
    low,
    anchor,
    anchorLabel,
    priceBarRatio,
    levels,
    angleLines,
  };
}

export function StockChart({ bars, signal }: { bars: Bar[]; signal?: Signal | null }) {
  const containerRef = useRef<HTMLDivElement>(null);
  const gannBox = buildGannBox(bars, signal);
  const gannSquare = buildGannSquare(bars, signal);

  useEffect(() => {
    if (!containerRef.current || bars.length === 0) return;
    const activeGannBox = buildGannBox(bars, signal);
    const activeGannSquare = buildGannSquare(bars, signal);
    const chart = createChart(containerRef.current, {
      height: 360,
      layout: {
        background: { type: ColorType.Solid, color: "transparent" },
        textColor: "#8d98aa",
        attributionLogo: false,
      },
      grid: {
        vertLines: { color: "rgba(38, 50, 73, 0.42)" },
        horzLines: { color: "rgba(38, 50, 73, 0.42)" },
      },
      rightPriceScale: { borderColor: "#263249" },
      timeScale: { borderColor: "#263249", timeVisible: false },
    });
    const candles = chart.addSeries(CandlestickSeries, {
      upColor: "#ff6675",
      downColor: "#4ee0a0",
      borderVisible: false,
      wickUpColor: "#ff6675",
      wickDownColor: "#4ee0a0",
    });
    candles.setData(
      bars.map((bar) => ({
        time: bar.trade_date as Time,
        open: bar.open,
        high: bar.high,
        low: bar.low,
        close: bar.close,
      })),
    );
    if (signal) {
      createSeriesMarkers(candles, [signalMarker(signal)]);
      if (signal.trigger_price != null) {
        candles.createPriceLine({
          price: signal.trigger_price,
          color: "#4ee0a0",
          lineWidth: 1,
          lineStyle: 2,
          axisLabelVisible: true,
          title: "確認價",
        });
      }
      if (signal.stop_price != null) {
        candles.createPriceLine({
          price: signal.stop_price,
          color: "#fb7185",
          lineWidth: 1,
          lineStyle: 2,
          axisLabelVisible: true,
          title: "停損",
        });
      }
    }
    const ma5 = chart.addSeries(LineSeries, {
      color: "#f5b942",
      lineWidth: 2,
      priceLineVisible: false,
      lastValueVisible: false,
    });
    ma5.setData(movingAverage(bars, 5));
    const ma20 = chart.addSeries(LineSeries, {
      color: "#6ea8fe",
      lineWidth: 2,
      priceLineVisible: false,
      lastValueVisible: false,
    });
    ma20.setData(movingAverage(bars, 20));
    const drawGannLines = (group: GannLineGroup, titlePrefix: string) => {
      const startTime = bars[group.startIndex].trade_date as Time;
      const endTime = bars[group.endIndex].trade_date as Time;
      group.levels.forEach((level) => {
        const line = chart.addSeries(LineSeries, {
          color: level.color,
          lineWidth: level.lineWidth,
          lineStyle: 2,
          priceLineVisible: false,
          lastValueVisible: false,
        });
        line.setData([
          { time: startTime, value: level.value },
          { time: endTime, value: level.value },
        ]);
        candles.createPriceLine({
          price: level.value,
          color: level.color,
          lineWidth: level.lineWidth,
          lineStyle: 2,
          axisLabelVisible: true,
          title: `${titlePrefix}${level.label}`,
        });
      });
      group.angleLines?.forEach((angleLine) => {
        if (angleLine.data.length < 2) return;
        const line = chart.addSeries(LineSeries, {
          color: angleLine.color,
          lineWidth: angleLine.lineWidth,
          lineStyle: 1,
          priceLineVisible: false,
          lastValueVisible: false,
        });
        line.setData(angleLine.data);
      });
    };
    if (activeGannBox) drawGannLines(activeGannBox, "江恩箱");
    if (activeGannSquare) drawGannLines(activeGannSquare, "江恩");
    chart.timeScale().fitContent();

    const observer = new ResizeObserver(([entry]) => {
      chart.applyOptions({ width: entry.contentRect.width });
    });
    observer.observe(containerRef.current);
    return () => {
      observer.disconnect();
      chart.remove();
    };
  }, [bars, signal]);

  return (
    <div>
      <div ref={containerRef} className="w-full" />
      {gannBox && (
        <div className="mt-3 rounded-xl border border-violet-400/20 bg-violet-400/5 p-3">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <div>
              <div className="text-xs font-bold tracking-wider text-violet-200">
                江恩箱參考線
              </div>
              <div className="mt-1 text-[11px] text-slate-400">
                目前位階 {(gannBox.position ?? 0).toFixed(0)}%｜箱體{" "}
                {formatPrice(gannBox.low ?? 0)}～{formatPrice(gannBox.high ?? 0)}
              </div>
            </div>
            <div className="text-[11px] text-slate-500">
              {gannBox.anchorLabel}｜含1x1 / 2x1 / 1x2角度線
            </div>
          </div>
          <div className="mt-3 grid grid-cols-2 gap-2 sm:grid-cols-5">
            {gannBox.levels.map((level) => (
              <div key={level.key} className="rounded-lg bg-slate-950/35 p-2">
                <div className="flex items-center gap-1.5 text-[10px] text-slate-500">
                  <span
                    className="h-1.5 w-4 rounded-full"
                    style={{ backgroundColor: level.color }}
                  />
                  {level.label}
                </div>
                <div className="mt-1 text-sm font-semibold text-violet-100">
                  {formatPrice(level.value)}
                </div>
              </div>
            ))}
          </div>
        </div>
      )}
      {gannSquare && (
        <div className="mt-3 rounded-xl border border-fuchsia-400/20 bg-fuchsia-400/5 p-3">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <div>
              <div className="text-xs font-bold tracking-wider text-fuchsia-200">
                江恩正方形參考線
              </div>
              <div className="mt-1 text-[11px] text-slate-400">
                {gannSquare.anchorLabel}｜價格/K棒比{" "}
                {formatPrice(gannSquare.priceBarRatio)}｜參考主要高低點框線
              </div>
            </div>
            <div className="text-[11px] text-slate-500">
              站上1x1偏強，跌破1x1轉弱；快慢線看延伸力道
            </div>
          </div>
          <div className="mt-3 grid grid-cols-2 gap-2 sm:grid-cols-5">
            {gannSquare.levels.map((level) => (
              <div key={level.key} className="rounded-lg bg-slate-950/35 p-2">
                <div className="flex items-center gap-1.5 text-[10px] text-slate-500">
                  <span
                    className="h-1.5 w-4 rounded-full"
                    style={{ backgroundColor: level.color }}
                  />
                  {level.label}
                </div>
                <div className="mt-1 text-sm font-semibold text-fuchsia-100">
                  {formatPrice(level.value)}
                </div>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
