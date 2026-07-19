"""Volume Profile (POC / VAH / VAL / HVN / LVN) — pure functions.

Distributes each candle's volume uniformly across its [low, high] price range
(a simple tick-proxy), buckets the result into fixed-size price bins, then
derives:

  - POC  : the price bin with the highest traded volume.
  - VA   : the Value Area via the classic expand-from-POC algorithm until
           `value_area_pct` of total volume is captured (default 70%).
  - VAH  : the top of the Value Area.
  - VAL  : the bottom of the Value Area.
  - HVN  : High Volume Nodes = local maxima of a 3-bin-smoothed histogram.
  - LVN  : Low  Volume Nodes = local minima of a 3-bin-smoothed histogram.

Bin count is capped (default 100) by aggregating small bins so the per-bar
histogram stays performant for the chart.

Pure: no DB / no IO. Takes a CandleDTO list, returns a plain dict.
"""
from __future__ import annotations

import statistics
from typing import Literal

from ..data.twelvedata import CandleDTO


# Per-symbol bin-size defaults (quote units per bin).
_SYMBOL_BIN_SIZE = {
    "XAU/USD": 1.0,
    "BTC/USD": 50.0,
}
MAX_BINS = 100  # cap; aggregate up if the natural bin count exceeds this


def compute_volume_profile(
    candles: list[CandleDTO],
    bin_size: float | None = None,
    value_area_pct: float = 0.70,
    symbol: str | None = None,
) -> dict:
    """Build a volume profile over the candle list.

    Args:
        candles:        OHLCV candles (any timeframe).
        bin_size:       price units per bin. None -> auto per symbol / 0.1% of
                        median price.
        value_area_pct: fraction of total volume the Value Area must contain.
        symbol:         optional symbol hint for bin_size auto-pick.

    Returns a dict with poc, vah, val, value_area_pct, bins, hvn, lvn.
    """
    if not candles:
        return _empty_profile(value_area_pct)

    lo_global = min(c.low for c in candles)
    hi_global = max(c.high for c in candles)
    if hi_global <= lo_global:
        return _empty_profile(value_area_pct)

    # --- pick bin size ---
    if bin_size is None or bin_size <= 0:
        bin_size = _pick_bin_size(symbol, lo_global, hi_global, candles)

    # If the per-symbol default is too coarse for this particular window (e.g.
    # a tight intraday range that all collapses into 1 bin), shrink it so we get
    # a meaningful histogram. Target ~40-80 bins across the actual range.
    natural_bins = int((hi_global - lo_global) / bin_size) + 1
    if natural_bins < 20:
        bin_size = max((hi_global - lo_global) / 50.0, 1e-6)
        natural_bins = int((hi_global - lo_global) / bin_size) + 1

    # Cap total bins: if too many, widen bin_size so we land <= MAX_BINS.
    if natural_bins > MAX_BINS:
        bin_size = (hi_global - lo_global) / MAX_BINS
        natural_bins = MAX_BINS

    n_bins = max(1, natural_bins)
    # bin[i] covers [lo_global + i*bs, lo_global + (i+1)*bs)
    bins_volume = [0.0] * n_bins
    bins_low = [lo_global + i * bin_size for i in range(n_bins)]
    bins_high = [b + bin_size for b in bins_low]

    # --- distribute each candle's volume across its [low, high] range ---
    for c in candles:
        span = max(c.high - c.low, 1e-9)
        vol = float(c.volume or 0.0)
        if vol <= 0:
            continue
        first_bin = max(0, min(n_bins - 1, int((c.low - lo_global) / bin_size)))
        last_bin = max(0, min(n_bins - 1, int((c.high - lo_global) / bin_size)))
        if first_bin == last_bin:
            bins_volume[first_bin] += vol
            continue
        # uniform distribution across the bins the candle touches
        vol_per_unit = vol / span
        for b in range(first_bin, last_bin + 1):
            lo_overlap = max(c.low, bins_low[b])
            hi_overlap = min(c.high, bins_high[b])
            overlap = max(0.0, hi_overlap - lo_overlap)
            bins_volume[b] += vol_per_unit * overlap

    total_volume = sum(bins_volume)
    if total_volume <= 0:
        # No volume data — fall back to a tick-count proxy (1 per candle per bin touched)
        for c in candles:
            first_bin = max(0, min(n_bins - 1, int((c.low - lo_global) / bin_size)))
            last_bin = max(0, min(n_bins - 1, int((c.high - lo_global) / bin_size)))
            for b in range(first_bin, last_bin + 1):
                bins_volume[b] += 1.0
        total_volume = sum(bins_volume)
        if total_volume <= 0:
            return _empty_profile(value_area_pct)

    # --- POC = argmax volume bin ---
    poc_idx = max(range(n_bins), key=lambda i: bins_volume[i])
    poc_price = (bins_low[poc_idx] + bins_high[poc_idx]) / 2.0

    # --- Value Area via expand-from-POC ---
    vah_idx, val_idx = _value_area(bins_volume, poc_idx, value_area_pct)
    vah_price = (bins_low[vah_idx] + bins_high[vah_idx]) / 2.0
    val_price = (bins_low[val_idx] + bins_high[val_idx]) / 2.0

    # --- HVN / LVN from 3-bin-smoothed histogram ---
    hvn, lvn = _high_low_volume_nodes(bins_volume, bins_low, bins_high, poc_idx)

    bins_out = [
        {
            "price_low": round(bins_low[i], 3),
            "price_high": round(bins_high[i], 3),
            "price_mid": round((bins_low[i] + bins_high[i]) / 2.0, 3),
            "volume": round(bins_volume[i], 3),
            "in_value_area": val_idx <= i <= vah_idx,
            "is_poc": i == poc_idx,
        }
        for i in range(n_bins)
    ]

    return {
        "poc": round(poc_price, 3),
        "vah": round(vah_price, 3),
        "val": round(val_price, 3),
        "value_area_pct": value_area_pct,
        "bin_size": round(bin_size, 4),
        "total_volume": round(total_volume, 3),
        "bins": bins_out,
        "hvn": [round(p, 3) for p in hvn],
        "lvn": [round(p, 3) for p in lvn],
    }


# ---------------------------------------------------------------------------
# Bin-size picker
# ---------------------------------------------------------------------------

def _pick_bin_size(
    symbol: str | None, lo: float, hi: float, candles: list[CandleDTO]
) -> float:
    """Auto-pick a bin size per symbol; default 0.1% of the median price."""
    if symbol and symbol.upper().replace(" ", "") in {
        s.upper().replace("/", "") for s in _SYMBOL_BIN_SIZE
    }:
        # match loosely (XAUUSD == XAU/USD)
        for key, val in _SYMBOL_BIN_SIZE.items():
            if _norm_sym(symbol) == _norm_sym(key):
                return val
    closes = [c.close for c in candles if c.close > 0]
    median = statistics.median(closes) if closes else (lo + hi) / 2.0
    return max(0.01, median * 0.001)  # 0.1% of median


def _norm_sym(s: str) -> str:
    return (s or "").upper().replace("/", "").replace(" ", "").replace("-", "")


# ---------------------------------------------------------------------------
# Value Area (expand from POC)
# ---------------------------------------------------------------------------

def _value_area(
    bins_volume: list[float], poc_idx: int, value_area_pct: float
) -> tuple[int, int]:
    """Classic expand-from-POC: alternate adding the heavier of the
    bin-above-the-VA-top or bin-below-the-VA-bottom until target % is captured.

    Returns (vah_idx, val_idx) (top index, bottom index).
    """
    n = len(bins_volume)
    total = sum(bins_volume)
    if total <= 0 or not (0 < value_area_pct < 1):
        return poc_idx, poc_idx

    target = total * value_area_pct
    hi = poc_idx
    lo = poc_idx
    captured = bins_volume[poc_idx]
    while captured < target and (lo > 0 or hi < n - 1):
        above = bins_volume[hi + 1] if hi + 1 < n else -1.0
        below = bins_volume[lo - 1] if lo - 1 >= 0 else -1.0
        if above < 0 and below < 0:
            break
        if above >= below:
            hi += 1
            captured += above
        else:
            lo -= 1
            captured += below
    return hi, lo  # vah_idx, val_idx


# ---------------------------------------------------------------------------
# HVN / LVN
# ---------------------------------------------------------------------------

def _high_low_volume_nodes(
    bins_volume: list[float],
    bins_low: list[float],
    bins_high: list[float],
    poc_idx: int,
) -> tuple[list[float], list[float]]:
    """HVN = local maxima, LVN = local minima of the 3-bin-smoothed histogram.

    The POC is always added as an HVN. Edge bins are not considered nodes
    (no neighbor on one side).
    """
    n = len(bins_volume)
    if n < 3:
        mid = (bins_low[poc_idx] + bins_high[poc_idx]) / 2.0
        return [mid], []
    smoothed = [
        (bins_volume[i - 1] + bins_volume[i] + bins_volume[i + 1]) / 3.0
        for i in range(1, n - 1)
    ]
    hvn_idx: set[int] = {poc_idx}
    lvn_idx: set[int] = set()
    for j, v in enumerate(smoothed):
        i = j + 1  # original index
        if v > smoothed[j - 1] and v > (smoothed[j + 1] if j + 1 < len(smoothed) else -1):
            hvn_idx.add(i)
        elif v < smoothed[j - 1] and v < (smoothed[j + 1] if j + 1 < len(smoothed) else float("inf")):
            lvn_idx.add(i)
    hvn = sorted({(bins_low[i] + bins_high[i]) / 2.0 for i in hvn_idx if 0 <= i < n})
    lvn = sorted({(bins_low[i] + bins_high[i]) / 2.0 for i in lvn_idx if 0 <= i < n})
    return hvn, lvn


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _empty_profile(value_area_pct: float) -> dict:
    return {
        "poc": None, "vah": None, "val": None,
        "value_area_pct": value_area_pct,
        "bin_size": None, "total_volume": 0.0,
        "bins": [], "hvn": [], "lvn": [],
    }
