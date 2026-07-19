"""Market Structure (BOS / CHoCH / MSS / MSNR) — pure functions.

Detects the classic ICT / SMC market-structure events on a candle list:

  - Swing high/low = fractal pivot (a candle whose high/low is the extreme of
    the `swing_length` candles on each side).
  - BOS  (Break of Structure)     = close beyond the last same-direction swing
                                    (continuation of the prevailing trend).
  - CHoCH (Change of Character)   = first close beyond a counter-trend internal
                                    swing (the first hint of a reversal).
  - MSS  (Market Structure Shift) = CHoCH with displacement: body >= 1.5*ATR AND
                                    body_ratio >= 0.6, OR leaves an FVG.
  - MSNR (Market Structure No Run)= a structure break that should be rejected if:
                                    (a) no prior liquidity sweep within 3 bars,
                                    (b) weak close (<0.2*ATR beyond the swing),
                                    (c) immediate failure (closes back within 2
                                        bars of the break).

Pure: no DB / no IO. Takes CandleDTO lists, returns plain dicts suitable for JSON.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Literal

from ..data.twelvedata import CandleDTO
from .crt import atr


# ---------------------------------------------------------------------------
# Swings (fractal pivots)
# ---------------------------------------------------------------------------

@dataclass
class Swing:
    idx: int                 # index into the candle list
    ts: datetime
    price: float
    type: Literal["high", "low"]
    confirmed: bool = True   # always True here — fractal pivots are confirmed by definition


def detect_swings(
    candles: list[CandleDTO], swing_length: int = 2
) -> list[dict]:
    """Fractal pivot detection.

    A swing high at index i requires candles[i].high to be strictly the highest
    of [i-L .. i+L]; a swing low requires strictly the lowest. `swing_length`
    is L on each side (so the window is 2L+1 candles).

    Returns a list of {ts, price, type, confirmed, idx} dicts (oldest-first).
    """
    L = max(1, int(swing_length))
    out: list[dict] = []
    n = len(candles)
    for i in range(L, n - L):
        window = candles[i - L: i + L + 1]
        hi = max(c.high for c in window)
        lo = min(c.low for c in window)
        c = candles[i]
        if c.high == hi and sum(1 for w in window if w.high == hi) == 1:
            out.append({
                "ts": c.ts.isoformat(), "price": round(c.high, 3),
                "type": "high", "confirmed": True, "idx": i,
            })
        if c.low == lo and sum(1 for w in window if w.low == lo) == 1:
            out.append({
                "ts": c.ts.isoformat(), "price": round(c.low, 3),
                "type": "low", "confirmed": True, "idx": i,
            })
    out.sort(key=lambda s: s["idx"])
    return out


# ---------------------------------------------------------------------------
# BOS / CHoCH / MSS / MSNR
# ---------------------------------------------------------------------------

@dataclass
class _StructureEvent:
    kind: str                 # bos | choch | mss
    direction: Literal["bullish", "bearish"]
    ts: datetime              # break candle ts
    break_idx: int
    swing_ts: datetime        # the swing that was broken
    swing_price: float
    close: float
    displaced: bool = False   # body >= 1.5*ATR + body_ratio >= 0.6 (or FVG)
    leaves_fvg: bool = False
    msnr_rejected: bool = False
    reject_reason: str = ""


def market_structure(
    candles: list[CandleDTO], swing_length: int = 2
) -> dict:
    """Detect market structure events and the prevailing trend.

    Returns:
        {
          trend:        "bullish" | "bearish" | "range",
          swings:       [...],          # from detect_swings
          last_bos:     {...} | None,
          last_choch:   {...} | None,
          last_mss:     {...} | None,
          events:       [...],          # chronological list of all events
        }
    """
    swings_raw = detect_swings(candles, swing_length=swing_length)
    if len(candles) < 5 or not swings_raw:
        return {
            "trend": "range",
            "swings": swings_raw,
            "last_bos": None,
            "last_choch": None,
            "last_mss": None,
            "events": [],
        }

    atrs = atr(candles, period=14)
    # Map idx -> swing for quick lookup of the most-recent same/counter swing.
    events: list[_StructureEvent] = []
    trend: Literal["bullish", "bearish", "range"] = "range"
    last_high_swing: dict | None = None   # last swing high (resistance)
    last_low_swing: dict | None = None    # last swing low (support)
    swing_idx_consumed: set[int] = set()  # swings already "broken" so we don't refire

    # Walk candles in order; when a candle closes beyond the most-recent
    # relevant swing, classify the event.
    for i in range(len(candles)):
        c = candles[i]
        a = atrs[i] or 1e-9
        body = abs(c.close - c.open)
        body_ratio = body / max(abs(c.high - c.low), 1e-9)

        # update the rolling last-swing pointers using swings that have just
        # become "confirmed" (i.e. their pivot index + swing_length <= i)
        for s in swings_raw:
            s_idx = s["idx"]
            if s_idx + swing_length == i:  # the candle that completes this swing
                if s["type"] == "high":
                    last_high_swing = s
                else:
                    last_low_swing = s

        # --- bullish structure break: close above the last swing high ---
        if last_high_swing and c.close > last_high_swing["price"] \
                and last_high_swing["idx"] not in swing_idx_consumed:
            swing_idx_consumed.add(last_high_swing["idx"])
            displaced = body >= 1.5 * a and body_ratio >= 0.6
            leaves_fvg = _leaves_fvg(candles, i, "bullish")
            is_choch = (trend == "bearish")
            kind = "choch" if is_choch else "bos"
            ev = _StructureEvent(
                kind=kind, direction="bullish",
                ts=c.ts, break_idx=i,
                swing_ts=_parse_iso(last_high_swing["ts"]),
                swing_price=last_high_swing["price"],
                close=c.close,
                displaced=displaced, leaves_fvg=leaves_fvg,
            )
            # MSNR: only flag for CHoCH-type reversal attempts (the "fake" breaks)
            if is_choch:
                ev.msnr_rejected, ev.reject_reason = _msnr_check(
                    candles, i, last_high_swing["price"], a, direction="bullish"
                )
                # promote CHoCH to MSS if displaced and not MSNR-rejected
                if (displaced or leaves_fvg) and not ev.msnr_rejected:
                    ev.kind = "mss"
            events.append(ev)
            if ev.kind == "mss":
                trend = "bullish"
            elif kind == "bos":
                trend = "bullish"
            # plain choch (no displacement / msnr-rejected) leaves trend unchanged

        # --- bearish structure break: close below the last swing low ---
        elif last_low_swing and c.close < last_low_swing["price"] \
                and last_low_swing["idx"] not in swing_idx_consumed:
            swing_idx_consumed.add(last_low_swing["idx"])
            displaced = body >= 1.5 * a and body_ratio >= 0.6
            leaves_fvg = _leaves_fvg(candles, i, "bearish")
            is_choch = (trend == "bullish")
            kind = "choch" if is_choch else "bos"
            ev = _StructureEvent(
                kind=kind, direction="bearish",
                ts=c.ts, break_idx=i,
                swing_ts=_parse_iso(last_low_swing["ts"]),
                swing_price=last_low_swing["price"],
                close=c.close,
                displaced=displaced, leaves_fvg=leaves_fvg,
            )
            if is_choch:
                ev.msnr_rejected, ev.reject_reason = _msnr_check(
                    candles, i, last_low_swing["price"], a, direction="bearish"
                )
                if (displaced or leaves_fvg) and not ev.msnr_rejected:
                    ev.kind = "mss"
            events.append(ev)
            if ev.kind == "mss":
                trend = "bearish"
            elif kind == "bos":
                trend = "bearish"

    # last of each kind
    last_bos = _last_of_kind(events, "bos")
    last_choch = _last_of_kind(events, "choch")
    last_mss = _last_of_kind(events, "mss")

    return {
        "trend": trend,
        "swings": swings_raw,
        "last_bos": _ev_to_dict(last_bos),
        "last_choch": _ev_to_dict(last_choch),
        "last_mss": _ev_to_dict(last_mss),
        "events": [_ev_to_dict(e) for e in events],
    }


# ---------------------------------------------------------------------------
# MSS / MSNR helpers
# ---------------------------------------------------------------------------

def _leaves_fvg(candles: list[CandleDTO], i: int, direction: str) -> bool:
    """True if the 3-candle window [i-1, i, i+1] forms an FVG in `direction`."""
    if i < 1 or i >= len(candles) - 1:
        return False
    a, b = candles[i - 1], candles[i + 1]
    if direction == "bullish":
        return a.high < b.low
    return a.low > b.high


def _msnr_check(
    candles: list[CandleDTO],
    i: int,
    swing_price: float,
    atr_val: float,
    direction: str,
) -> tuple[bool, str]:
    """MSNR rejection filter. Returns (rejected, reason).

    Reject if any of:
      (a) no prior liquidity sweep within 3 bars (a wick beyond the swing
          before the close-break);
      (b) weak close: less than 0.2*ATR beyond the swing;
      (c) immediate failure: a later candle within 2 bars closes back inside.
    """
    # (b) weak close
    if direction == "bullish":
        weak = (candles[i].close - swing_price) < 0.2 * atr_val
    else:
        weak = (swing_price - candles[i].close) < 0.2 * atr_val
    if weak:
        return True, "weak_close_<0.2ATR"

    # (a) prior liquidity sweep within 3 bars before i
    swept = False
    for k in range(max(0, i - 3), i):
        if direction == "bullish" and candles[k].high > swing_price:
            swept = True
            break
        if direction == "bearish" and candles[k].low < swing_price:
            swept = True
            break
    if not swept:
        return True, "no_prior_sweep_within_3_bars"

    # (c) immediate failure: closes back inside within 2 bars
    for k in range(i + 1, min(len(candles), i + 3)):
        if direction == "bullish" and candles[k].close < swing_price:
            return True, "immediate_failure_within_2_bars"
        if direction == "bearish" and candles[k].close > swing_price:
            return True, "immediate_failure_within_2_bars"

    return False, ""


def _last_of_kind(events: list[_StructureEvent], kind: str) -> _StructureEvent | None:
    for ev in reversed(events):
        if ev.kind == kind:
            return ev
    return None


def _ev_to_dict(ev: _StructureEvent | None) -> dict | None:
    if ev is None:
        return None
    return {
        "kind": ev.kind,
        "direction": ev.direction,
        "ts": ev.ts.isoformat(),
        "break_idx": ev.break_idx,
        "swing_ts": ev.swing_ts.isoformat() if ev.swing_ts else None,
        "swing_price": round(ev.swing_price, 3),
        "close": round(ev.close, 3),
        "displaced": ev.displaced,
        "leaves_fvg": ev.leaves_fvg,
        "msnr_rejected": ev.msnr_rejected,
        "reject_reason": ev.reject_reason,
    }


def _parse_iso(s: str) -> datetime:
    """Parse an ISO timestamp back to a tz-aware datetime (best-effort)."""
    try:
        return datetime.fromisoformat(s)
    except (ValueError, TypeError):
        from datetime import timezone
        return datetime.now(timezone.utc)
