"""Analyze a stored Signal: build prompt (setup + recent perf), call ZAI, persist."""
from __future__ import annotations

import json
import logging
from datetime import timezone

from sqlalchemy.orm import Session

from ..feedback.outcomes import get_latest_perf_text
from ..models import Analysis, Signal
from .llm import ZAIClient, extract_json
from .prompts import build_user_prompt, system_prompt_for

log = logging.getLogger(__name__)

_DOW = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]


def analyze_signal(db: Session, signal_id: int) -> Analysis | None:
    """Generate (or regenerate) the LLM analysis for a signal. Graceful on failure."""
    sig = db.get(Signal, signal_id)
    if sig is None:
        return None

    # Replace any existing analysis row (PK = signal_id)
    existing = db.get(Analysis, signal_id)
    if existing:
        db.delete(existing)
        db.commit()

    client = ZAIClient()
    if not client.enabled:
        log.info("LLM disabled; skipping analysis for signal %s.", signal_id)
        return None

    perf_text = get_latest_perf_text(db)
    user_prompt = build_user_prompt(
        symbol=sig.symbol,
        timeframe=sig.timeframe,
        setup_block=_setup_block(sig),
        perf_block=perf_text,
    )

    result = client.chat_json(system_prompt_for(sig.symbol), user_prompt, temperature=0.4)
    if not result.ok:
        log.warning("Analysis failed for signal %s: %s", signal_id, result.error)
        return None

    data = extract_json(result.text) or {}
    if not data:
        log.warning("Could not parse JSON for signal %s. Raw: %.200s", signal_id, result.text)

    analysis = Analysis(
        signal_id=signal_id,
        llm_model=result.model,
        bias=str(data.get("bias", "")).upper() or _default_bias(sig),
        llm_confidence=_as_float(data.get("confidence"), default=sig.confidence),
        reasoning_md=_render_reasoning(data, result.text),
        key_levels=json.dumps(data.get("key_levels") or {}),
        latency_ms=result.latency_ms,
    )
    db.add(analysis)
    db.commit()
    db.refresh(analysis)
    log.info("Analyzed signal %s -> bias=%s conf=%.0f (%dms)",
             signal_id, analysis.bias, analysis.llm_confidence, analysis.latency_ms)
    return analysis


def _setup_block(sig: Signal) -> str:
    equilibrium = (sig.range_high + sig.range_low) / 2.0
    # describe premium/discount alignment for this direction
    if sig.direction == "LONG":
        pd_aligned = sig.entry < equilibrium
        pd_note = "entry is in the DISCOUNT half (aligned for a long)" if pd_aligned \
            else "entry is in the PREMIUM half (MISALIGNED for a long — lower quality)"
    else:
        pd_aligned = sig.entry > equilibrium
        pd_note = "entry is in the PREMIUM half (aligned for a short)" if pd_aligned \
            else "entry is in the DISCOUNT half (MISALIGNED for a short — lower quality)"
    kz_note = (
        f"displacement candle is INSIDE the {sig.killzone} killzone (higher probability)"
        if sig.in_killzone
        else "displacement candle is OUTSIDE all killzones (lower priority; avoid if Asian session)"
    )
    lines = [
        f"Timeframe: {sig.timeframe}",
        f"Direction: {sig.direction}",
        f"Session (UTC): {sig.session or 'n/a'}  |  Day: {_DOW[sig.dow] if 0 <= sig.dow < 7 else 'n/a'}",
        f"ATR: {sig.atr:.3f}",
        "",
        "Structure:",
        f"  Range high / low : {sig.range_high:.3f} / {sig.range_low:.3f}",
        f"  Equilibrium      : {equilibrium:.3f}",
        f"  Sweep level      : {sig.sweep_level:.3f}",
        f"  FVG              : {sig.fvg_bottom:.3f} - {sig.fvg_top:.3f}",
        "",
        "Trade plan (already computed):",
        f"  Entry model : {sig.entry_model} (entry at FVG midpoint)",
        f"  Entry       : {sig.entry:.3f}",
        f"  Stop        : {sig.sl:.3f}    (beyond sweep wick + buffer)",
        f"  Target      : {sig.tp:.3f}    (opposite range liquidity, min 1:2 R)",
        f"  R:R         : {abs(sig.tp - sig.entry) / max(abs(sig.entry - sig.sl), 1e-9):.2f}",
        "",
        "Quality context (ICT enhancement):",
        f"  Premium/Discount : {sig.premium_discount} — {pd_note}",
        f"  Killzone         : {kz_note}",
        "",
        f"Detection confidence (heuristic): {sig.confidence:.0f}/100",
    ]
    return "\n".join(lines)


def _render_reasoning(data: dict, raw_text: str) -> str:
    """Render the analysis as clean markdown for the frontend."""
    if not data:
        return f"```\n{raw_text[:1500]}\n```"
    out = []
    summary = data.get("summary")
    if summary:
        out.append(f"**{summary}**\n")
    reasoning = data.get("reasoning") or []
    if isinstance(reasoning, list) and reasoning:
        out.append("### Reasoning")
        for r in reasoning:
            out.append(f"- {r}")
        out.append("")
    risks = data.get("risks") or []
    if isinstance(risks, list) and risks:
        out.append("### Risks")
        for r in risks:
            out.append(f"- {r}")
    return "\n".join(out) if out else (raw_text[:1500] or "_No analysis._")


def _as_float(v, default: float = 0.0) -> float:
    try:
        return float(v)
    except (TypeError, ValueError):
        return default


def _default_bias(sig: Signal) -> str:
    return "LONG" if sig.direction == "LONG" else "SHORT"


def analysis_one_liner(analysis: Analysis | None) -> str:
    """Short summary for cards/Telegram — pulls the first sentence of reasoning."""
    if analysis is None:
        return "No AI analysis available (set ZAI_API_KEY to enable)."
    md = analysis.reasoning_md or ""
    # grab a bolded **...** line or first sentence
    import re
    bold = re.search(r"\*\*(.+?)\*\*", md)
    if bold:
        return bold.group(1).strip()
    first = md.split("\n")[0].strip(" -")
    return first[:160] or f"Bias: {analysis.bias} · confidence {analysis.llm_confidence:.0f}/100"
