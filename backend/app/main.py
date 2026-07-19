"""FastAPI application entrypoint.

Wires routers, inits the DB, starts the scheduler, and serves the built frontend
from / (in production) or proxies via Vite (in dev).
"""
from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from .api import backtest, chart, control, events, performance, signals
from .config import settings
from .db import init_db
from .scheduler import shutdown_scheduler, start_scheduler

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-7s %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("xauusd")


@asynccontextmanager
async def lifespan(app: FastAPI):
    log.info("Startup — symbol=%s timeframe=%s", settings.symbol, settings.timeframe)
    log.info(
        "Integrations: provider=%s llm=%s telegram=%s",
        settings.provider_enabled, settings.llm_enabled, settings.telegram_enabled,
    )
    if not settings.provider_enabled:
        log.warning(
            "TWELVE_DATA_API_KEY is not set — the app will run but cannot fetch candles. "
            "Add it to backend/.env."
        )
    if not settings.llm_enabled:
        log.warning("ZAI_API_KEY is not set — textual analysis will be skipped.")

    init_db()
    start_scheduler()
    try:
        yield
    finally:
        shutdown_scheduler()
        log.info("Shutdown complete.")


app = FastAPI(
    title="XAUUSD CRT-4H Trading Signals",
    description="Candle Range Theory signals on XAUUSD 4h with AI analysis.",
    version="1.0.0",
    lifespan=lifespan,
)

# CORS: allow the Vite dev server (5173) to call the API in dev.
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

api_prefix = "/api"
app.include_router(chart.router, prefix=api_prefix)
app.include_router(signals.router, prefix=api_prefix)
app.include_router(performance.router, prefix=api_prefix)
app.include_router(control.router, prefix=api_prefix)
app.include_router(events.router, prefix=api_prefix)
app.include_router(backtest.router, prefix=api_prefix)


@app.get("/", tags=["root"])
def root():
    return {
        "name": "XAUUSD CRT-4H Trading Signals",
        "symbol": settings.symbol,
        "timeframe": settings.timeframe,
        "docs": "/docs",
        "dashboard": "run the React frontend (frontend/) on :5173",
    }


# Serve the built React SPA if it exists (production-style single-port deploy).
_FRONTEND_DIST = Path(__file__).resolve().parents[2] / "frontend" / "dist"
if _FRONTEND_DIST.exists():
    app.mount("/app", StaticFiles(directory=str(_FRONTEND_DIST), html=True), name="app")
