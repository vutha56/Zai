"""High-level scan pipeline: candles -> CRT detection -> persist new signals.

This is the single entrypoint the scheduler and /api/scan use. It:
  1. Ensures candles are synced.
  2. Runs CRT detection on the most recent lookback window.
  3. Persists signals that are new (not already stored for that candle_ts+direction).
  4. Returns the freshly created Signal rows (so callers can analyze + notify).
"""
from __future__ import annotations

import logging

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import settings
from ..data.sync import load_candles, sync_candles
from ..data.twelvedata import CandleDTO, TwelveDataProvider
from ..models import Signal
from .crt import bar_seconds, detect_setups, latest_unique_setups

log = logging.getLogger(__name__)


def candles_to_dto(rows) -> list[CandleDTO]:
    return [
        CandleDTO(ts=r.ts, open=r.open, high=r.high, low=r.low, close=r.close, volume=r.volume)
        for r in rows
    ]


def run_scan(
    db: Session,
    provider: TwelveDataProvider | None = None,
    fetch: bool = True,
    timeframe: str | None = None,
    symbol: str | None = None,
) -> list[Signal]:
    """Run one scan cycle across one or all configured (symbol, timeframe) pairs.

    Returns newly-created Signal rows (newest-first).
    - If `symbol`/`timeframe` given, only that pair is scanned.
    - Otherwise all `settings.symbols_list` × `settings.timeframes` are scanned,
      each with its own provider + candle fetch.
    - If a `provider` is passed, its symbol/interval are honored and the loop
      is skipped (single-pair manual scan).
    """
    overrides = settings.tf_overrides
    all_new: list[Signal] = []

    if provider is not None:
        # explicit provider -> single pair, no loop
        try:
            all_new = _scan_one_timeframe(
                db, provider, provider.interval, overrides, fetch=fetch
            )
        except Exception as exc:
            log.error("Scan failed for %s %s: %s", provider.symbol, provider.interval, exc)
        all_new.sort(key=lambda s: s.created_at, reverse=True)
        return all_new

    symbols = [symbol] if symbol else settings.symbols_list
    timeframes = [timeframe] if timeframe else settings.timeframes

    for sym in symbols:
        for tf in timeframes:
            pair_provider = TwelveDataProvider(symbol=sym, interval=tf)
            try:
                new_signals = _scan_one_timeframe(
                    db, pair_provider, tf, overrides, fetch=fetch, symbol=sym
                )
            except Exception as exc:
                log.error("Scan failed for %s %s: %s", sym, tf, exc)
                continue
            all_new.extend(new_signals)

    all_new.sort(key=lambda s: s.created_at, reverse=True)
    return all_new


def _scan_one_timeframe(
    db: Session,
    provider: TwelveDataProvider,
    timeframe: str,
    overrides: dict,
    fetch: bool,
    symbol: str | None = None,
) -> list[Signal]:
    """Scan a single symbol/timeframe: sync candles, detect, persist new signals."""
    sym = symbol or provider.symbol
    if fetch:
        try:
            sync_candles(db, provider=provider)
        except Exception as exc:
            log.error("Candle sync failed for %s %s: %s", sym, timeframe, exc)
            return []

    candles = load_candles(db, limit=settings.crt_scan_lookback + 12, symbol=sym, timeframe=timeframe)
    if len(candles) < 8:
        log.info("Scan %s %s: not enough candles (%d).", sym, timeframe, len(candles))
        return []

    dtos = candles_to_dto(candles)
    setups = detect_setups(dtos, timeframe=timeframe, tf_overrides=overrides)
    if not setups:
        log.info("Scan %s %s: no CRT setups detected.", sym, timeframe)
        return []

    # Only act on setups anchored near the most recent candle (last few bars).
    last_ts = dtos[-1].ts
    bar_sec = bar_seconds(timeframe)
    fresh = [s for s in setups if _is_fresh(s, last_ts, bar_sec)]
    fresh = latest_unique_setups(fresh)
    if not fresh:
        log.info("Scan %s %s: setups exist but none recent.", sym, timeframe)
        return []

    new_signals: list[Signal] = []
    for s in fresh:
        # dedup key now includes timeframe + symbol (also enforced by the DB unique index)
        exists = db.scalar(
            select(Signal).where(
                Signal.symbol == sym,
                Signal.timeframe == timeframe,
                Signal.candle_ts == s.candle_ts,
                Signal.direction == s.direction,
            )
        )
        if exists:
            continue
        sig = Signal(
            symbol=sym,
            timeframe=timeframe,
            candle_ts=s.candle_ts,
            direction=s.direction,
            range_high=s.range_high,
            range_low=s.range_low,
            sweep_level=s.sweep_level,
            fvg_top=s.fvg_top,
            fvg_bottom=s.fvg_bottom,
            entry=s.entry,
            sl=s.sl,
            tp=s.tp,
            atr=s.atr,
            session=s.session,
            dow=s.dow,
            confidence=s.confidence,
            premium_discount=s.premium_discount,
            in_killzone=s.in_killzone,
            killzone=s.killzone,
            entry_model=s.entry_model,
            status="open",
        )
        db.add(sig)
        new_signals.append(sig)

    if new_signals:
        db.commit()
        for sig in new_signals:
            db.refresh(sig)
        log.info(
            "Scan %s %s: created %d new signal(s): %s",
            sym, timeframe, len(new_signals), [s.id for s in new_signals],
        )
    else:
        log.info("Scan %s %s: no new signals (already stored).", sym, timeframe)
    return new_signals


def _is_fresh(s, last_ts, bar_sec: int) -> bool:
    """A setup is 'fresh' if its displacement candle is within the last 3 bars."""
    # displacement candle must be no older than 3 bars of this timeframe.
    return (last_ts - s.candle_ts).total_seconds() <= 3 * bar_sec + 1
