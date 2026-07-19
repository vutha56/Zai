"""Outcome resolution + performance summaries (the daily-improvement data).

For each matured signal we walk the candles that came AFTER it and decide:
  - WIN  : TP was touched before SL.
  - LOSS : SL was touched before TP.
  - EXPIRED : neither was touched within the look-forward window.

Performance summaries are rebuilt from resolved outcomes and feed back into the
LLM prompt — this is the "improve every day" loop.
"""
from __future__ import annotations

import json
import logging
from collections import defaultdict
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import settings
from ..data.sync import load_candles
from ..models import Candle, Outcome, PerfSummary, Signal
from ..strategy.crt import bar_seconds


def _as_utc(ts: datetime) -> datetime:
    """SQLite returns naive datetimes (strips tzinfo); force UTC for safe math."""
    if ts is None:
        return None  # type: ignore[return-value]
    return ts if ts.tzinfo else ts.replace(tzinfo=timezone.utc)

log = logging.getLogger(__name__)

HOURS_PER_CANDLE = 4


def resolve_outcomes(db: Session) -> int:
    """Resolve all open signals past their per-timeframe look-forward window.

    The look-forward window is derived from EACH signal's own timeframe (via
    bar_seconds), not a global 4h assumption. Candles are loaded per
    (symbol, timeframe) so BTC/15min signals resolve against BTC/15min candles.
    """
    # buffer multiplier so we don't prematurely expire signals whose data is stale
    lookforward_bars = settings.crt_lookforward_candles

    open_signals = list(
        db.execute(select(Signal).where(Signal.status == "open")).scalars()
    )
    if not open_signals:
        return 0

    now = datetime.now(timezone.utc)
    resolved = 0
    # group signals by (symbol, timeframe) to batch-load candles once per group
    groups: dict[tuple[str, str], list] = {}
    for sig in open_signals:
        groups.setdefault((sig.symbol, sig.timeframe), []).append(sig)

    for (sym, tf), sigs in groups.items():
        bar_sec = bar_seconds(tf)
        lookforward_secs = lookforward_bars * bar_sec
        candle_list = load_candles(db, limit=400, symbol=sym, timeframe=tf)
        if not candle_list:
            continue
        for sig in sigs:
            age = (now - _as_utc(sig.candle_ts)).total_seconds()
            if age < lookforward_secs:
                continue  # not enough time elapsed to resolve yet
            if _already_resolved(db, sig.id):
                sig.status = _status_from_existing(db, sig.id)
                continue
            future = [c for c in candle_list if c.ts > sig.candle_ts][: lookforward_bars + 1]
            outcome = _evaluate(sig, future)
            if outcome is None:
                continue  # not enough candle data yet
            db.add(outcome)
            sig.status = outcome.result
            resolved += 1

    db.commit()
    if resolved:
        log.info("Resolved %d signal outcome(s).", resolved)
    return resolved


def _already_resolved(db: Session, signal_id: int) -> bool:
    return db.scalar(select(Outcome.signal_id).where(Outcome.signal_id == signal_id)) is not None


def _status_from_existing(db: Session, signal_id: int) -> str:
    o = db.scalar(select(Outcome).where(Outcome.signal_id == signal_id))
    return o.result if o else "open"


def _evaluate(sig: Signal, future: list[Candle]) -> Outcome | None:
    if not future:
        return None
    is_long = sig.direction == "LONG"
    tp, sl = sig.tp, sig.sl
    for c in future:
        # wick checks first
        hit_tp = c.high >= tp if is_long else c.low <= tp
        hit_sl = c.low <= sl if is_long else c.high >= sl
        if hit_tp and hit_sl:
            # ambiguous same-candle hit -> conservatively call it a loss
            result, hit_price = "loss", sl
        elif hit_tp:
            result, hit_price = "win", tp
        elif hit_sl:
            result, hit_price = "loss", sl
        else:
            continue
        r = _r_multiple(sig, result, hit_price)
        return Outcome(
            signal_id=sig.id, result=result, r_multiple=round(r, 3),
            hit_price=hit_price, hit_ts=c.ts,
        )
    # neither hit -> expired
    return Outcome(
        signal_id=sig.id, result="expired", r_multiple=0.0,
        hit_price=0.0, hit_ts=None,
    )


def _r_multiple(sig: Signal, result: str, hit_price: float) -> float:
    risk = abs(sig.entry - sig.sl) or 1e-9
    if result == "win":
        return abs(sig.tp - sig.entry) / risk
    if result == "loss":
        return -1.0
    return 0.0


# ---------------------------------------------------------------------------
# Performance summary (feeds back into the LLM)
# ---------------------------------------------------------------------------

def rebuild_perf_summary(db: Session) -> PerfSummary | None:
    """Aggregate resolved outcomes into a PerfSummary row + return it."""
    rows = list(
        db.execute(
            select(Signal, Outcome)
            .join(Outcome, Outcome.signal_id == Signal.id)
            .order_by(Signal.created_at.desc())
        ).all()
    )
    if not rows:
        return None

    signals = [r[0] for r in rows]
    outcomes = [r[1] for r in rows]

    def _win_rate(slice_signals, slice_outcomes) -> float:
        decided = [o for o in slice_outcomes if o.result in ("win", "loss")]
        if not decided:
            return 0.0
        wins = sum(1 for o in decided if o.result == "win")
        return round(100.0 * wins / len(decided), 1)

    def _avg_r(slice_outcomes) -> float:
        decided = [o for o in slice_outcomes if o.result in ("win", "loss")]
        if not decided:
            return 0.0
        return round(sum(o.r_multiple for o in decided) / len(decided), 3)

    win20 = _win_rate(signals[:20], outcomes[:20])
    win50 = _win_rate(signals[:50], outcomes[:50])
    avg_r = _avg_r(outcomes)

    by_session = _breakdown(signals, outcomes, key=lambda s: s.session or "unknown")
    by_dir = _breakdown(signals, outcomes, key=lambda s: s.direction)

    narrative = build_narrative(
        win20=win20, win50=win50, avg_r=avg_r,
        by_session=by_session, by_dir=by_dir, n=len(signals),
    )

    summary = PerfSummary(
        win_rate_20=win20,
        win_rate_50=win50,
        avg_r=avg_r,
        sample_size=len(signals),
        by_session=json.dumps(by_session),
        by_direction=json.dumps(by_dir),
        narrative=narrative,
    )
    db.add(summary)
    db.commit()
    db.refresh(summary)
    log.info("Perf summary rebuilt: win20=%.1f%% win50=%.1f%% avgR=%.2f (n=%d)",
             win20, win50, avg_r, len(signals))
    return summary


def _breakdown(signals: list[Signal], outcomes: list[Outcome], key) -> dict:
    buckets: dict[str, dict] = defaultdict(lambda: {"n": 0, "wins": 0, "r": 0.0, "decided": 0})
    for s, o in zip(signals, outcomes):
        k = key(s)
        b = buckets[k]
        b["n"] += 1
        if o.result in ("win", "loss"):
            b["decided"] += 1
            if o.result == "win":
                b["wins"] += 1
            b["r"] += o.r_multiple
    out = {}
    for k, b in buckets.items():
        out[k] = {
            "n": b["n"],
            "win_rate": round(100.0 * b["wins"] / b["decided"], 1) if b["decided"] else 0.0,
            "avg_r": round(b["r"] / b["decided"], 3) if b["decided"] else 0.0,
        }
    return out


def build_narrative(win20: float, win50: float, avg_r: float,
                    by_session: dict, by_dir: dict, n: int) -> str:
    """Human-readable summary injected into the LLM prompt as feedback context."""
    parts = [
        f"Tracked {n} resolved CRT setups. "
        f"Win rate (last 20): {win20}%. Win rate (last 50): {win50}%. "
        f"Average R-multiple: {avg_r:+.2f}R."
    ]
    # best/worst session
    sess = [(k, v["win_rate"], v["n"]) for k, v in by_session.items() if v["n"] >= 2]
    if sess:
        sess.sort(key=lambda x: x[1], reverse=True)
        best = sess[0]
        worst = sess[-1]
        if best[0] != worst[0]:
            parts.append(
                f"Best session: {best[0]} ({best[1]}% over {best[2]}). "
                f"Weakest session: {worst[0]} ({worst[1]}% over {worst[2]})."
            )
    dirs = [(k, v["win_rate"], v["n"]) for k, v in by_dir.items() if v["n"] >= 2]
    if len(dirs) == 2:
        dirs.sort(key=lambda x: x[1], reverse=True)
        parts.append(
            f"{dirs[0][0]} setups are outperforming ({dirs[0][1]}%) vs {dirs[1][0]} ({dirs[1][1]}%)."
        )
    return " ".join(parts)


def get_latest_perf_text(db: Session) -> str:
    """Return the most recent perf narrative (or a sensible default)."""
    row = db.scalar(select(PerfSummary).order_by(PerfSummary.generated_at.desc()))
    if row and row.narrative:
        return row.narrative
    return ("No tracked history yet. This is an early-stage CRT deployment; treat "
            "confidence with caution until at least 20 setups are resolved.")
