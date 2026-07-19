"""Control endpoints: health check, manual scan, manual analysis."""
from __future__ import annotations

import logging

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..ai.analyzer import analyze_signal
from ..config import settings
from ..db import get_db
from ..models import Candle, Signal
from ..schemas import HealthOut
from ..strategy.scanner import run_scan

router = APIRouter()
log = logging.getLogger(__name__)


@router.get("/health", response_model=HealthOut, tags=["control"])
def health(db: Session = Depends(get_db)):
    candles = db.scalar(select(func.count()).select_from(Candle)) or 0
    signals = db.scalar(select(func.count()).select_from(Signal)) or 0
    open_signals = db.scalar(
        select(func.count()).select_from(Signal).where(Signal.status == "open")
    ) or 0
    return HealthOut(
        status="ok",
        symbol=settings.symbol,
        timeframe=settings.timeframe,
        timeframes=settings.timeframes,
        symbols=settings.symbols_list,
        provider=settings.provider_enabled,
        llm=settings.llm_enabled,
        telegram=settings.telegram_enabled,
        candles=candles,
        signals=signals,
        open_signals=open_signals,
    )


@router.post("/scan", tags=["control"])
def trigger_scan(
    background: BackgroundTasks,
    timeframe: str | None = None,
    symbol: str | None = None,
    db: Session = Depends(get_db),
):
    """Manually trigger a fetch + CRT scan.

    Optional `?symbol=BTC/USD` and/or `?timeframe=15min` scan a subset;
    otherwise all configured (symbol, timeframe) pairs are scanned.
    """
    try:
        new_signals = run_scan(db, timeframe=timeframe, symbol=symbol)
    except Exception as exc:
        log.exception("Manual scan failed")
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    # analyze + notify in the background (don't block the request)
    for sig in new_signals:
        background.add_task(_bg_analyze, sig.id)
    return {
        "new_signals": len(new_signals),
        "signal_ids": [s.id for s in new_signals],
        "symbol": symbol or "all",
        "timeframe": timeframe or "all",
    }


@router.post("/signals/{signal_id}/analyze", tags=["control"])
def trigger_analyze(signal_id: int, background: BackgroundTasks, db: Session = Depends(get_db)):
    sig = db.get(Signal, signal_id)
    if sig is None:
        raise HTTPException(status_code=404, detail="Signal not found")
    background.add_task(_bg_analyze, signal_id)
    return {"status": "queued", "signal_id": signal_id}


def _bg_analyze(signal_id: int) -> None:
    """Background task: open its own session, run analysis, publish event."""
    from ..db import SessionLocal
    from ..events import bus
    from ..notify.telegram_bot import send_signal

    db = SessionLocal()
    try:
        sig = db.get(Signal, signal_id)
        if sig is None:
            return
        analysis = analyze_signal(db, signal_id)
        try:
            send_signal(sig, analysis)
        except Exception as exc:
            log.warning("Telegram notify failed: %s", exc)
        if analysis is not None:
            bus.publish({"type": "analysis", "data": {"signal_id": signal_id}})
    finally:
        db.close()
