"""Agent3 review backtest: measure the filtering impact of each new SMC layer
(Daily Bias, Volume Profile, MSS confirmation, Power of 3) on the CRT baseline.

Run from the backend dir:
    python -m app.review_backtest
or
    python review_backtest.py

Prints a baseline row + one row per filter, plus bucket splits (HVN vs LVN,
MSS-confirmed vs unconfirmed). Small-sample numbers — read with skepticism.
"""
from __future__ import annotations

import sys
from pathlib import Path

# Make `app.*` importable when run as a plain script from the backend dir.
sys.path.insert(0, str(Path(__file__).resolve().parent))

from app.data.sync import load_candles
from app.db import SessionLocal
from app.backtest.engine import run_backtest
from app.strategy.bias import compute_daily_bias, detect_power_of_3, to_daily
from app.strategy.crt import atr
from app.strategy.scanner import candles_to_dto
from app.strategy.structure import market_structure
from app.strategy.volumeprofile import compute_volume_profile


SYMBOL = "XAU/USD"
TIMEFRAME = "4h"
LIMIT = 500  # we only have ~208 4h candles; load_candles caps at what's stored
LOOKFORWARD = 12


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def win_rate(trades):
    decided = [t for t in trades if t.result in ("win", "loss")]
    if not decided:
        return 0.0, 0
    wins = sum(1 for t in decided if t.result == "win")
    return 100.0 * wins / len(decided), len(decided)


def avg_r(trades):
    if not trades:
        return 0.0
    return sum(t.r_multiple for t in trades) / len(trades)


def fmt_row(label, trades, baseline=None):
    wr, decided = win_rate(trades)
    ar = avg_r(trades)
    n = len(trades)
    line = f"  {label:<28} trades={n:<4} decided={decided:<4} win_rate={wr:5.1f}%  avg_r={ar:+.3f}"
    if baseline is not None and decided:
        b_wr = baseline["win_rate"]
        b_ar = baseline["avg_r"]
        line += f"   delta_wr={wr - b_wr:+5.1f}pp  delta_r={ar - b_ar:+.3f}"
    return line


# ---------------------------------------------------------------------------
# Filters
# ---------------------------------------------------------------------------

def bias_for_trade(trade, candles_up_to):
    """Daily bias at trade time, computed only from candles strictly BEFORE the trade."""
    prior = [c for c in candles_up_to if c.ts < trade.candle_ts]
    if len(prior) < 20:
        return "neutral"
    daily = to_daily(prior)
    if len(daily) < 3:
        return "neutral"
    return compute_daily_bias(daily).get("bias", "neutral")


def passes_bias_filter(trade, bias):
    if bias == "neutral":
        return True
    if bias == "bullish" and trade.direction == "LONG":
        return True
    if bias == "bearish" and trade.direction == "SHORT":
        return True
    return False


def vp_for_trade(trade, candles_up_to):
    """Volume profile over the candles strictly before the trade."""
    prior = [c for c in candles_up_to if c.ts < trade.candle_ts]
    if len(prior) < 20:
        return None
    return compute_volume_profile(prior, symbol=SYMBOL)


def vp_bucket(trade, vp, atr_val):
    """Bucket the trade by where its entry sits vs the volume profile.

    'poc'      -> within 0.3*ATR of the POC
    'in_va'    -> inside VAL..VAH (but not at POC)
    'lvn'      -> strictly outside the value area
    """
    if not vp or vp.get("poc") is None or vp.get("vah") is None or vp.get("val") is None:
        return "unknown"
    e = trade.entry
    if abs(e - vp["poc"]) <= 0.3 * atr_val:
        return "poc"
    if vp["val"] <= e <= vp["vah"]:
        return "in_va"
    return "lvn"


def mss_confirmed(trade, candles_up_to, lookback=50):
    """True if a same-direction MSS fires on the candles leading into the trade.

    `lookback` = number of candles of structure context. MSS requires a confirmed
    prior trend reversal, so a tiny window (20) produces zero hits — we use 50,
    which is enough for a fractal swing_length=2 to confirm and a CHoCH->MSS to
    fire (validated separately on this dataset).
    """
    prior = [c for c in candles_up_to if c.ts < trade.candle_ts]
    if len(prior) < lookback:
        return False
    window = prior[-lookback:]
    ms = market_structure(window)
    mss = ms.get("last_mss")
    if not mss:
        return False
    want_dir = "bullish" if trade.direction == "LONG" else "bearish"
    return mss.get("direction") == want_dir


def po3_for_day(trade, candles_up_to):
    """PO3 signal for the trade's UTC day, computed only from candles before the trade."""
    prior = [c for c in candles_up_to if c.ts < trade.candle_ts]
    if len(prior) < 20:
        return None
    # detect_power_of_3 picks the most-recent day with both Asia + London sessions.
    po3 = detect_power_of_3(prior, timeframe=TIMEFRAME)
    return po3.get("po3_signal")


def passes_po3_filter(trade, po3_sig):
    if po3_sig is None:
        return True  # treat unknown as no-filter
    if po3_sig == "long" and trade.direction == "LONG":
        return True
    if po3_sig == "short" and trade.direction == "SHORT":
        return True
    return False


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    db = SessionLocal()
    try:
        rows = load_candles(db, limit=LIMIT, symbol=SYMBOL, timeframe=TIMEFRAME)
    finally:
        db.close()

    n = len(rows)
    print(f"\n=== AGENT3 REVIEW BACKTEST ===")
    print(f"symbol={SYMBOL}  timeframe={TIMEFRAME}  candles_available={n}  lookforward_bars={LOOKFORWARD}")
    if n < 50:
        print("Not enough candles — abort.")
        return
    if n < LIMIT:
        print(f"(requested {LIMIT} but only {n} stored — using what we have)")

    candles = candles_to_dto(rows)

    # --- BASELINE ---
    res = run_backtest(
        candles, timeframe=TIMEFRAME, symbol=SYMBOL, lookforward_bars=LOOKFORWARD
    )
    baseline_trades = res.trades
    baseline = {
        "win_rate": win_rate(baseline_trades)[0],
        "avg_r": avg_r(baseline_trades),
        "n": len(baseline_trades),
    }

    print("\n--- BASELINE (CRT, no SMC filters) ---")
    print(f"  metrics = {res.metrics}")
    print(fmt_row("baseline", baseline_trades))

    # --- (b) Daily Bias filter ---
    bias_kept, bias_dropped = [], []
    for t in baseline_trades:
        b = bias_for_trade(t, candles)
        if passes_bias_filter(t, b):
            bias_kept.append(t)
        else:
            bias_dropped.append(t)
    print("\n--- (b) DAILY BIAS FILTER (keep trade only if direction matches bias) ---")
    print(fmt_row("bias_kept", bias_kept, baseline))
    print(fmt_row("bias_dropped", bias_dropped, baseline))

    # --- (c) Volume Profile buckets ---
    atrs = atr(candles, period=14)
    # build a ts -> atr lookup (nearest prior)
    ts_atr = {c.ts: a for c, a in zip(candles, atrs)}

    def atr_at(t):
        # nearest-prior atr
        prior_a = 0.0
        for c in candles:
            if c.ts <= t.candle_ts:
                prior_a = ts_atr.get(c.ts, prior_a)
            else:
                break
        return prior_a or 1.0

    poc_trades, va_trades, lvn_trades, vp_unknown = [], [], [], []
    vp_kept, vp_dropped = [], []
    for t in baseline_trades:
        vp = vp_for_trade(t, candles)
        a = atr_at(t)
        bucket = vp_bucket(t, vp, a)
        {"poc": poc_trades, "in_va": va_trades, "lvn": lvn_trades}.get(bucket, vp_unknown).append(t)
        # "edge" filter: keep trades at POC or in VA (high liquidity), drop LVN
        if bucket in ("poc", "in_va"):
            vp_kept.append(t)
        elif bucket == "lvn":
            vp_dropped.append(t)
        else:
            vp_kept.append(t)  # unknown -> keep

    print("\n--- (c) VOLUME PROFILE BUCKETS ---")
    print(fmt_row("at_poc", poc_trades, baseline))
    print(fmt_row("in_value_area", va_trades, baseline))
    print(fmt_row("at_lvn (outside VA)", lvn_trades, baseline))
    print(fmt_row("vp_unknown", vp_unknown, baseline))
    print(fmt_row("vp_kept (POC+VA)", vp_kept, baseline))
    print(fmt_row("vp_dropped (LVN)", vp_dropped, baseline))

    # --- (d) MSS confirmation ---
    mss_yes, mss_no = [], []
    for t in baseline_trades:
        if mss_confirmed(t, candles):
            mss_yes.append(t)
        else:
            mss_no.append(t)
    print("\n--- (d) MSS CONFIRMATION ---")
    print(fmt_row("mss_confirmed", mss_yes, baseline))
    print(fmt_row("mss_unconfirmed", mss_no, baseline))
    print(fmt_row("mss_filter (kept=confirmed)", mss_yes, baseline))

    # --- (e) PO3 filter ---
    po3_kept, po3_dropped, po3_match, po3_mismatch, po3_unknown = [], [], [], [], []
    for t in baseline_trades:
        sig = po3_for_day(t, candles)
        if sig is None:
            po3_unknown.append(t)
            po3_kept.append(t)  # unknown -> keep (no filter)
            continue
        if passes_po3_filter(t, sig):
            po3_match.append(t)
            po3_kept.append(t)
        else:
            po3_mismatch.append(t)
            po3_dropped.append(t)
    print("\n--- (e) POWER OF 3 FILTER ---")
    print(fmt_row("po3_match (same-dir)", po3_match, baseline))
    print(fmt_row("po3_mismatch", po3_mismatch, baseline))
    print(fmt_row("po3_unknown (no signal)", po3_unknown, baseline))
    print(fmt_row("po3_kept (match+unknown)", po3_kept, baseline))
    print(fmt_row("po3_dropped (mismatch)", po3_dropped, baseline))

    # --- Summary table ---
    print("\n=== SUMMARY: each layer as a hard filter vs baseline ===")
    print(f"  {'layer':<28} {'kept':<6} {'drop':<6} {'wr_kept':>8} {'delta_wr':>9} {'avg_r_kept':>11} {'delta_r':>9}")
    def summary_row(label, kept, dropped):
        wr_k = win_rate(kept)[0]
        ar_k = avg_r(kept)
        print(f"  {label:<28} {len(kept):<6} {len(dropped):<6} {wr_k:>7.1f}% {wr_k - baseline['win_rate']:>+8.1f}pp {ar_k:>+11.3f} {ar_k - baseline['avg_r']:>+9.3f}")
    summary_row("baseline (no filter)", baseline_trades, [])
    summary_row("Daily Bias", bias_kept, bias_dropped)
    summary_row("VP (drop LVN)", vp_kept, vp_dropped)
    summary_row("MSS confirmed only", mss_yes, mss_no)
    summary_row("PO3 (drop mismatch)", po3_kept, po3_dropped)
    print()
    print(f"baseline win_rate = {baseline['win_rate']:.1f}%   baseline avg_r = {baseline['avg_r']:+.3f}")
    print(f"baseline n_trades = {baseline['n']}  (SMALL SAMPLE — read deltas with caution)")


if __name__ == "__main__":
    main()
