"""Smart Money Concepts (SMC) level detection — pure functions on candle DTOs.

Detects the classic ICT structures so they can be drawn on the chart:
  - FVG   : 3-candle imbalance (candle[i-1].high < candle[i+1].low for bullish)
  - iFVG  : inverse FVG — a 3-candle gap in the OPPOSITE direction of the move
  - Order Block : last opposite-color candle before a strong displacement
  - Breaker    : an OB that was violated then flipped polarity
  - Previous Daily High/Low + today's developing High/Low

Pure: no DB / no IO. Takes CandleDTO lists, returns plain dicts suitable for JSON.
Each rectangle level exposes {ts_from, ts_to, top, bottom, dir} so the frontend
can draw a time-bounded shaded band.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from typing import Literal

from ..data.twelvedata import CandleDTO
from .crt import atr


# ---------------------------------------------------------------------------
# Data shapes
# ---------------------------------------------------------------------------

@dataclass
class Zone:
    kind: str            # fvg | ifvg | order_block | breaker
    dir: str             # bullish | bearish
    ts_from: datetime    # candle where the zone starts
    ts_to: datetime      # candle where it ends (the candle that formed it + extension)
    top: float
    bottom: float
    mitigated: bool = False   # was price returned into the zone after it formed?


# ---------------------------------------------------------------------------
# FVG / iFVG
# ---------------------------------------------------------------------------

def detect_fvgs(candles: list[CandleDTO], extend_bars: int = 20) -> list[Zone]:
    """Standard 3-candle Fair Value Gaps.

    Bullish FVG: candle[i-1].high < candle[i+1].low  -> gap [high[i-1], low[i+1]]
    Bearish FVG: candle[i-1].low  > candle[i+1].high -> gap [high[i+1], low[i-1]]
    `candle[i]` is the displacement candle in the middle.

    NOTE: a 3-candle imbalance is *either* an FVG or an iFVG depending on trend
    context — see detect_ifvgs. This function flags every imbalance; iFVGs are
    split off in detect_ifvgs based on whether the gap aligns with the local trend.
    """
    return [z for z in _all_imbalances(candles, extend_bars) if z.kind == "fvg"]


def detect_ifvgs(candles: list[CandleDTO], extend_bars: int = 20) -> list[Zone]:
    """Inverse FVGs — 3-candle gaps that form AGAINST the local trend.

    The same 3-candle imbalance geometry as a normal FVG, but classified as iFVG
    when it forms against the short-term trend (20-bar EMA slope). A bullish
    imbalance below a falling EMA, or a bearish imbalance above a rising EMA,
    is treated as an inverse (counter-trend) FVG that tends to act as a fade zone.
    """
    return [z for z in _all_imbalances(candles, extend_bars) if z.kind == "ifvg"]


def _all_imbalances(candles: list[CandleDTO], extend_bars: int) -> list[Zone]:
    """Classify every 3-candle imbalance as fvg (with-trend) or ifvg (counter-trend)."""
    ema = _ema([c.close for c in candles], period=20)
    zones: list[Zone] = []
    for i in range(1, len(candles) - 1):
        a, mid, b = candles[i - 1], candles[i], candles[i + 1]
        if a.high < b.low and mid.close > mid.open:
            # bullish imbalance
            trending_up = ema[i] is not None and ema[i] > (ema[i - 5] if i >= 5 and ema[i - 5] is not None else ema[i])
            kind = "fvg" if trending_up else "ifvg"
            zones.append(Zone(
                kind=kind, dir="bullish",
                ts_from=a.ts, ts_to=_extend(candles, i + 1, extend_bars),
                top=b.low, bottom=a.high,
            ))
        elif a.low > b.high and mid.close < mid.open:
            # bearish imbalance
            trending_down = ema[i] is not None and ema[i] < (ema[i - 5] if i >= 5 and ema[i - 5] is not None else ema[i])
            kind = "fvg" if trending_down else "ifvg"
            zones.append(Zone(
                kind=kind, dir="bearish",
                ts_from=a.ts, ts_to=_extend(candles, i + 1, extend_bars),
                top=a.low, bottom=b.high,
            ))
    return _mark_mitigated(zones, candles)


def _ema(values: list[float], period: int = 20) -> list[float | None]:
    """Simple EMA; returns None for the first (period-1) entries."""
    if not values:
        return []
    k = 2 / (period + 1)
    out: list[float | None] = []
    ema_prev: float | None = None
    for idx, v in enumerate(values):
        if idx < period - 1:
            out.append(None)
            continue
        if ema_prev is None:
            ema_prev = sum(values[:period]) / period
        else:
            ema_prev = v * k + ema_prev * (1 - k)
        out.append(ema_prev)
    return out


# ---------------------------------------------------------------------------
# Order Blocks + Breaker Blocks
# ---------------------------------------------------------------------------

def detect_order_blocks(
    candles: list[CandleDTO],
    displacement_k: float = 1.0,
    extend_bars: int = 20,
) -> list[Zone]:
    """Order blocks: last opposite-color candle before a strong displacement.

    Bullish OB: the last DOWN candle (close<open) immediately before an up-move
    whose body >= displacement_k * ATR.
    Bearish OB: the last UP candle immediately before a down-move of similar size.
    """
    if len(candles) < 5:
        return []
    atrs = atr(candles, period=14)
    zones: list[Zone] = []
    i = 1
    while i < len(candles) - 1:
        cur = candles[i]
        cur_atr = atrs[i] or 1e-9
        body = abs(cur.close - cur.open)
        # bullish displacement
        if cur.close > cur.open and body >= displacement_k * cur_atr:
            ob = _find_ob_before(candles, i, want_down=True)
            if ob is not None:
                zones.append(Zone(
                    kind="order_block", dir="bullish",
                    ts_from=candles[ob].ts, ts_to=_extend(candles, i, extend_bars),
                    top=max(candles[ob].high, candles[ob].open),
                    bottom=min(candles[ob].low, candles[ob].close),
                ))
        # bearish displacement
        elif cur.close < cur.open and body >= displacement_k * cur_atr:
            ob = _find_ob_before(candles, i, want_down=False)
            if ob is not None:
                zones.append(Zone(
                    kind="order_block", dir="bearish",
                    ts_from=candles[ob].ts, ts_to=_extend(candles, i, extend_bars),
                    top=max(candles[ob].high, candles[ob].close),
                    bottom=min(candles[ob].low, candles[ob].open),
                ))
        i += 1
    return _mark_mitigated(zones, candles)


def _find_ob_before(candles: list[CandleDTO], idx: int, want_down: bool) -> int | None:
    """Find the last opposite-color candle at or before idx-1 (the OB origin)."""
    j = idx - 1
    while j >= 0:
        c = candles[j]
        is_down = c.close < c.open
        if (want_down and is_down) or (not want_down and not is_down):
            return j
        j -= 1
    return None


def detect_breakers(
    candles: list[CandleDTO],
    displacement_k: float = 1.0,
    extend_bars: int = 20,
) -> list[Zone]:
    """Breaker blocks: order blocks that were violated, then flipped polarity.

    Simplified breaker: an OB whose zone was later penetrated by a strong
    opposite displacement. The violated OB becomes a breaker of the new direction.
    """
    obs = detect_order_blocks(candles, displacement_k=displacement_k, extend_bars=0)
    if not obs or len(candles) < 6:
        return []
    atrs = atr(candles, period=14)
    breakers: list[Zone] = []
    for ob in obs:
        # find candles after the OB that violate it
        violated_idx = None
        for k in range(1, len(candles)):
            if candles[k].ts <= ob.ts_from:
                continue
            c = candles[k]
            ka = atrs[k] or 1e-9
            body = abs(c.close - c.open)
            strong = body >= displacement_k * ka
            if ob.dir == "bullish" and strong and c.close < c.open and c.close < ob.bottom:
                # bullish OB broken downward -> bearish breaker
                violated_idx = k
                break
            if ob.dir == "bearish" and strong and c.close > c.open and c.close > ob.top:
                # bearish OB broken upward -> bullish breaker
                violated_idx = k
                break
        if violated_idx is not None:
            new_dir = "bearish" if ob.dir == "bullish" else "bullish"
            breakers.append(Zone(
                kind="breaker", dir=new_dir,
                ts_from=ob.ts_from, ts_to=_extend(candles, violated_idx, extend_bars),
                top=ob.top, bottom=ob.bottom,
            ))
    return _mark_mitigated(breakers, candles)


# ---------------------------------------------------------------------------
# Previous / current daily high & low
# ---------------------------------------------------------------------------

def daily_high_low(candles: list[CandleDTO]) -> dict:
    """Compute previous-day and current-day high/low (UTC day boundaries).

    Returns {prev_high, prev_low, curr_high, curr_low, prev_date}.
    """
    if not candles:
        return {"prev_high": None, "prev_low": None, "curr_high": None, "curr_low": None}
    # group by UTC date
    by_day: dict[date, list[CandleDTO]] = {}
    for c in candles:
        d = _as_utc(c.ts).date()
        by_day.setdefault(d, []).append(c)
    days = sorted(by_day.keys())
    if len(days) < 2:
        only = by_day[days[-1]]
        hi = max(c.high for c in only)
        lo = min(c.low for c in only)
        return {"prev_high": None, "prev_low": None,
                "curr_high": hi, "curr_low": lo, "prev_date": None}
    prev_day = days[-2]
    curr_day = days[-1]
    prev = by_day[prev_day]
    curr = by_day[curr_day]
    return {
        "prev_high": max(c.high for c in prev),
        "prev_low": min(c.low for c in prev),
        "curr_high": max(c.high for c in curr),
        "curr_low": min(c.low for c in curr),
        "prev_date": prev_day.isoformat(),
    }


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _extend(candles: list[CandleDTO], idx: int, bars: int) -> datetime:
    """Timestamp `bars` candles after idx (the right edge of the zone)."""
    target = min(len(candles) - 1, idx + bars)
    return candles[target].ts


def _as_utc(ts: datetime) -> datetime:
    if ts.tzinfo:
        return ts
    return ts.replace(tzinfo=timezone.utc)


def _mark_mitigated(zones: list[Zone], candles: list[CandleDTO]) -> list[Zone]:
    """Flag a zone as mitigated if any later candle returned into its price band."""
    for z in zones:
        for c in candles:
            if c.ts <= z.ts_from:
                continue
            if z.bottom <= c.low <= z.top or z.bottom <= c.high <= z.top:
                z.mitigated = True
                break
    return zones


def zone_to_dict(z: Zone) -> dict:
    return {
        "kind": z.kind,
        "dir": z.dir,
        "ts_from": z.ts_from.isoformat(),
        "ts_to": z.ts_to.isoformat(),
        "top": round(z.top, 3),
        "bottom": round(z.bottom, 3),
        "mitigated": z.mitigated,
    }


def all_levels(candles: list[CandleDTO], displacement_k: float = 1.0) -> dict:
    """Compute every SMC level for a candle list — the shape the API returns."""
    return {
        "fvgs":      [zone_to_dict(z) for z in detect_fvgs(candles)],
        "ifvgs":     [zone_to_dict(z) for z in detect_ifvgs(candles)],
        "order_blocks": [zone_to_dict(z) for z in detect_order_blocks(candles, displacement_k=displacement_k)],
        "breakers":  [zone_to_dict(z) for z in detect_breakers(candles, displacement_k=displacement_k)],
        "daily":     daily_high_low(candles),
    }
