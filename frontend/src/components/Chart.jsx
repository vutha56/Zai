import React, { useEffect, useRef } from "react";
import { createChart, ColorType } from "lightweight-charts";
import { RectanglePrimitive, zoneStyle } from "./RectanglePrimitive";
import { VolumeProfilePrimitive } from "./VolumeProfilePrimitive";
import { fmtPrice } from "./helpers";

// Candlestick chart with SMC + ICT context overlays:
//  - FVG / iFVG / Order Block / Breaker (time-bounded shaded rectangles)
//  - Previous Daily High/Low + today's developing High/Low (full-width lines)
//  - active signal's entry / SL / TP (dashed lines)
//  - context (ICT layers):
//      * Volume Profile horizontal histogram on the right edge (POC/VAH/VAL lines)
//      * Daily bias badge (CSS overlay, top-left)
//      * BOS / CHoCH / MSS as price lines at the broken swing price
//      * Power-of-3 Asian range as a shaded rectangle
//
// `smc` prop:     { fvgs, ifvgs, order_blocks, breakers, daily }
// `context` prop: { bias, structure, volume_profile, po3 }
export default function Chart({ candles = [], signal = null, smc = null, context = null, height = 420 }) {
  const containerRef = useRef(null);
  const chartRef = useRef(null);
  const seriesRef = useRef(null);
  const linesRef = useRef([]);            // signal price lines (createPriceLine)
  const primitivesRef = useRef([]);       // SMC rectangles (attachPrimitive)
  const dailyLinesRef = useRef([]);       // daily H/L price lines
  const vpPrimitiveRef = useRef(null);    // Volume Profile primitive
  const ctxLinesRef = useRef([]);         // context price lines (POC/VAH/VAL, structure)
  const ctxPrimitivesRef = useRef([]);    // context rectangles (PO3 Asian range)

  // create chart + candlestick series once
  useEffect(() => {
    if (!containerRef.current) return;
    const chart = createChart(containerRef.current, {
      height,
      autoWidth: true,
      layout: {
        background: { type: ColorType.Solid, color: "transparent" },
        textColor: "#1d1d1f",
        fontFamily: 'system-ui, -apple-system, "SF Pro Text", "Inter", sans-serif',
        fontSize: 12,
      },
      grid: {
        vertLines: { color: "rgba(0,0,0,0.04)" },
        horzLines: { color: "rgba(0,0,0,0.04)" },
      },
      rightPriceScale: { borderColor: "rgba(0,0,0,0.08)" },
      timeScale: {
        borderColor: "rgba(0,0,0,0.08)",
        timeVisible: true,
        secondsVisible: false,
      },
      crosshair: { mode: 0 },
    });
    const series = chart.addCandlestickSeries({
      upColor: "#1a8f3a",
      downColor: "#c2364b",
      borderVisible: false,
      wickUpColor: "#1a8f3a",
      wickDownColor: "#c2364b",
    });
    chartRef.current = chart;
    seriesRef.current = series;

    return () => {
      chart.remove();
      chartRef.current = null;
      seriesRef.current = null;
      linesRef.current = [];
      primitivesRef.current = [];
      dailyLinesRef.current = [];
      vpPrimitiveRef.current = null;
      ctxLinesRef.current = [];
      ctxPrimitivesRef.current = [];
    };
  }, [height]);

  // feed candles
  useEffect(() => {
    if (!seriesRef.current || !candles.length) return;
    const data = candles.map((c) => ({
      time: Math.floor(Date.parse(c.ts) / 1000),
      open: c.open,
      high: c.high,
      low: c.low,
      close: c.close,
    }));
    try {
      seriesRef.current.setData(data);
      chartRef.current?.timeScale().fitContent();
    } catch (err) {
      console.error("Chart setData failed:", err);
    }
  }, [candles]);

  // draw SMC zone rectangles + daily H/L lines
  useEffect(() => {
    const series = seriesRef.current;
    if (!series) return;

    // clear previous primitives
    primitivesRef.current.forEach((p) => {
      try { series.detachPrimitive(p); } catch { /* already gone */ }
    });
    primitivesRef.current = [];
    dailyLinesRef.current.forEach((l) => {
      try { series.removePriceLine(l); } catch { /* gone */ }
    });
    dailyLinesRef.current = [];

    if (!smc) return;

    // flatten zones in draw order: breakers (bottom) -> OBs -> iFVGs -> FVGs (top)
    const groups = [
      smc.breakers || [],
      smc.order_blocks || [],
      smc.ifvgs || [],
      smc.fvgs || [],
    ];
    groups.forEach((zones) => {
      zones.forEach((z) => {
        const style = zoneStyle(z.kind, z.dir, z.mitigated);
        try {
          const prim = new RectanglePrimitive(series, chartRef.current, {
            timeFrom: Math.floor(Date.parse(z.ts_from) / 1000),
            timeTo: Math.floor(Date.parse(z.ts_to) / 1000),
            priceTop: z.top,
            priceBottom: z.bottom,
            fill: style.fill,
            border: z.mitigated ? null : style.border,
            label: z.mitigated ? null : style.label,
          });
          series.attachPrimitive(prim);
          primitivesRef.current.push(prim);
        } catch (err) {
          console.error("attachPrimitive failed:", err);
        }
      });
    });

    // daily high/low as full-width lines
    const dl = smc.daily || {};
    const addDaily = (price, color, title) => {
      if (price == null || !Number.isFinite(price)) return;
      try {
        const line = series.createPriceLine({
          price,
          color,
          lineWidth: 1,
          lineStyle: 1, // solid
          axisLabelVisible: true,
          title,
        });
        dailyLinesRef.current.push(line);
      } catch { /* ignore */ }
    };
    addDaily(dl.prev_high, "rgba(26,143,58,0.7)", `PDH ${fmtPrice(dl.prev_high)}`);
    addDaily(dl.prev_low, "rgba(194,54,75,0.7)", `PDL ${fmtPrice(dl.prev_low)}`);
    addDaily(dl.curr_high, "rgba(26,143,58,0.4)", `Today H`);
    addDaily(dl.curr_low, "rgba(194,54,75,0.4)", `Today L`);
  }, [smc]);

  // signal entry/SL/TP lines
  useEffect(() => {
    const series = seriesRef.current;
    if (!series) return;
    linesRef.current.forEach((l) => {
      try { series.removePriceLine(l); } catch { /* gone */ }
    });
    linesRef.current = [];
    if (!signal) return;
    const add = (price, color, title) => {
      const line = series.createPriceLine({
        price,
        color,
        lineWidth: 1,
        lineStyle: 2, // dashed
        axisLabelVisible: true,
        title,
      });
      linesRef.current.push(line);
    };
    add(signal.entry, "#0066cc", `Entry ${fmtPrice(signal.entry)}`);
    add(signal.sl, "#c2364b", `SL ${fmtPrice(signal.sl)}`);
    add(signal.tp, "#1a8f3a", `TP ${fmtPrice(signal.tp)}`);
  }, [signal]);

  // draw ICT context overlays: Volume Profile, BOS/CHoCH/MSS, PO3 Asian range
  useEffect(() => {
    const series = seriesRef.current;
    const chart = chartRef.current;
    if (!series || !chart) return;

    // --- tear down previous context artifacts ---
    if (vpPrimitiveRef.current) {
      try { series.detachPrimitive(vpPrimitiveRef.current); } catch { /* gone */ }
      vpPrimitiveRef.current = null;
    }
    ctxPrimitivesRef.current.forEach((p) => {
      try { series.detachPrimitive(p); } catch { /* gone */ }
    });
    ctxPrimitivesRef.current = [];
    ctxLinesRef.current.forEach((l) => {
      try { series.removePriceLine(l); } catch { /* gone */ }
    });
    ctxLinesRef.current = [];

    if (!context) return;

    // --- Volume Profile: horizontal histogram on the right edge ---
    const vp = context.volume_profile;
    if (vp && Array.isArray(vp.bins) && vp.bins.length) {
      const maxVolume = vp.bins.reduce((m, b) => Math.max(m, b.volume || 0), 0);
      if (maxVolume > 0) {
        try {
          const prim = new VolumeProfilePrimitive(series, chart, {
            bins: vp.bins,
            maxVolume,
            widthPct: 0.22,
          });
          series.attachPrimitive(prim);
          vpPrimitiveRef.current = prim;
        } catch (err) {
          console.error("VolumeProfilePrimitive attach failed:", err);
        }
      }
      // POC / VAH / VAL as full-width price lines (solid, distinct colors)
      const addVPLine = (price, color, title) => {
        if (price == null || !Number.isFinite(price)) return;
        try {
          const line = series.createPriceLine({
            price,
            color,
            lineWidth: 1,
            lineStyle: 0, // solid
            axisLabelVisible: true,
            title,
          });
          ctxLinesRef.current.push(line);
        } catch { /* ignore */ }
      };
      addVPLine(vp.poc, "rgba(255,159,0,0.9)", `POC ${fmtPrice(vp.poc)}`);
      addVPLine(vp.vah, "rgba(0,102,204,0.6)", `VAH ${fmtPrice(vp.vah)}`);
      addVPLine(vp.val, "rgba(0,102,204,0.6)", `VAL ${fmtPrice(vp.val)}`);
    }

    // --- BOS / CHoCH / MSS as price lines at the broken swing price ---
    const st = context.structure;
    if (st) {
      const addStructLine = (ev, color, prefix) => {
        if (!ev || ev.swing_price == null || !Number.isFinite(ev.swing_price)) return;
        const tag = ev.msnr_rejected ? `${prefix}*` : prefix;
        try {
          const line = series.createPriceLine({
            price: ev.swing_price,
            color,
            lineWidth: 1,
            lineStyle: 2, // dashed
            axisLabelVisible: true,
            title: `${tag} ${ev.direction === "bullish" ? "▲" : "▼"}`,
          });
          ctxLinesRef.current.push(line);
        } catch { /* ignore */ }
      };
      addStructLine(st.last_bos, "rgba(88,86,214,0.7)", "BOS");
      addStructLine(st.last_choch, "rgba(255,149,0,0.75)", "CHoCH");
      addStructLine(st.last_mss, "rgba(194,54,75,0.85)", "MSS");
    }

    // --- Power of 3: Asian range as a transparent rectangle spanning the Asia window ---
    const po3 = context.po3;
    if (po3 && po3.asia_high != null && po3.asia_low != null && po3.asia_date) {
      // Asia window = 00:00-07:00 UTC on asia_date. Build the time bounds.
      const day = po3.asia_date; // ISO date YYYY-MM-DD
      if (day) {
        const tFrom = Math.floor(Date.parse(`${day}T00:00:00Z`) / 1000);
        const tTo = Math.floor(Date.parse(`${day}T07:00:00Z`) / 1000);
        // signal-driven fill: long=green, short=red, none=grey
        const fill =
          po3.po3_signal === "long" ? "rgba(26,143,58,0.10)"
          : po3.po3_signal === "short" ? "rgba(194,54,75,0.10)"
          : "rgba(120,120,120,0.07)";
        const border =
          po3.po3_signal === "long" ? "rgba(26,143,58,0.45)"
          : po3.po3_signal === "short" ? "rgba(194,54,75,0.45)"
          : "rgba(120,120,120,0.30)";
        try {
          const prim = new RectanglePrimitive(series, chart, {
            timeFrom: tFrom,
            timeTo: tTo,
            priceTop: po3.asia_high,
            priceBottom: po3.asia_low,
            fill,
            border,
            label: "Asia",
          });
          series.attachPrimitive(prim);
          ctxPrimitivesRef.current.push(prim);
        } catch (err) {
          console.error("PO3 rectangle attach failed:", err);
        }
      }
    }
  }, [context]);

  // Daily bias badge (CSS overlay, top-left). Pure DOM, no chart interaction.
  const bias = context?.bias;
  const biasLabel =
    bias && bias.bias ? `${bias.bias.toUpperCase()}${bias.draw_on_liquidity != null ? ` · DOL ${fmtPrice(bias.draw_on_liquidity)}` : ""}` : "";
  const biasClass =
    bias?.bias === "bullish" ? "bias-badge bias-badge--bull"
    : bias?.bias === "bearish" ? "bias-badge bias-badge--bear"
    : "bias-badge bias-badge--neutral";

  return (
    <div className="chart-mount-wrap" style={{ position: "relative", height }}>
      <div ref={containerRef} className="chart-mount" style={{ height }} />
      {biasLabel && (
        <>
          <div className={biasClass} title={bias?.note || ""}>
            <span className="bias-badge__dot" />
            <span className="bias-badge__label">{biasLabel}</span>
            {bias?.confidence != null && (
              <span className="bias-badge__conf">{Math.round(bias.confidence)}%</span>
            )}
          </div>
          <style>{`
            .bias-badge {
              position: absolute; top: 8px; left: 8px; z-index: 5;
              display: inline-flex; align-items: center; gap: 6px;
              padding: 4px 10px; border-radius: 999px;
              font-size: 12px; font-weight: 600; color: #fff;
              backdrop-filter: blur(4px);
              box-shadow: 0 2px 6px rgba(0,0,0,0.12);
              pointer-events: none;
            }
            .bias-badge--bull  { background: rgba(26,143,58,0.85); }
            .bias-badge--bear  { background: rgba(194,54,75,0.85); }
            .bias-badge--neutral { background: rgba(90,90,95,0.85); }
            .bias-badge__dot { width: 8px; height: 8px; border-radius: 50%; background: #fff; opacity: 0.95; }
            .bias-badge__conf { font-weight: 700; opacity: 0.85; }
          `}</style>
        </>
      )}
    </div>
  );
}
