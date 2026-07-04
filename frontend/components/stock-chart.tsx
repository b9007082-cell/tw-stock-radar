"use client";

import {
  CandlestickSeries,
  ColorType,
  createChart,
  LineSeries,
  type Time,
} from "lightweight-charts";
import { useEffect, useRef } from "react";

import type { Bar } from "@/lib/types";

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

export function StockChart({ bars }: { bars: Bar[] }) {
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
  }, [bars]);

  return <div ref={containerRef} className="w-full" />;
}

