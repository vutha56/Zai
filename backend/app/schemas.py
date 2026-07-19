"""Pydantic response schemas (serialization for the API)."""
from __future__ import annotations

import json
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, field_validator


class AnalysisOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    llm_model: str = ""
    bias: str = ""
    llm_confidence: float = 0.0
    reasoning_md: str = ""
    key_levels: dict[str, Any] = {}
    latency_ms: int = 0
    created_at: datetime | None = None

    @field_validator("key_levels", mode="before")
    @classmethod
    def _coerce_key_levels(cls, v):
        """The ORM stores key_levels as a JSON string; coerce to dict here."""
        if v is None or v == "":
            return {}
        if isinstance(v, str):
            try:
                parsed = json.loads(v)
                return parsed if isinstance(parsed, dict) else {}
            except json.JSONDecodeError:
                return {}
        return v


class OutcomeOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    result: str
    r_multiple: float
    hit_price: float
    hit_ts: datetime | None = None
    resolved_at: datetime


class SignalOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    symbol: str
    timeframe: str
    candle_ts: datetime
    created_at: datetime
    direction: str
    range_high: float
    range_low: float
    sweep_level: float
    fvg_top: float
    fvg_bottom: float
    entry: float
    sl: float
    tp: float
    atr: float
    session: str
    dow: int
    confidence: float
    status: str
    premium_discount: str = "equilibrium"
    in_killzone: bool = False
    killzone: str = ""
    entry_model: str = "FVG_midpoint"
    analysis: AnalysisOut | None = None
    outcome: OutcomeOut | None = None
    one_liner: str = ""


class CandleOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    ts: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float = 0.0
    symbol: str = ""
    timeframe: str = ""


class PerfOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    generated_at: datetime | None = None
    win_rate_20: float = 0.0
    win_rate_50: float = 0.0
    avg_r: float = 0.0
    sample_size: int = 0
    by_session: dict[str, Any] = {}
    by_direction: dict[str, Any] = {}
    narrative: str = ""

    @field_validator("by_session", "by_direction", mode="before")
    @classmethod
    def _coerce_json_dict(cls, v):
        """ORM stores these as JSON strings; coerce to dict here."""
        if v is None or v == "":
            return {}
        if isinstance(v, str):
            try:
                parsed = json.loads(v)
                return parsed if isinstance(parsed, dict) else {}
            except json.JSONDecodeError:
                return {}
        return v


class HealthOut(BaseModel):
    status: str
    symbol: str
    timeframe: str
    timeframes: list[str] = []
    symbols: list[str] = []
    provider: bool
    llm: bool
    telegram: bool
    candles: int
    signals: int
    open_signals: int


class BacktestTradeOut(BaseModel):
    candle_ts: datetime
    direction: str
    entry: float
    sl: float
    tp: float
    confidence: float
    premium_discount: str
    killzone: str
    result: str
    r_multiple: float
    hit_ts: datetime | None = None
    bars_to_resolve: int


class BacktestResultOut(BaseModel):
    symbol: str
    timeframe: str
    metrics: dict[str, Any]
    equity_curve: list[dict[str, Any]]
    trades: list[BacktestTradeOut]
