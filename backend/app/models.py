"""SQLAlchemy ORM models."""
from datetime import datetime, timezone

from sqlalchemy import (
    Boolean,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .db import Base


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Candle(Base):
    __tablename__ = "candles"
    __table_args__ = (UniqueConstraint("symbol", "timeframe", "ts", name="uq_candle_key"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    symbol: Mapped[str] = mapped_column(String(16), index=True, default="XAU/USD")
    timeframe: Mapped[str] = mapped_column(String(8), default="4h")  # widened for "15min" etc.
    ts: Mapped[datetime] = mapped_column(index=True)  # candle open time (UTC)
    open: Mapped[float] = mapped_column(Float)
    high: Mapped[float] = mapped_column(Float)
    low: Mapped[float] = mapped_column(Float)
    close: Mapped[float] = mapped_column(Float)
    volume: Mapped[float] = mapped_column(Float, default=0.0)

    def __repr__(self) -> str:
        return f"<Candle {self.symbol} {self.ts} close={self.close}>"


class Signal(Base):
    __tablename__ = "signals"
    __table_args__ = (
        UniqueConstraint("symbol", "timeframe", "candle_ts", "direction", name="uq_signal_key"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    created_at: Mapped[datetime] = mapped_column(default=_utcnow, index=True)
    symbol: Mapped[str] = mapped_column(String(16), default="XAU/USD")
    timeframe: Mapped[str] = mapped_column(String(8), default="4h")  # widened for "15min" etc.
    candle_ts: Mapped[datetime] = mapped_column(index=True)  # sweep/displacement candle

    direction: Mapped[str] = mapped_column(String(8))  # LONG | SHORT
    # CRT structure
    range_high: Mapped[float] = mapped_column(Float)
    range_low: Mapped[float] = mapped_column(Float)
    sweep_level: Mapped[float] = mapped_column(Float)
    fvg_top: Mapped[float] = mapped_column(Float)
    fvg_bottom: Mapped[float] = mapped_column(Float)
    # Trade plan
    entry: Mapped[float] = mapped_column(Float)
    sl: Mapped[float] = mapped_column(Float)
    tp: Mapped[float] = mapped_column(Float)
    atr: Mapped[float] = mapped_column(Float)
    # Context
    session: Mapped[str] = mapped_column(String(16), default="")   # Asia/London/NY
    dow: Mapped[int] = mapped_column(Integer, default=0)           # 0=Mon..6=Sun
    confidence: Mapped[float] = mapped_column(Float, default=0.0)  # 0-100 heuristic
    # Strategy enhancement (ICT premium/discount + killzones)
    premium_discount: Mapped[str] = mapped_column(String(12), default="equilibrium")
    in_killzone: Mapped[bool] = mapped_column(default=False)
    killzone: Mapped[str] = mapped_column(String(8), default="")
    entry_model: Mapped[str] = mapped_column(String(16), default="FVG_midpoint")
    # Lifecycle
    status: Mapped[str] = mapped_column(String(16), default="open", index=True)
    # open | filled | win | loss | expired

    analysis: Mapped["Analysis | None"] = relationship(
        back_populates="signal", uselist=False, cascade="all, delete-orphan"
    )
    outcome: Mapped["Outcome | None"] = relationship(
        back_populates="signal", uselist=False, cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<Signal #{self.id} {self.direction} {self.candle_ts}>"


class Analysis(Base):
    __tablename__ = "analyses"

    signal_id: Mapped[int] = mapped_column(
        ForeignKey("signals.id", ondelete="CASCADE"), primary_key=True
    )
    llm_model: Mapped[str] = mapped_column(String(64), default="")
    bias: Mapped[str] = mapped_column(String(16), default="")     # LONG/SHORT/NEUTRAL
    llm_confidence: Mapped[float] = mapped_column(Float, default=0.0)
    reasoning_md: Mapped[str] = mapped_column(Text, default="")
    key_levels: Mapped[str] = mapped_column(Text, default="{}")   # JSON
    latency_ms: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(default=_utcnow)

    signal: Mapped["Signal"] = relationship(back_populates="analysis")


class Outcome(Base):
    __tablename__ = "outcomes"

    signal_id: Mapped[int] = mapped_column(
        ForeignKey("signals.id", ondelete="CASCADE"), primary_key=True
    )
    result: Mapped[str] = mapped_column(String(16))  # win | loss | expired
    r_multiple: Mapped[float] = mapped_column(Float, default=0.0)
    resolved_at: Mapped[datetime] = mapped_column(default=_utcnow, index=True)
    hit_price: Mapped[float] = mapped_column(Float, default=0.0)
    hit_ts: Mapped[datetime | None] = mapped_column(nullable=True)

    signal: Mapped["Signal"] = relationship(back_populates="outcome")


class PerfSummary(Base):
    __tablename__ = "perf_summaries"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    generated_at: Mapped[datetime] = mapped_column(default=_utcnow, index=True)
    win_rate_20: Mapped[float] = mapped_column(Float, default=0.0)
    win_rate_50: Mapped[float] = mapped_column(Float, default=0.0)
    avg_r: Mapped[float] = mapped_column(Float, default=0.0)
    sample_size: Mapped[int] = mapped_column(Integer, default=0)
    by_session: Mapped[str] = mapped_column(Text, default="{}")   # JSON
    by_direction: Mapped[str] = mapped_column(Text, default="{}")  # JSON
    narrative: Mapped[str] = mapped_column(Text, default="")       # human-readable summary
