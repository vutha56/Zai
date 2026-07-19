"""Database engine, session factory, and declarative base."""
import logging
from collections.abc import Generator

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from .config import settings

log = logging.getLogger(__name__)

engine = create_engine(
    settings.database_url,
    connect_args={"check_same_thread": False},  # SQLite + threads (scheduler)
    future=True,
)

SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)


class Base(DeclarativeBase):
    pass


def get_db() -> Generator[Session, None, None]:
    """FastAPI dependency: yields a session and always closes it."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db() -> None:
    """Create all tables + run idempotent migrations. Safe to call on every startup."""
    from . import models  # noqa: F401 — ensure mappers are registered

    Base.metadata.create_all(bind=engine)
    migrate()


def migrate() -> None:
    """Idempotent schema evolution for SQLite.

    SQLAlchemy's create_all only creates missing tables — it won't ALTER existing
    ones. We handle column additions + the new unique index here so existing
    dev databases upgrade in place without data loss.
    """
    insp = inspect(engine)

    # --- signals: add new columns if missing ---
    if insp.has_table("signals"):
        existing_cols = {c["name"] for c in insp.get_columns("signals")}
        new_columns = {
            "premium_discount": "TEXT DEFAULT 'equilibrium'",
            "in_killzone": "BOOLEAN DEFAULT 0",
            "killzone": "TEXT DEFAULT ''",
            "entry_model": "TEXT DEFAULT 'FVG_midpoint'",
        }
        for col, ddl in new_columns.items():
            if col not in existing_cols:
                with engine.begin() as conn:
                    conn.execute(text(f"ALTER TABLE signals ADD COLUMN {col} {ddl}"))
                log.info("Migration: added column signals.%s", col)

        # --- unique index for dedup across timeframes ---
        # Drop any partial/legacy index with the same name first, then create.
        existing_indexes = {idx["name"] for idx in insp.get_indexes("signals")}
        if "uq_signal_key" not in existing_indexes:
            # dedupe any rows that would collide before creating the unique index
            with engine.begin() as conn:
                conn.execute(text(
                    "DELETE FROM signals WHERE id NOT IN ("
                    "  SELECT MIN(id) FROM signals GROUP BY symbol, timeframe, candle_ts, direction"
                    ")"
                ))
                conn.execute(text(
                    "CREATE UNIQUE INDEX IF NOT EXISTS uq_signal_key "
                    "ON signals (symbol, timeframe, candle_ts, direction)"
                ))
            log.info("Migration: created uq_signal_key unique index")

