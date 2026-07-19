"""Signal list + detail endpoints."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..ai.analyzer import analysis_one_liner
from ..db import get_db
from ..models import Signal
from ..schemas import SignalOut

router = APIRouter()


def _attach_one_liner(sig: Signal) -> str:
    return analysis_one_liner(sig.analysis)


def _to_out(sig: Signal) -> SignalOut:
    out = SignalOut.model_validate(sig)
    out.one_liner = _attach_one_liner(sig)
    return out


@router.get("/signals", response_model=list[SignalOut], tags=["signals"])
def list_signals(
    status: str | None = Query(None, description="open|win|loss|expired"),
    timeframe: str | None = Query(None, description="5min/15min/1h/4h"),
    symbol: str | None = Query(None, description="XAU/USD, BTC/USD, ..."),
    limit: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
):
    stmt = select(Signal).order_by(Signal.created_at.desc())
    if status:
        stmt = stmt.where(Signal.status == status)
    if timeframe:
        stmt = stmt.where(Signal.timeframe == timeframe)
    if symbol:
        stmt = stmt.where(Signal.symbol == symbol)
    stmt = stmt.limit(limit)
    rows = db.execute(stmt).scalars().all()
    return [_to_out(s) for s in rows]


@router.get("/signals/{signal_id}", response_model=SignalOut, tags=["signals"])
def get_signal(signal_id: int, db: Session = Depends(get_db)):
    sig = db.get(Signal, signal_id)
    if sig is None:
        raise HTTPException(status_code=404, detail="Signal not found")
    return _to_out(sig)
