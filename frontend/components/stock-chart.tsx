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

export function StockChart({ bars, signal }: { bars: Bar[]; signal?: Signal | null }) {
  const containerRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!containerRef.current || bars.length === 0) return;
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

  return <div ref={containerRef} className="w-full" />;
}
