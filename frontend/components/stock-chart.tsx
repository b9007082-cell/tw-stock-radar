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

function bollingerBands(bars: Bar[], period = 20, multiplier = 2) {
  return bars.flatMap((bar, index) => {
    if (index < period - 1) return [];
    const slice = bars.slice(index - period + 1, index + 1);
    const middle = slice.reduce((sum, item) => sum + item.close, 0) / period;
    const variance =
      slice.reduce((sum, item) => sum + (item.close - middle) ** 2, 0) / period;
    const deviation = Math.sqrt(variance);
    return [
      {
        time: bar.trade_date as Time,
        upper: middle + deviation * multiplier,
        middle,
        lower: middle - deviation * multiplier,
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

function formatPrice(value: number) {
  return value.toFixed(2);
}

export function StockChart({ bars, signal }: { bars: Bar[]; signal?: Signal | null }) {
  const containerRef = useRef<HTMLDivElement>(null);
  const bands = bollingerBands(bars);
  const latestBand = bands.at(-1);

  useEffect(() => {
    if (!containerRef.current || bars.length === 0) return;
    const activeBands = bollingerBands(bars);
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
    const upperBand = chart.addSeries(LineSeries, {
      color: "#f472b6",
      lineWidth: 1,
      lineStyle: 2,
      priceLineVisible: false,
      lastValueVisible: false,
    });
    upperBand.setData(
      activeBands.map((band) => ({ time: band.time, value: band.upper })),
    );
    const middleBand = chart.addSeries(LineSeries, {
      color: "#c084fc",
      lineWidth: 1,
      lineStyle: 3,
      priceLineVisible: false,
      lastValueVisible: false,
    });
    middleBand.setData(
      activeBands.map((band) => ({ time: band.time, value: band.middle })),
    );
    const lowerBand = chart.addSeries(LineSeries, {
      color: "#38bdf8",
      lineWidth: 1,
      lineStyle: 2,
      priceLineVisible: false,
      lastValueVisible: false,
    });
    lowerBand.setData(
      activeBands.map((band) => ({ time: band.time, value: band.lower })),
    );
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
      {latestBand && (
        <div className="mt-3 rounded-xl border border-fuchsia-400/20 bg-fuchsia-400/5 p-3">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <div>
              <div className="text-xs font-bold tracking-wider text-fuchsia-200">
                布林通道參考線
              </div>
              <div className="mt-1 text-[11px] text-slate-400">
                上軌與下軌越靠近，代表波動壓縮；突破方向出來前先觀察。
              </div>
            </div>
            <div className="text-[11px] text-slate-500">
              20日中線 ± 2倍標準差
            </div>
          </div>
          <div className="mt-3 grid grid-cols-3 gap-2">
            {[
              { label: "上通道", value: latestBand.upper, color: "#f472b6" },
              { label: "中線", value: latestBand.middle, color: "#c084fc" },
              { label: "下通道", value: latestBand.lower, color: "#38bdf8" },
            ].map((band) => (
              <div key={band.label} className="rounded-lg bg-slate-950/35 p-2">
                <div className="flex items-center gap-1.5 text-[10px] text-slate-500">
                  <span
                    className="h-1.5 w-4 rounded-full"
                    style={{ backgroundColor: band.color }}
                  />
                  {band.label}
                </div>
                <div className="mt-1 text-sm font-semibold text-fuchsia-100">
                  {formatPrice(band.value)}
                </div>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
