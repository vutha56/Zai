"""APscheduler jobs: periodic fetch+scan, and daily outcome/perf rebuild.

Runs in a BackgroundScheduler (separate thread). The scan job publishes new
signals to the EventBus so SSE subscribers get them live.
"""
from __future__ import annotations

import logging
import traceback

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger

from .ai.analyzer import analyze_signal
from .config import settings
from .db import SessionLocal
from .events import bus
from .feedback.outcomes import rebuild_perf_summary, resolve_outcomes
from .notify.telegram_bot import send_signal
from .strategy.scanner import run_scan

log = logging.getLogger(__name__)
_scheduler: BackgroundScheduler | None = None


def start_scheduler() -> None:
    global _scheduler
    if _scheduler is not None:
        return
    _scheduler = BackgroundScheduler(timezone="UTC")
    # fetch + scan every 15 minutes (configurable via scan_cron_minutes)
    minute_expr = settings.scan_cron_minutes or "*/15"
    _scheduler.add_job(
        job_scan,
        CronTrigger.from_crontab(f"{minute_expr} * * * *"),
        id="scan",
        max_instances=1,
        coalesce=True,
    )
    # also kick one off ~30s after startup
    _scheduler.add_job(job_scan, "date", run_date=None, id="scan-bootstrap") if False else None
    # daily outcome resolution + perf rebuild at 06:00 UTC
    _scheduler.add_job(
        job_daily,
        CronTrigger(hour=6, minute=5),
        id="daily",
        max_instances=1,
        coalesce=True,
    )
    _scheduler.start()
    log.info("Scheduler started: scan every '%s' min, daily at 06:05 UTC.", minute_expr)
    # run an initial scan + resolve shortly after start
    _scheduler.add_job(job_scan, "date", id="scan-initial")


def shutdown_scheduler() -> None:
    global _scheduler
    if _scheduler:
        _scheduler.shutdown(wait=False)
        _scheduler = None


def job_scan() -> None:
    """One scan cycle: fetch candles, detect new CRT setups, analyze + notify."""
    log.info("Scan job starting.")
    db = SessionLocal()
    try:
        new_signals = run_scan(db)
        for sig in new_signals:
            analysis = analyze_signal(db, sig.id)
            # publish SSE event
            bus.publish({
                "type": "signal",
                "data": _serialize_signal(sig, analysis),
            })
            # telegram
            try:
                send_signal(sig, analysis)
            except Exception as exc:
                log.warning("Telegram notify failed for signal %s: %s", sig.id, exc)
        if new_signals:
            log.info("Scan job done: %d new signal(s).", len(new_signals))
        else:
            log.info("Scan job done: no new signals.")
    except Exception:
        log.error("Scan job failed:\n%s", traceback.format_exc())
    finally:
        db.close()


def job_daily() -> None:
    """Daily backfill: resolve matured outcomes and rebuild performance summary."""
    log.info("Daily job starting.")
    db = SessionLocal()
    try:
        resolved = resolve_outcomes(db)
        summary = rebuild_perf_summary(db)
        if summary:
            from .models import Signal
            from sqlalchemy import select, func
            open_count = db.scalar(
                select(func.count()).select_from(Signal).where(Signal.status == "open")
            ) or 0
            try:
                from .notify.telegram_bot import send_daily_summary
                send_daily_summary(summary.win_rate_20, summary.avg_r, summary.sample_size, open_count)
            except Exception as exc:
                log.warning("Daily summary notify failed: %s", exc)
            bus.publish({
                "type": "performance",
                "data": {
                    "win_rate_20": summary.win_rate_20,
                    "win_rate_50": summary.win_rate_50,
                    "avg_r": summary.avg_r,
                    "sample_size": summary.sample_size,
                    "narrative": summary.narrative,
                },
            })
        log.info("Daily job done: resolved=%d.", resolved)
    except Exception:
        log.error("Daily job failed:\n%s", traceback.format_exc())
    finally:
        db.close()


def _serialize_signal(sig, analysis) -> dict:
    return {
        "id": sig.id,
        "direction": sig.direction,
        "symbol": sig.symbol,
        "timeframe": sig.timeframe,
        "candle_ts": sig.candle_ts.isoformat(),
        "entry": sig.entry,
        "sl": sig.sl,
        "tp": sig.tp,
        "confidence": sig.confidence,
        "session": sig.session,
        "premium_discount": sig.premium_discount,
        "in_killzone": sig.in_killzone,
        "killzone": sig.killzone,
        "entry_model": sig.entry_model,
        "bias": analysis.bias if analysis else None,
        "one_liner": _one_liner(analysis, sig),
    }


def _one_liner(analysis, sig) -> str:
    if analysis is None:
        return "No AI analysis available."
    import re
    bold = re.search(r"\*\*(.+?)\*\*", analysis.reasoning_md or "")
    return bold.group(1).strip() if bold else f"Bias: {analysis.bias} ({analysis.llm_confidence:.0f}/100)"
