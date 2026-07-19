"""Twelve Data provider — fetches XAUUSD OHLCV candles.

Designed as a pluggable interface so other providers (MT5, Alpha Vantage) can be
added later without touching the caller.
"""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from datetime import datetime, timezone

import httpx

from ..config import settings

log = logging.getLogger(__name__)


@dataclass
class CandleDTO:
    """Lightweight transfer object — maps cleanly to the Candle ORM row."""
    ts: datetime   # candle open time, tz-aware UTC
    open: float
    high: float
    low: float
    close: float
    volume: float


class TwelveDataError(RuntimeError):
    pass


class TwelveDataProvider:
    """Fetches candles from the Twelve Data REST API.

    Free-tier notes: ~8 requests/min, 800/day. We poll conservatively (every 15 min)
    and request only what we need. Responses are cached upstream by Twelve Data for
    the timeframe interval, so repeated calls within an interval are cheap.
    """

    def __init__(
        self,
        api_key: str | None = None,
        base_url: str | None = None,
        symbol: str | None = None,
        interval: str | None = None,
        timeout: float = 20.0,
    ) -> None:
        self.api_key = api_key if api_key is not None else settings.twelve_data_api_key
        self.base_url = (base_url or settings.twelve_data_base_url).rstrip("/")
        self.symbol = symbol or settings.symbol
        self.interval = interval or settings.timeframe
        self.timeout = timeout

    @property
    def enabled(self) -> bool:
        return bool(self.api_key)

    def _client(self) -> httpx.Client:
        return httpx.Client(timeout=self.timeout)

    def fetch_series(self, outputsize: int = 200) -> list[CandleDTO]:
        """Return up to `outputsize` most-recent candles, oldest-first."""
        if not self.enabled:
            raise TwelveDataError("Twelve Data API key not configured.")
        params = {
            "symbol": self.symbol,
            "interval": self.interval,
            "outputsize": outputsize,
            "format": "JSON",
            "apikey": self.api_key,
            "timezone": "UTC",
            "order": "ASC",  # oldest first
        }
        url = f"{self.base_url}/time_series"
        log.debug("Twelve Data GET %s symbol=%s interval=%s", url, self.symbol, self.interval)
        t0 = time.perf_counter()
        with self._client() as client:
            resp = client.get(url, params=params)
            resp.raise_for_status()
        payload = resp.json()
        dt_ms = int((time.perf_counter() - t0) * 1000)

        if isinstance(payload, dict) and payload.get("status") == "error":
            raise TwelveDataError(
                f"Twelve Data error: {payload.get('message')} (code {payload.get('code')})"
            )
        rows = payload.get("values") or []
        if not rows:
            log.warning("Twelve Data returned no rows (latency=%dms).", dt_ms)
            return []

        candles: list[CandleDTO] = []
        for row in rows:  # already ASC, but normalise just in case
            candles.append(
                CandleDTO(
                    ts=_parse_ts(row["datetime"]),
                    open=float(row["open"]),
                    high=float(row["high"]),
                    low=float(row["low"]),
                    close=float(row["close"]),
                    volume=float(row.get("volume") or 0.0),
                )
            )
        candles.sort(key=lambda c: c.ts)
        log.info(
            "Fetched %d candles %s %s (latency=%dms), last=%s",
            len(candles), self.symbol, self.interval, dt_ms,
            candles[-1].ts.isoformat() if candles else "n/a",
        )
        return candles

    def latest_price(self) -> float | None:
        """Best-effort current quote — used for dashboard header."""
        if not self.enabled:
            return None
        url = f"{self.base_url}/quote"
        params = {"symbol": self.symbol, "apikey": self.api_key, "format": "JSON"}
        try:
            with self._client() as client:
                resp = client.get(url, params=params, timeout=10.0)
                resp.raise_for_status()
            data = resp.json()
            return float(data.get("close") or 0.0) or None
        except Exception as exc:  # quote is best-effort only
            log.debug("quote failed: %s", exc)
            return None


def _parse_ts(raw: str | float) -> datetime:
    """Twelve Data returns 'YYYY-MM-DD HH:MM:SS' in UTC (we asked for UTC)."""
    if isinstance(raw, (int, float)):
        return datetime.fromtimestamp(float(raw), tz=timezone.utc)
    # tolerate a trailing 'Z'
    text = str(raw).strip()
    if text.endswith("Z"):
        text = text[:-1]
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M"):
        try:
            return datetime.strptime(text, fmt).replace(tzinfo=timezone.utc)
        except ValueError:
            continue
    # final fallback: ISO fromisoformat
    return datetime.fromisoformat(str(raw)).astimezone(timezone.utc)
