"""Backtest API router — runs the CRT strategy over historical DB candles."""
from __future__ import annotations

import logging

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from ..backtest.engine import run_backtest
from ..config import settings
from ..data.sync import load_candles
from ..db import get_db
from ..strategy.scanner import candles_to_dto
from ..schemas import BacktestResultOut, BacktestTradeOut

router = APIRouter()
log = logging.getLogger(__name__)


class BacktestRequest(BaseModel):
    symbol: str = "XAU/USD"
    timeframe: str = "4h"
    candles_limit: int = Field(500, ge=50, le=5000)
    lookforward_bars: int = Field(8, ge=1, le=50)
    min_confidence: float = Field(0.0, ge=0.0, le=100.0)
    initial_capital: float = Field(10000.0, gt=0.0)
    risk_per_trade_pct: float = Field(1.0, gt=0.0, le=10.0)
    # optional strategy overrides (None -> use defaults / tf_overrides)
    range_window: int | None = None
    displacement_k: float | None = None
    min_rr: float | None = None


@router.get("/backtest/options", tags=["backtest"])
def backtest_options():
    """Return available symbols/timeframes + default params for the form."""
    return {
        "symbols": settings.symbols_list,
        "timeframes": settings.timeframes,
        "defaults": {
            "candles_limit": 500,
            "lookforward_bars": settings.crt_lookforward_candles * 2 + 2,
            "min_confidence": 0.0,
            "initial_capital": 10000.0,
            "risk_per_trade_pct": 1.0,
            "range_window": settings.crt_range_window,
            "displacement_k": settings.crt_displacement_k,
            "min_rr": settings.crt_min_rr,
        },
    }


@router.post("/backtest", response_model=BacktestResultOut, tags=["backtest"])
def run_backtest_endpoint(req: BacktestRequest, db: Session = Depends(get_db)):
    """Run a backtest. Reads candles from the DB (sync them via /scan first)."""
    rows = load_candles(
        db, limit=req.candles_limit, symbol=req.symbol, timeframe=req.timeframe
    )
    if len(rows) < 12:
        log.info("Backtest: not enough candles (%d) for %s %s", len(rows), req.symbol, req.timeframe)
        return BacktestResultOut(
            symbol=req.symbol, timeframe=req.timeframe,
            metrics={"trades": 0, "error": "not enough candles — run a scan first"},
            equity_curve=[], trades=[],
        )

    result = run_backtest(
        candles=candles_to_dto(rows),
        timeframe=req.timeframe,
        symbol=req.symbol,
        range_window=req.range_window,
        displacement_k=req.displacement_k,
        min_rr=req.min_rr,
        tf_overrides=settings.tf_overrides,
        lookforward_bars=req.lookforward_bars,
        min_confidence=req.min_confidence,
        initial_capital=req.initial_capital,
        risk_per_trade_pct=req.risk_per_trade_pct,
    )
    return BacktestResultOut(
        symbol=result.symbol,
        timeframe=result.timeframe,
        metrics=result.metrics,
        equity_curve=result.equity_curve,
        trades=[BacktestTradeOut(**{
            k: v for k, v in t.__dict__.items()
        }) for t in result.trades],
    )
