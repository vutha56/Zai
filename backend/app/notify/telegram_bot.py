"""Telegram notifier — pushes new CRT signals to a chat/channel.

No-op (returns False) when TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID are unset, so the
rest of the app keeps working without Telegram configured.
"""
from __future__ import annotations

import logging

import httpx

from ..ai.analyzer import analysis_one_liner
from ..config import settings
from ..models import Analysis, Signal

log = logging.getLogger(__name__)


def _enabled() -> bool:
    return settings.telegram_enabled


def send_signal(signal: Signal, analysis: Analysis | None) -> bool:
    """Send a single new-signal alert. Returns True on success."""
    if not _enabled():
        return False
    text = _format_signal(signal, analysis)
    return _send(text)


def send_daily_summary(win20: float, avg_r: float, n: int, open_count: int) -> bool:
    if not _enabled():
        return False
    text = (
        f"📊 *XAUUSD CRT — Daily Summary*\n\n"
        f"Tracked setups: {n}\n"
        f"Win rate (last 20): *{win20:.1f}%*\n"
        f"Avg R-multiple: *{avg_r:+.2f}R*\n"
        f"Currently open: {open_count}"
    )
    return _send(text)


def _format_signal(signal: Signal, analysis: Analysis | None) -> str:
    arrow = "🟢 LONG" if signal.direction == "LONG" else "🔴 SHORT"
    one_liner = analysis_one_liner(analysis)
    bias_line = ""
    if analysis is not None:
        bias_line = f"\n🤖 AI bias: *{analysis.bias}* ({analysis.llm_confidence:.0f}/100)"
    sym = (signal.symbol or "").replace("/", "")  # XAUUSD / BTCUSD
    return (
        f"{arrow}  *{sym} · CRT {signal.timeframe}*\n"
        f"_{signal.session} session · conf {signal.confidence:.0f}_\n\n"
        f"▸ Entry: `{signal.entry}`\n"
        f"▸ Stop:  `{signal.sl}`\n"
        f"▸ Target:`{signal.tp}`\n\n"
        f"FVG `{signal.fvg_bottom}`–`{signal.fvg_top}`  |  sweep `{signal.sweep_level}`"
        f"{bias_line}\n\n"
        f"_{one_liner}_"
    )


def _send(text: str) -> bool:
    url = f"https://api.telegram.org/bot{settings.telegram_bot_token}/sendMessage"
    payload = {
        "chat_id": settings.telegram_chat_id,
        "text": text,
        "parse_mode": "Markdown",
        "disable_web_page_preview": True,
    }
    try:
        with httpx.Client(timeout=15.0) as client:
            resp = client.post(url, json=payload)
            resp.raise_for_status()
        log.info("Telegram notification sent to chat %s.", settings.telegram_chat_id)
        return True
    except Exception as exc:
        log.warning("Telegram send failed: %s", exc)
        return False
