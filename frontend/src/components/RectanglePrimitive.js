// A lightweight-charts v4 series primitive that draws a filled rectangle between
// two times (x-axis) and two prices (y-axis). Used to render SMC zones
// (FVG / iFVG / Order Block / Breaker) anchored to specific candles.
//
// v4 plugin API: attachPrimitive(primitive) where primitive implements
// ISeriesPrimitive (paneViews()) returning ISeriesPrimitivePaneView[], which
// returns ISeriesPrimitivePaneRenderer[] whose draw(target) paints via fancy-canvas.

import { CanvasRenderingTarget2D } from "fancy-canvas";

/**
 * @param {object} series  the candlestick series (provides priceToCoordinate)
 * @param {object} chart   the chart (provides timeScale().timeToCoordinate)
 * @param {object} opts    { timeFrom, timeTo, priceTop, priceBottom, fill, border, label }
 *   times in UNIX seconds; prices in quote units.
 */
export class RectanglePrimitive {
  constructor(series, chart, opts) {
    this._series = series;
    this._chart = chart;
    this._opts = opts;
    this._paneViews = [new RectanglePaneView(series, chart, opts)];
  }

  updateAllViews() {
    this._paneViews.forEach((v) => v.update());
  }

  paneViews() {
    return this._paneViews;
  }

  update(opts) {
    this._opts = { ...this._opts, ...opts };
    this._paneViews[0].update(this._opts);
  }
}

class RectanglePaneView {
  constructor(series, chart, opts) {
    this._series = series;
    this._chart = chart;
    this._opts = opts;
    this._renderer = new RectangleRenderer(series, chart, opts);
  }

  update(opts) {
    if (opts) this._opts = opts;
    this._renderer.update(this._opts);
  }

  renderer() {
    this._renderer.update(this._opts);
    return this._renderer;
  }
}

class RectangleRenderer {
  constructor(series, chart, opts) {
    this._series = series;
    this._chart = chart;
    this._opts = opts;
  }

  update(opts) {
    this._opts = opts || this._opts;
  }

  draw(target) {
    target.useMediaCoordinateSpace((scope) => {
      const ctx = scope?.ctx;
      const o = this._opts;
      if (!ctx || !o) return;

      const ts = this._chart.timeScale();
      // timeToCoordinate expects the same time type the series was given.
      // Our candle series uses UNIX-seconds numbers.
      const x1 = ts.timeToCoordinate(o.timeFrom);
      const x2 = ts.timeToCoordinate(o.timeTo);
      const y1 = this._series.priceToCoordinate(o.priceTop);
      const y2 = this._series.priceToCoordinate(o.priceBottom);
      if (x1 == null || x2 == null || y1 == null || y2 == null) return;

      const left = Math.min(x1, x2);
      const right = Math.max(x1, x2);
      const top = Math.min(y1, y2);
      const bottom = Math.max(y1, y2);
      const w = Math.max(1, right - left);
      const h = Math.max(1, bottom - top);

      // filled body
      ctx.fillStyle = o.fill || "rgba(0,102,204,0.12)";
      ctx.fillRect(left, top, w, h);

      // border
      if (o.border) {
        ctx.strokeStyle = o.border;
        ctx.lineWidth = o.borderWidth || 1;
        ctx.strokeRect(left, top, w, h);
      }

      // label on the left edge
      if (o.label) {
        ctx.font = "10px system-ui, sans-serif";
        ctx.fillStyle = o.border || o.fill || "#0066cc";
        ctx.textAlign = "left";
        ctx.textBaseline = "top";
        ctx.fillText(o.label, left + 3, top + 2);
      }
    });
  }
}

// Zone colour palette by kind/direction.
export function zoneStyle(kind, dir, mitigated = false) {
  const alpha = mitigated ? 0.06 : 0.13;
  const bAlpha = mitigated ? 0.3 : 0.6;
  const palettes = {
    fvg: {
      bullish: { fill: `rgba(26,143,58,${alpha})`, border: `rgba(26,143,58,${bAlpha})`, label: "FVG" },
      bearish: { fill: `rgba(194,54,75,${alpha})`, border: `rgba(194,54,75,${bAlpha})`, label: "FVG" },
    },
    ifvg: {
      bullish: { fill: `rgba(26,143,58,${alpha * 0.8})`, border: `rgba(26,143,58,${bAlpha})`, label: "iFVG" },
      bearish: { fill: `rgba(194,54,75,${alpha * 0.8})`, border: `rgba(194,54,75,${bAlpha})`, label: "iFVG" },
    },
    order_block: {
      bullish: { fill: `rgba(0,150,199,${alpha})`, border: `rgba(0,150,199,${bAlpha})`, label: "OB" },
      bearish: { fill: `rgba(255,149,0,${alpha})`, border: `rgba(255,149,0,${bAlpha})`, label: "OB" },
    },
    breaker: {
      bullish: { fill: `rgba(88,86,214,${alpha})`, border: `rgba(88,86,214,${bAlpha})`, label: "BKR" },
      bearish: { fill: `rgba(88,86,214,${alpha})`, border: `rgba(88,86,214,${bAlpha})`, label: "BKR" },
    },
  };
  return (palettes[kind] && palettes[kind][dir]) || palettes.fvg.bullish;
}
