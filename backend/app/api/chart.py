"""Chart endpoints — candlesticks, latest quote, SMC levels, ICT context."""
from __future__ import annotations

import threading
import time

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from ..data.sync import load_candles
from ..data.twelvedata import TwelveDataProvider
from ..db import get_db
from ..schemas import CandleOut
from ..strategy.bias import compute_daily_bias, detect_power_of_3, to_daily
from ..strategy.scanner import candles_to_dto
from ..strategy.smc import all_levels
from ..strategy.structure import market_structure
from ..strategy.volumeprofile import compute_volume_profile

router = APIRouter()


@router.get("/candles", response_model=list[CandleOut], tags=["chart"])
def get_candles(
    limit: int = Query(200, ge=1, le=500),
    timeframe: str = Query("5min", description="5min/15min/1h/4h"),
    symbol: str = Query("XAU/USD", description="XAU/USD, BTC/USD, ..."),
    db: Session = Depends(get_db),
):
    rows = load_candles(db, limit=limit, symbol=symbol, timeframe=timeframe)
    return [CandleOut.model_validate(r) for r in rows]


@router.get("/smc", tags=["chart"])
def get_smc(
    limit: int = Query(300, ge=50, le=1000),
    timeframe: str = Query("5min", description="5min/15min/1h/4h"),
    symbol: str = Query("XAU/USD", description="XAU/USD, BTC/USD, ..."),
    db: Session = Depends(get_db),
):
    """Smart Money Concepts levels for the chart: FVG, iFVG, Order Blocks,
    Breaker Blocks, and Previous/Current Daily High-Low. Computed on demand
    from stored candles (no persistence)."""
    rows = load_candles(db, limit=limit, symbol=symbol, timeframe=timeframe)
    if len(rows) < 10:
        return {"fvgs": [], "ifvgs": [], "order_blocks": [], "breakers": [], "daily": {}}
    return all_levels(candles_to_dto(rows))


@router.get("/context", tags=["chart"])
def get_context(
    limit: int = Query(300, ge=50, le=1000),
    timeframe: str = Query("5min", description="5min/15min/1h/4h"),
    symbol: str = Query("XAU/USD", description="XAU/USD, BTC/USD, ..."),
    db: Session = Depends(get_db),
):
    """ICT context overlay for the chart: daily bias, market structure,
    volume profile, and Power-of-3. Computed on demand from stored candles.

    Returns {bias, structure, volume_profile, po3}. Each section degrades
    gracefully to a neutral/empty shape when there isn't enough data.
    """
    rows = load_candles(db, limit=limit, symbol=symbol, timeframe=timeframe)
    if len(rows) < 5:
        return {
            "bias": {"bias": "neutral", "note": "not enough candles"},
            "structure": {"trend": "range", "swings": [], "events": [],
                          "last_bos": None, "last_choch": None, "last_mss": None},
            "volume_profile": {"poc": None, "vah": None, "val": None, "bins": []},
            "po3": {"po3_signal": None, "note": "not enough candles"},
        }
    dtos = candles_to_dto(rows)

    # Daily bias: roll up to D1 unless the source timeframe is already daily.
    tf_lower = (timeframe or "").strip().lower()
    is_daily = tf_lower in ("1day", "1d", "day", "d")
    daily = dtos if is_daily else to_daily(dtos)
    bias = compute_daily_bias(daily, h4_candles=None if is_daily else dtos)

    structure = market_structure(dtos)
    volume_profile = compute_volume_profile(dtos, symbol=symbol)
    po3 = detect_power_of_3(dtos, timeframe)

    return {
        "bias": bias,
        "structure": structure,
        "volume_profile": volume_profile,
        "po3": po3,
    }


# --- Quote cache: protect the Twelve Data free-tier rate limit (8 req/min).
# The dashboard polls /quote frequently; we hit Twelve Data at most once per 60s
# per symbol. Keyed by symbol so XAU and BTC don't share a slot.
_QUOTE_TTL = 60.0
_quote_cache: dict[str, dict] = {}
_quote_lock = threading.Lock()


@router.get("/quote", tags=["chart"])
def get_quote(symbol: str = Query("XAU/USD")):
    """Best-effort latest price (live). Cached 60s per symbol.

    Falls back to the most recent candle close in the DB if the provider is
    unavailable or rate-limited — so the header always shows a sensible number.
    """
    now = time.time()
    with _quote_lock:
        slot = _quote_cache.get(symbol)
        if slot and slot.get("price") is not None and (now - slot["fetched_at"]) < _QUOTE_TTL:
            return {"price": slot["price"], "source": "cache", "symbol": symbol}

    # Cache miss or stale — fetch fresh (but don't block on errors)
    price = None
    source = "twelvedata"
    try:
        price = TwelveDataProvider(symbol=symbol).latest_price()
    except Exception:
        price = None
    if price is None:
        # fallback: last candle close
        from ..db import SessionLocal
        from ..data.sync import load_candles

        session = SessionLocal()
        try:
            rows = load_candles(session, limit=1, symbol=symbol)
            if rows:
                price = rows[-1].close
                source = "lastclose"
        finally:
            session.close()

    with _quote_lock:
        _quote_cache[symbol] = {"price": price, "fetched_at": now}
    return {"price": price, "source": source, "symbol": symbol}
