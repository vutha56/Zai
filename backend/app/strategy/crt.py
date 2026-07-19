"""CRT (Candle Range Theory) 4h detection engine.

A CRT setup = Range -> Manipulation (sweep) -> Distribution (displacement + FVG).

This module is pure: given a list of candles it returns detected setups without any
DB or I/O dependency, so it can be unit-tested in isolation.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Literal

from ..config import settings
from ..data.twelvedata import CandleDTO


Direction = Literal["LONG", "SHORT"]


@dataclass
class CRTSetup:
    """A fully-formed CRT setup with a trade plan and feature vector."""

    # Structural indices into the source candle list
    range_start_idx: int
    range_end_idx: int      # last candle of the consolidation range (exclusive end)
    sweep_idx: int          # the manipulation candle
    displacement_idx: int   # the impulsive reversal candle

    # Structural levels
    direction: Direction
    range_high: float
    range_low: float
    sweep_high: float
    sweep_low: float
    sweep_close: float
    sweep_level: float      # the extreme that was swept (low for LONG, high for SHORT)

    # Displacement + FVG
    displacement_body: float
    fvg_top: float
    fvg_bottom: float

    # Trade plan
    entry: float
    sl: float
    tp: float
    atr: float

    # Context
    candle_ts: datetime     # timestamp of the displacement candle (signal trigger)
    session: str
    dow: int
    confidence: float = 0.0
    timeframe: str = ""     # interval this setup was detected on (e.g. "15min")

    # Strategy enhancement (ICT premium/discount + killzones)
    premium_discount: str = "equilibrium"   # premium | discount | equilibrium
    in_killzone: bool = False
    killzone: str = ""                       # London | NY_AM | NY_PM | ""
    entry_model: str = "FVG_midpoint"

    features: dict = field(default_factory=dict)

    @property
    def fvg_size(self) -> float:
        return abs(self.fvg_top - self.fvg_bottom)

    @property
    def risk(self) -> float:
        return abs(self.entry - self.sl)

    @property
    def reward(self) -> float:
        return abs(self.tp - self.entry)

    @property
    def rr(self) -> float:
        return self.reward / self.risk if self.risk else 0.0


# ---------------------------------------------------------------------------
# Indicators
# ---------------------------------------------------------------------------

def atr(candles: list[CandleDTO], period: int = 14) -> list[float]:
    """Simple ATR (Wilder not required for ranking; SMA of TR is fine)."""
    if len(candles) < 2:
        return [0.0] * len(candles)
    trs = [0.0]
    for i in range(1, len(candles)):
        c, p = candles[i], candles[i - 1]
        tr = max(c.high - c.low, abs(c.high - p.close), abs(c.low - p.close))
        trs.append(tr)
    out: list[float] = []
    for i in range(len(candles)):
        window = trs[max(1, i - period + 1): i + 1]
        out.append(sum(window) / len(window) if window else 0.0)
    return out


def trading_session(ts: datetime) -> str:
    """Coarse FX session label from a UTC timestamp."""
    h = ts.hour
    if 0 <= h < 7:
        return "Asia"
    if 7 <= h < 12:
        return "London"
    if 12 <= h < 17:
        return "NY"
    return "LateNY"


# ICT Silver Bullet killzone windows (UTC). Derived from the EST times:
#   London 03-04 EST -> 07-10 UTC (widened to the London sweep window)
#   NY AM  10-11 EST -> 14-17 UTC
#   NY PM  02-03 EST -> 18-21 UTC (London close)
# Asia is deliberately excluded — research consensus: avoid gold Asian session.
KILLZONES: list[tuple[str, int, int]] = [
    ("London", 7, 10),
    ("NY_AM", 14, 17),
    ("NY_PM", 18, 21),
]


def killzone_of(ts: datetime) -> str:
    """Return the killzone name for a UTC timestamp, or '' if outside all windows."""
    h = ts.hour
    for name, start, end in KILLZONES:
        if start <= h < end:
            return name
    return ""


def bar_seconds(timeframe: str) -> int:
    """Seconds per candle for a Twelve Data interval string (5min/15min/1h/4h/1day...)."""
    tf = (timeframe or "").strip().lower()
    try:
        if tf.endswith("min"):
            return int(tf[:-3]) * 60
        if tf.endswith("h"):
            return int(tf[:-1]) * 3600
        if tf.endswith("day") or tf == "1d":
            return 86400
        if tf.endswith("week") or tf == "1w":
            return 604800
    except ValueError:
        pass
    return 4 * 3600  # safe fallback (4h)


# ---------------------------------------------------------------------------
# Detection
# ---------------------------------------------------------------------------

def detect_setups(
    candles: list[CandleDTO],
    timeframe: str | None = None,
    range_window: int | None = None,
    displacement_k: float | None = None,
    atr_period: int | None = None,
    sl_buffer_atr: float | None = None,
    min_rr: float | None = None,
    tf_overrides: dict | None = None,
) -> list[CRTSetup]:
    """Scan the candle list for CRT setups.

    We slide a window and look for the pattern
    [range: N candles] [sweep: 1 candle] [displacement: 1 candle] [confirm: 1 candle]
    anchored at the most recent confirm candle. One setup per anchor index.
    """
    n = len(candles)
    if n < 6:
        return []

    range_window = range_window or settings.crt_range_window
    displacement_k = displacement_k or settings.crt_displacement_k
    atr_period = atr_period or settings.crt_atr_period
    sl_buffer_atr = sl_buffer_atr if sl_buffer_atr is not None else settings.crt_sl_buffer_atr
    min_rr = min_rr if min_rr is not None else settings.crt_min_rr

    # Apply per-timeframe overrides (e.g. tighter range / stricter displacement on 5m).
    tf = timeframe or ""
    if tf and tf_overrides:
        ov = tf_overrides.get(tf) or {}
        range_window = ov.get("range_window", range_window)
        displacement_k = ov.get("displacement_k", displacement_k)

    atrs = atr(candles, period=atr_period)
    setups: list[CRTSetup] = []

    # We need: range [i..i+W-1], sweep at i+W, displacement at i+W+1, confirm at i+W+2.
    # The confirm candle is what leaves the FVG with the displacement.
    W = range_window
    for i in range(0, n - (W + 3) + 1):
        rng = candles[i:i + W]
        sweep = candles[i + W]
        disp = candles[i + W + 1]
        confirm = candles[i + W + 2]

        r_high = max(c.high for c in rng)
        r_low = min(c.low for c in rng)

        # --- Manipulation: poke an extreme then close back inside ---
        bullish_sweep = sweep.low < r_low and sweep.close >= r_low
        bearish_sweep = sweep.high > r_high and sweep.close <= r_high
        if not (bullish_sweep or bearish_sweep):
            continue

        direction: Direction = "LONG" if bullish_sweep else "SHORT"
        sweep_level = r_low if bullish_sweep else r_high

        # --- Displacement: strong impulse in reversal direction ---
        disp_body = abs(disp.close - disp.open)
        disp_atr = atrs[i + W + 1] or 1e-9
        if disp_body < displacement_k * disp_atr:
            continue
        if direction == "LONG" and not (disp.close > disp.open):
            continue
        if direction == "SHORT" and not (disp.close < disp.open):
            continue

        # --- FVG: standard 3-candle imbalance straddling the displacement ---
        # The displacement is so strong that the wicks of the sweep candle
        # (before) and the confirm candle (after) don't overlap.
        #   Bullish FVG: sweep.high < confirm.low  -> gap [sweep.high, confirm.low]
        #   Bearish FVG: sweep.low  > confirm.high -> gap [confirm.high, sweep.low]
        if direction == "LONG":
            fvg_bottom = sweep.high
            fvg_top = confirm.low
            if fvg_top <= fvg_bottom:
                continue
        else:
            fvg_top = sweep.low
            fvg_bottom = confirm.high
            if fvg_top <= fvg_bottom:
                continue

        a = atrs[i + W + 1] or max(fvg_top - fvg_bottom, 1e-9)

        # --- Trade plan ---
        entry = round((fvg_top + fvg_bottom) / 2.0, 3)
        if direction == "LONG":
            sl = round(sweep.low - sl_buffer_atr * a, 3)
            # default TP at the opposite range liquidity, then enforce min RR
            tp = round(r_high, 3)
            risk = entry - sl
            if risk <= 0:
                continue
            reward = max(r_high - entry, min_rr * risk)
            tp = round(entry + reward, 3)
        else:
            sl = round(sweep.high + sl_buffer_atr * a, 3)
            tp = round(r_low, 3)
            risk = sl - entry
            if risk <= 0:
                continue
            reward = max(entry - r_low, min_rr * risk)
            tp = round(entry - reward, 3)

        confidence = _confidence(
            direction=direction,
            disp_body=disp_body,
            disp_atr=disp_atr,
            fvg_size=fvg_top - fvg_bottom,
            sweep_wick=(
                (sweep.low - r_low) if direction == "LONG" else (r_high - sweep.high)
            ),
            atr_val=a,
            rr=abs(tp - entry) / abs(entry - sl) if (entry - sl) else 0.0,
        )

        # --- ICT enhancement: premium/discount + killzone ---
        equilibrium = (r_high + r_low) / 2.0
        # classify entry relative to the range equilibrium
        if direction == "LONG":
            # longs want to buy in the discount half
            premium_discount = "discount" if entry < equilibrium else "premium"
            pd_aligned = entry < equilibrium
        else:
            # shorts want to sell in the premium half
            premium_discount = "premium" if entry > equilibrium else "discount"
            pd_aligned = entry > equilibrium
        if not pd_aligned:
            if settings.crt_pd_strict:
                continue  # drop low-quality setups entirely in strict mode
            confidence -= settings.crt_pd_penalty

        # killzone membership from the displacement candle's UTC hour
        kz = killzone_of(disp.ts)
        in_kz = bool(kz)
        if in_kz:
            confidence += settings.crt_killzone_bonus
        else:
            confidence -= settings.crt_killzone_off_penalty

        confidence = round(max(0.0, min(100.0, confidence)), 1)

        setup = CRTSetup(
            range_start_idx=i,
            range_end_idx=i + W,
            sweep_idx=i + W,
            displacement_idx=i + W + 1,
            direction=direction,
            range_high=round(r_high, 3),
            range_low=round(r_low, 3),
            sweep_high=round(sweep.high, 3),
            sweep_low=round(sweep.low, 3),
            sweep_close=round(sweep.close, 3),
            sweep_level=round(sweep_level, 3),
            displacement_body=round(disp_body, 3),
            fvg_top=round(fvg_top, 3),
            fvg_bottom=round(fvg_bottom, 3),
            entry=entry,
            sl=sl,
            tp=tp,
            atr=round(a, 3),
            candle_ts=disp.ts,
            session=trading_session(disp.ts),
            dow=disp.ts.weekday(),
            confidence=confidence,
            timeframe=tf,
            premium_discount=premium_discount,
            in_killzone=in_kz,
            killzone=kz,
            entry_model="FVG_midpoint",
            features={
                "range_width_atr": round((r_high - r_low) / a, 3),
                "equilibrium": round(equilibrium, 3),
                "sweep_depth_atr": round(
                    ((sweep.low - r_low) if direction == "LONG" else (r_high - sweep.high)) / a, 3
                ),
                "displacement_body_atr": round(disp_body / disp_atr, 3),
                "fvg_size_atr": round((fvg_top - fvg_bottom) / a, 3),
                "rr": round(abs(tp - entry) / abs(entry - sl), 3) if (entry - sl) else 0.0,
            },
        )
        setups.append(setup)

    return setups


def latest_unique_setups(setups: list[CRTSetup]) -> list[CRTSetup]:
    """Collapse to the single most-recent setup per direction in the last cycle.

    Scans typically return multiple overlapping windows; we keep only setups whose
    displacement candle is within the last few candles, deduped by displacement_ts.
    """
    seen: dict[datetime, CRTSetup] = {}
    for s in setups:
        # keep the highest-confidence setup for each displacement timestamp
        cur = seen.get(s.candle_ts)
        if cur is None or s.confidence > cur.confidence:
            seen[s.candle_ts] = s
    # return newest-first
    return sorted(seen.values(), key=lambda s: s.candle_ts, reverse=True)


def _confidence(
    direction: Direction,
    disp_body: float,
    disp_atr: float,
    fvg_size: float,
    sweep_wick: float,
    atr_val: float,
    rr: float,
) -> float:
    """Heuristic 0-100 score. Recent win rate is blended in by the caller."""
    # displacement strength: 1*ATR = 50, 2*ATR = 100
    disp_score = _clip((disp_body / max(disp_atr, 1e-9)) * 50.0, 0, 45)
    # FVG size: bigger imbalance = more institutional footprint
    fvg_score = _clip((fvg_size / max(atr_val, 1e-9)) * 60.0, 0, 30)
    # sweep wick: a deeper sweep = more liquidity grabbed
    sweep_score = _clip((sweep_wick / max(atr_val, 1e-9)) * 50.0, 0, 15)
    # R:R quality: reward up to 10 points at rr>=2
    rr_score = _clip((rr / 2.0) * 10.0, 0, 10)
    return disp_score + fvg_score + sweep_score + rr_score


def _clip(x: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, x))
