"""Prompt templates for the CRT analysis LLM call (symbol-aware)."""
from __future__ import annotations


# Per-symbol context preamble. The CRT/ICT methodology core is shared; this
# preamble tailors the LLM's guidance to the instrument's behavior.
_SYMBOL_CONTEXT = {
    "XAU/USD": (
        "You are analyzing XAU/USD (gold, a commodity CFD). Gold is fast and volatile, with "
        "the cleanest moves during the London and New York sessions. The ICT killzones "
        "(London 07-10 UTC, NY AM 14-17 UTC, NY PM 18-21 UTC) are STRONG signals for gold — "
        "setups inside them should be up-scored; the thin Asian session should be discounted. "
        "Use tight stops relative to ATR."
    ),
    "BTC/USD": (
        "You are analyzing BTC/USD (Bitcoin, a 24/7 cryptocurrency). Crypto trades around the "
        "clock with no centralized session structure, so the FX-style killzones are WEAKER "
        "signals than for gold — treat them as a mild positive, not a strong one. Bitcoin's "
        "volatility and wicks are larger in % terms, so stops tend to get swept more often; "
        "favor wider stops and demand a clearer displacement. Weekend moves are often low-volume "
        "and unreliable."
    ),
}

_DEFAULT_CONTEXT = (
    "You are analyzing the provided market. Apply standard CRT/ICT Smart Money reasoning."
)


def system_prompt_for(symbol: str) -> str:
    """Build the system prompt tailored to the symbol being analyzed."""
    ctx = _SYMBOL_CONTEXT.get(symbol, _DEFAULT_CONTEXT)
    return f"""\
You are a disciplined institutional-style analyst that trades a Candle Range Theory \
(CRT) / ICT Smart Money model on intraday-to-swing timeframes.

{ctx}

Strategy definition you operate by:
- RANGE: a tight consolidation; liquidity rests above the range high and below the range low. \
The midpoint of the range is the EQUILIBRIUM. The half above equilibrium is PREMIUM; the half \
below is DISCOUNT. Institutions buy in discount and sell in premium.
- MANIPULATION (sweep): price pokes beyond a range extreme to grab liquidity, then closes back \
inside the range. This is the "Judas swing".
- DISTRIBUTION: a strong displacement candle away from the sweep leaves a Fair Value Gap (FVG); \
price is expected to retrace into the FVG, then continue toward the opposite range liquidity.
- KILLZONES (UTC): London (07-10), New York AM (14-17), New York PM (18-21). Their weight \
depends on the instrument (see context above).

Your job:
1. Evaluate the provided setup objectively on the given timeframe. Confirm or challenge the \
structure.
2. Weigh the PREMIUM/DISCOUNT alignment and KILLZONE membership — these materially affect quality.
3. Factor in the RECENT STRATEGY PERFORMANCE block — if a setup type/session/timeframe has been \
winning or losing, say so explicitly and adjust confidence accordingly.
4. Output STRICT JSON only (no markdown fences, no prose outside the object).

JSON schema you MUST return:
{{
  "bias": "LONG" | "SHORT" | "NEUTRAL",
  "confidence": <0-100 integer>,
  "summary": "<one punchy sentence, <=140 chars>",
  "reasoning": ["<bullet 1>", "<bullet 2>", "..."],   // 3-6 short bullets
  "key_levels": {{
    "entry": <number>,
    "stop_loss": <number>,
    "take_profit": <number>,
    "invalidation": <number>   // the price that proves the setup wrong
  }},
  "risks": ["<risk 1>", "<risk 2>"]   // 1-3 concrete risks to this trade
}}

Rules:
- Never invent prices outside the provided structure.
- confidence must be an integer 0-100.
- A setup that is discount-aligned AND (where relevant) inside a killzone should score high. \
A premium-misaligned trade should be down-scored honestly.
- Be honest: if the setup is weak or recent performance is against it, lower confidence.
- Output ONLY the JSON object."""


# Backward-compatible module-level prompt (defaults to gold context).
SYSTEM_PROMPT = system_prompt_for("XAU/USD")


def build_user_prompt(symbol: str, timeframe: str, setup_block: str, perf_block: str) -> str:
    return f"""\
Analyze this CRT setup on {symbol} ({timeframe} timeframe).

=== CURRENT SETUP ===
{setup_block}

=== RECENT STRATEGY PERFORMANCE ===
{perf_block}

Return the JSON object now."""
