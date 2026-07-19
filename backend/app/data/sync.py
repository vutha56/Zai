"""Persist fetched candles into the DB (upsert on symbol/timeframe/ts)."""
from __future__ import annotations

import logging
from sqlalchemy import select
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.orm import Session

from ..models import Candle
from .twelvedata import CandleDTO, TwelveDataProvider

log = logging.getLogger(__name__)


def sync_candles(
    db: Session,
    provider: TwelveDataProvider | None = None,
    outputsize: int = 200,
) -> tuple[int, CandleDTO | None]:
    """Fetch the latest candles and upsert them. Returns (rows_affected, last_candle)."""
    provider = provider or TwelveDataProvider()
    if not provider.enabled:
        log.warning("Provider disabled — skipping candle sync.")
        return 0, None

    candles = provider.fetch_series(outputsize=outputsize)
    if not candles:
        return 0, None

    rows = [
        {
            "symbol": provider.symbol,
            "timeframe": provider.interval,
            "ts": c.ts,
            "open": c.open,
            "high": c.high,
            "low": c.low,
            "close": c.close,
            "volume": c.volume,
        }
        for c in candles
    ]

    stmt = sqlite_insert(Candle).values(rows)
    stmt = stmt.on_conflict_do_update(
        index_elements=["symbol", "timeframe", "ts"],
        set_={
            "open": stmt.excluded.open,
            "high": stmt.excluded.high,
            "low": stmt.excluded.low,
            "close": stmt.excluded.close,
            "volume": stmt.excluded.volume,
        },
    )
    result = db.execute(stmt)
    db.commit()
    affected = getattr(result, "rowcount", len(rows)) or len(rows)
    log.info("Synced %d candle rows (db reported %s).", len(rows), affected)
    return len(rows), candles[-1]


def load_candles(
    db: Session, limit: int = 200, symbol: str = "XAU/USD", timeframe: str = "5min"
) -> list[Candle]:
    """Return the most recent `limit` candles oldest-first for the given timeframe."""
    stmt = (
        select(Candle)
        .where(Candle.symbol == symbol, Candle.timeframe == timeframe)
        .order_by(Candle.ts.desc())
        .limit(limit)
    )
    rows = list(db.execute(stmt).scalars())
    rows.reverse()
    return rows
