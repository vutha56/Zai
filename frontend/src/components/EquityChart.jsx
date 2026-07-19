import React, { useEffect, useRef } from "react";
import { createChart, ColorType } from "lightweight-charts";

// Line-series equity curve for backtest results.
export default function EquityChart({ equity = [], height = 360 }) {
  const containerRef = useRef(null);
  const chartRef = useRef(null);
  const seriesRef = useRef(null);

  useEffect(() => {
    if (!containerRef.current) return;
    const chart = createChart(containerRef.current, {
      height,
      autoWidth: true,
      layout: {
        background: { type: ColorType.Solid, color: "transparent" },
        textColor: "#1d1d1f",
        fontFamily: 'system-ui, -apple-system, "Inter", sans-serif',
        fontSize: 12,
      },
      grid: {
        vertLines: { color: "rgba(0,0,0,0.04)" },
        horzLines: { color: "rgba(0,0,0,0.04)" },
      },
      rightPriceScale: { borderColor: "rgba(0,0,0,0.08)" },
      timeScale: { borderColor: "rgba(0,0,0,0.08)", timeVisible: true, secondsVisible: false },
      crosshair: { mode: 0 },
    });
    const series = chart.addAreaSeries({
      lineColor: "#0066cc",
      topColor: "rgba(0, 102, 204, 0.25)",
      bottomColor: "rgba(0, 102, 204, 0.02)",
      lineWidth: 2,
    });
    chartRef.current = chart;
    seriesRef.current = series;
    return () => {
      chart.remove();
      chartRef.current = null;
      seriesRef.current = null;
    };
  }, [height]);

  useEffect(() => {
    if (!seriesRef.current || !equity.length) return;
    const data = equity
      .map((p) => ({
        time: Math.floor(Date.parse(p.t) / 1000),
        value: Number(p.equity),
      }))
      .filter((p) => Number.isFinite(p.time) && Number.isFinite(p.value));
    try {
      seriesRef.current.setData(data);
      chartRef.current?.timeScale().fitContent();
    } catch (err) {
      console.error("EquityChart setData failed:", err);
    }
  }, [equity]);

  return <div ref={containerRef} style={{ height }} />;
}
