// A lightweight-charts v4 series primitive that draws a horizontal volume-profile
// histogram on the right edge of the chart. Each price bin is rendered as a
// horizontal bar from `xStart` (a percentage of the plot width from the right
// edge) extending leftwards, with width proportional to that bin's volume
// relative to the POC bin.
//
// This is the standard way to overlay a price-keyed histogram on a chart whose
// x-axis is time: we don't use a series at all, we paint directly on the canvas
// using priceToCoordinate() for the y position.
//
// v4 plugin API: attachPrimitive(primitive) where primitive implements
// ISeriesPrimitive (paneViews()) returning ISeriesPrimitivePaneView[], which
// returns ISeriesPrimitivePaneRenderer[] whose draw(target) paints via fancy-canvas.

import { CanvasRenderingTarget2D } from "fancy-canvas";

/**
 * @param {object} series  the candlestick series (provides priceToCoordinate)
 * @param {object} chart   the chart (provides timeScale + chartWidth)
 * @param {object} opts    {
 *   bins: [{ price_low, price_high, price_mid, volume, in_value_area, is_poc }],
 *   maxVolume: number,     // precomputed max bin volume (POC)
 *   widthPct: number,      // 0..1 — fraction of plot width the bars occupy (default 0.22)
 *   align: "right"         // bars anchored to the right edge
 * }
 */
export class VolumeProfilePrimitive {
  constructor(series, chart, opts) {
    this._series = series;
    this._chart = chart;
    this._opts = opts;
    this._paneViews = [new VolumeProfilePaneView(series, chart, opts)];
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

class VolumeProfilePaneView {
  constructor(series, chart, opts) {
    this._series = series;
    this._chart = chart;
    this._opts = opts;
    this._renderer = new VolumeProfileRenderer(series, chart, opts);
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

class VolumeProfileRenderer {
  constructor(series, chart, opts) {
    this._series = series;
    this._chart = chart;
    this._opts = opts;
  }

  update(opts) {
    this._opts = opts || this._opts;
  }

  draw(target) {
    const o = this._opts;
    if (!o || !o.bins || !o.bins.length) return;
    target.useMediaCoordinateSpace((scope) => {
      const ctx = scope?.ctx;
      if (!ctx) return;
      const width = scope?.mediaSize?.width ?? 0;
      const maxVol = o.maxVolume || Math.max(...o.bins.map((b) => b.volume || 0));
      if (!maxVol || maxVol <= 0) return;
      const widthPct = o.widthPct == null ? 0.22 : o.widthPct;
      const maxBarWidth = width * widthPct;
      const rightEdge = width; // bars grow leftwards from the right edge
      const gap = 0.6; // px between adjacent bins

      for (const bin of o.bins) {
        const yTop = this._series.priceToCoordinate(bin.price_high);
        const yBot = this._series.priceToCoordinate(bin.price_low);
        if (yTop == null || yBot == null) continue;
        const top = Math.min(yTop, yBot);
        const h = Math.max(0.5, Math.abs(yBot - yTop) - gap);
        const vol = bin.volume || 0;
        const w = Math.max(0, (vol / maxVol) * maxBarWidth);
        if (w < 0.2) continue;
        ctx.fillStyle = vpBarColor(bin);
        ctx.fillRect(rightEdge - w, top, w, h);
      }
    });
  }
}

// Color a volume-profile bin by its position relative to the Value Area.
// POC = bright/strong, inside VA = medium, outside VA = dim.
export function vpBarColor(bin) {
  if (bin.is_poc) return "rgba(255, 159, 0, 0.85)"; // bright orange — the POC
  if (bin.in_value_area) return "rgba(0, 102, 204, 0.45)"; // medium blue — VA
  return "rgba(120, 120, 120, 0.22)"; // dim grey — outside VA
}
