"""ICT Daily Bias + Draw on Liquidity (DOL) and Power of 3 — pure functions.

Layer 1 — Daily Bias:
  - Rule Set A (close-based): last closed D1 closes above prior day high -> bullish,
    below prior day low -> bearish, else neutral.
  - DOL = nearest unswept swing high (bullish) / low (bearish) beyond current price.
  - bias_score amplifier: +1 if matches H4 trend (count up/down candles),
    +1 if the bias formed inside a killzone.

Layer 4 — Power of 3 (Asia accumulation -> London Judas sweep -> reclaim):
  - Asia session = 00:00-07:00 UTC (matches crt.trading_session).
  - London KZ = 07:00-10:00 UTC (matches crt.KILLZONES).
  - Bullish PO3: London wicks below asia_low then closes back above -> "long".
  - Bearish PO3: London wicks above asia_high then closes back below -> "short".

Pure: no DB / no IO. Takes CandleDTO lists, returns plain dicts suitable for JSON.
"""
from __future__ import annotations

import logging
from datetime import date, datetime, timezone
from typing import Literal

from ..config import settings
from ..data.twelvedata import CandleDTO
from .crt import killzone_of

log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Layer 1: Daily Bias + Draw on Liquidity
# ---------------------------------------------------------------------------

def to_daily(candles: list[CandleDTO]) -> list[CandleDTO]:
    """Aggregate intraday candles into D1 candles by UTC date.

    open=first, high=max, low=min, close=last, volume=sum.
    Returns oldest-first. The D1 candle's ts is set to the date at 00:00 UTC.
    """
    if not candles:
        return []
    by_day: dict[date, list[CandleDTO]] = {}
    order: list[date] = []
    for c in candles:
        d = _as_utc(c.ts).date()
        if d not in by_day:
            by_day[d] = []
            order.append(d)
        by_day[d].append(c)
    out: list[CandleDTO] = []
    for d in order:  # preserve insertion order = chronological for sorted input
        day_candles = by_day[d]
        out.append(CandleDTO(
            ts=datetime(d.year, d.month, d.day, tzinfo=timezone.utc),
            open=day_candles[0].open,
            high=max(c.high for c in day_candles),
            low=min(c.low for c in day_candles),
            close=day_candles[-1].close,
            volume=sum((c.volume or 0.0) for c in day_candles),
        ))
    out.sort(key=lambda c: c.ts)
    return out


def compute_daily_bias(
    daily_candles: list[CandleDTO],
    h4_candles: list[CandleDTO] | None = None,
    current_price: float | None = None,
) -> dict:
    """Compute daily bias + draw on liquidity from D1 candles.

    Args:
        daily_candles: D1 candles (use `to_daily` to roll up intraday).
        h4_candles:    optional H4 (or intraday) candles for the trend amplifier.
        current_price: optional live/last close for DOL anchoring; defaults to
                       the last D1 close.

    Returns:
        {bias, method, prev_day_high, prev_day_low, draw_on_liquidity, confidence,
         score_boosters, note}
    """
    if len(daily_candles) < 3:
        return {
            "bias": "neutral",
            "method": "insufficient_data",
            "prev_day_high": None,
            "prev_day_low": None,
            "draw_on_liquidity": None,
            "confidence": 0.0,
            "score_boosters": [],
            "note": "Need >=3 D1 candles for bias.",
        }

    # Last CLOSED D1 vs prior day's range. The final candle in the list may be
    # today's still-forming candle, so compare the second-to-last close against
    # the third-to-last day's range when we have >=3 candles. With exactly the
    # rolled-up history we treat the last fully-closed day as `last_closed`.
    last_closed = daily_candles[-2]
    prior_day = daily_candles[-3]
    last_close = last_closed.close
    prev_high = prior_day.high
    prev_low = prior_day.low

    # --- Rule Set A: close-based ---
    if last_close > prev_high:
        bias: Literal["bullish", "bearish", "neutral"] = "bullish"
        method = "close_above_prior_high"
    elif last_close < prev_low:
        bias = "bearish"
        method = "close_below_prior_low"
    else:
        bias = "neutral"
        method = "inside_prior_range"

    # --- Base confidence from how far beyond the range price closed (ATR-relative) ---
    day_range = max(prev_high - prev_low, 1e-9)
    if bias == "bullish":
        penetration = max(0.0, last_close - prev_high) / day_range
    elif bias == "bearish":
        penetration = max(0.0, prev_low - last_close) / day_range
    else:
        penetration = 0.0
    base_conf = _clip(40.0 + penetration * 60.0, 0.0, 80.0)

    # --- Amplifiers ---
    boosters: list[str] = []
    score_boost = 0
    h4_trend = _h4_trend(h4_candles) if h4_candles else None
    if h4_trend and h4_trend == bias:
        boosters.append("matches_h4_trend")
        score_boost += 1
    kz = killzone_of(last_closed.ts)
    if kz:
        boosters.append(f"in_killzone:{kz}")
        score_boost += 1

    confidence = _clip(base_conf + score_boost * 10.0, 0.0, 100.0)

    # --- Draw on Liquidity: nearest unswept swing beyond current price ---
    price = current_price if current_price is not None else last_close
    dol = _draw_on_liquidity(daily_candles, bias, price)

    note = {
        "bullish": "D1 close above prior high — bullish bias; DOL = next swing high.",
        "bearish": "D1 close below prior low — bearish bias; DOL = next swing low.",
        "neutral": "D1 close inside prior range — neutral / no clear bias.",
    }[bias]

    return {
        "bias": bias,
        "method": method,
        "prev_day_high": _round(prev_high),
        "prev_day_low": _round(prev_low),
        "last_close": _round(last_close),
        "draw_on_liquidity": _round(dol) if dol is not None else None,
        "confidence": round(confidence, 1),
        "score_boosters": boosters,
        "h4_trend": h4_trend,
        "note": note,
    }


def _draw_on_liquidity(
    daily_candles: list[CandleDTO], bias: str, current_price: float
) -> float | None:
    """Nearest unswept swing high (bullish) / low (bearish) beyond current price.

    A swing is "unswept" if no later candle wicked through it. We scan pivots
    using a 3-bar fractal over the D1 series and pick the nearest one strictly
    above (bullish) / below (bearish) the current price.
    """
    if bias == "neutral" or len(daily_candles) < 5:
        return None
    pivots: list[tuple[int, float, str]] = []  # (idx, price, type)
    for i in range(1, len(daily_candles) - 1):
        prev_c = daily_candles[i - 1]
        cur = daily_candles[i]
        nxt = daily_candles[i + 1]
        if cur.high > prev_c.high and cur.high > nxt.high:
            pivots.append((i, cur.high, "high"))
        if cur.low < prev_c.low and cur.low < nxt.low:
            pivots.append((i, cur.low, "low"))
    if not pivots:
        return None

    candidates = []
    for idx, price, ptype in pivots:
        # unswept: no later candle's high/low breaches this pivot
        if ptype == "high" and bias == "bullish":
            swept = any(daily_candles[j].high > price for j in range(idx + 1, len(daily_candles)))
            if not swept and price > current_price:
                candidates.append((idx, price))
        elif ptype == "low" and bias == "bearish":
            swept = any(daily_candles[j].low < price for j in range(idx + 1, len(daily_candles)))
            if not swept and price < current_price:
                candidates.append((idx, price))
    if not candidates:
        return None
    # nearest to current price
    candidates.sort(key=lambda ip: abs(ip[1] - current_price))
    return candidates[0][1]


def _h4_trend(h4_candles: list[CandleDTO] | None) -> Literal["bullish", "bearish", "neutral"] | None:
    """Simple up/down-candle count over the last ~20 H4 candles."""
    if not h4_candles or len(h4_candles) < 5:
        return None
    window = h4_candles[-20:]
    ups = sum(1 for c in window if c.close > c.open)
    downs = len(window) - ups
    if ups >= downs * 1.3:
        return "bullish"
    if downs >= ups * 1.3:
        return "bearish"
    return "neutral"


# ---------------------------------------------------------------------------
# Layer 4: Power of 3 (Asian range -> London Judas sweep -> reclaim)
# ---------------------------------------------------------------------------

# Asia accumulation window (UTC) — matches crt.trading_session's Asia block.
ASIA_START_HOUR = 0
ASIA_END_HOUR = 7
# London manipulation window (UTC) — matches crt.KILLZONES London entry.
LONDON_START_HOUR = 7
LONDON_END_HOUR = 10


def detect_power_of_3(candles: list[CandleDTO], timeframe: str = "") -> dict:
    """Detect ICT Power of 3 over the most recent trading day in `candles`.

    Asia (00-07 UTC) sets the range; London (07-10 UTC) sweeps + reclaims it.
    Returns the asia range, what London swept, and a po3_signal ("long"/"short"/None).

    On very wide Asian ranges (> max_range_pct of asia_low) we assume the day is
    already trending and skip — configurable via settings.crt_po3_max_range_pct.
    """
    if not candles:
        return _empty_po3("no candles")

    # Work on the most recent UTC date present in the candle series that has
    # BOTH an Asia and a London session recorded (so a partial today with only
    # Asian candles falls back to yesterday).
    candles = list(candles)
    prior_days = sorted({_as_utc(c.ts).date() for c in candles}, reverse=True)
    last_day = None
    day_candles: list[CandleDTO] = []
    for d in prior_days:
        dc = [c for c in candles if _as_utc(c.ts).date() == d]
        asia_d = [c for c in dc if ASIA_START_HOUR <= _as_utc(c.ts).hour < ASIA_END_HOUR]
        london_d = [c for c in dc if LONDON_START_HOUR <= _as_utc(c.ts).hour < LONDON_END_HOUR]
        if len(dc) >= 4 and asia_d and london_d:
            last_day = d
            day_candles = dc
            break
    if last_day is None:
        return _empty_po3("no day with both Asia and London sessions in the window")

    asia = [c for c in day_candles if ASIA_START_HOUR <= _as_utc(c.ts).hour < ASIA_END_HOUR]
    london = [c for c in day_candles if LONDON_START_HOUR <= _as_utc(c.ts).hour < LONDON_END_HOUR]
    if not asia or not london:
        return _empty_po3("missing asia or london session candles")

    asia_high = max(c.high for c in asia)
    asia_low = min(c.low for c in asia)
    if asia_high <= asia_low:
        return _empty_po3("degenerate asia range")
    asia_range_pct = (asia_high - asia_low) / asia_low * 100.0

    # London sweep + reclaim detection.
    swept_low = any(c.low < asia_low for c in london)
    swept_high = any(c.high > asia_high for c in london)
    if swept_low and swept_high:
        london_swept = "both"
    elif swept_low:
        london_swept = "low"
    elif swept_high:
        london_swept = "high"
    else:
        london_swept = "none"

    # reclaim = the London candle that wicked beyond the level CLOSES back inside.
    reclaimed_low = any(c.low < asia_low and c.close > asia_low for c in london)
    reclaimed_high = any(c.high > asia_high and c.close < asia_high for c in london)

    reclaim: Literal["long", "short"] | None = None
    po3_signal: Literal["long", "short"] | None = None
    note = "London did not sweep the Asian range."

    # Skip if the Asian range is already too wide (trend day).
    max_pct = getattr(settings, "crt_po3_max_range_pct", 1.0)
    if asia_range_pct > max_pct and timeframe.lower() in ("5min", "15min", "1h", "4h", ""):
        note = f"Asia range {asia_range_pct:.2f}% > {max_pct:.1f}% — likely trend day, PO3 skipped."
    elif reclaimed_low and not reclaimed_high:
        reclaim = "long"
        po3_signal = "long"
        note = "London swept Asian low and closed back above — bullish PO3 (Judas sweep)."
    elif reclaimed_high and not reclaimed_low:
        reclaim = "short"
        po3_signal = "short"
        note = "London swept Asian high and closed back below — bearish PO3 (Judas sweep)."
    elif reclaimed_low and reclaimed_high:
        # both sides swept and reclaimed — ambiguous, prefer the last sweep direction
        last_low_idx = max(i for i, c in enumerate(london) if c.low < asia_low and c.close > asia_low)
        last_high_idx = max(i for i, c in enumerate(london) if c.high > asia_high and c.close < asia_high)
        if last_low_idx >= last_high_idx:
            reclaim = "long"; po3_signal = "long"
            note = "Both sides swept; last reclaim was bullish (Asian low)."
        else:
            reclaim = "short"; po3_signal = "short"
            note = "Both sides swept; last reclaim was bearish (Asian high)."
    elif london_swept == "low":
        note = "London swept Asian low but did not close back above (no reclaim)."
    elif london_swept == "high":
        note = "London swept Asian high but did not close back below (no reclaim)."

    return {
        "asia_high": _round(asia_high),
        "asia_low": _round(asia_low),
        "asia_range_pct": round(asia_range_pct, 3),
        "london_swept": london_swept,
        "reclaim": reclaim,
        "po3_signal": po3_signal,
        "asia_date": last_day.isoformat(),
        "note": note,
    }


def _empty_po3(note: str) -> dict:
    return {
        "asia_high": None,
        "asia_low": None,
        "asia_range_pct": None,
        "london_swept": "none",
        "reclaim": None,
        "po3_signal": None,
        "asia_date": None,
        "note": note,
    }


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _as_utc(ts: datetime) -> datetime:
    if ts.tzinfo:
        return ts
    return ts.replace(tzinfo=timezone.utc)


def _round(v: float | None) -> float | None:
    return None if v is None else round(float(v), 3)


def _clip(x: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, x))
