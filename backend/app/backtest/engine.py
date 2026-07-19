"""Pure backtest engine for the CRT strategy.

Reuses the existing pure `detect_setups` on rolling historical windows and a
shared `resolve_trade` helper (extracted from the live outcome resolver) so the
backtest and the live system have IDENTICAL win/loss/R semantics.

No DB / no I/O — takes candle DTOs, returns a result dataclass. The API layer
loads candles from the DB and passes them in.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Literal

from ..data.twelvedata import CandleDTO
from ..strategy.crt import CRTSetup, bar_seconds, detect_setups


# ---------------------------------------------------------------------------
# Shared trade resolver (single source of truth for win/loss/R)
# ---------------------------------------------------------------------------

def resolve_trade(
    entry: float,
    sl: float,
    tp: float,
    is_long: bool,
    future: list,
    risk_hint: float | None = None,
) -> tuple[str, float, datetime | None, float]:
    """Resolve a single trade against future candles.

    Returns (result, hit_price, hit_ts, r_multiple).
    `result` is one of "win" | "loss" | "expired".
    Same-candle ambiguous hit -> conservatively a loss.

    `future` items only need .high/.low/.ts (works with CandleDTO or ORM Candle).
    `risk_hint` = |entry - sl|; if None it's computed from entry/sl.
    """
    if not future:
        return "expired", 0.0, None, 0.0
    risk = risk_hint if risk_hint is not None else abs(entry - sl) or 1e-9
    for c in future:
        hit_tp = c.high >= tp if is_long else c.low <= tp
        hit_sl = c.low <= sl if is_long else c.high >= sl
        if hit_tp and hit_sl:
            result, hit_price = "loss", sl  # ambiguous -> conservative loss
        elif hit_tp:
            result, hit_price = "win", tp
        elif hit_sl:
            result, hit_price = "loss", sl
        else:
            continue
        r = abs(tp - entry) / risk if result == "win" else (-1.0 if result == "loss" else 0.0)
        return result, hit_price, getattr(c, "ts", None), r
    return "expired", 0.0, None, 0.0


# ---------------------------------------------------------------------------
# Backtest
# ---------------------------------------------------------------------------

@dataclass
class BacktestTrade:
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
    hit_ts: datetime | None
    bars_to_resolve: int


@dataclass
class BacktestResult:
    symbol: str
    timeframe: str
    trades: list[BacktestTrade] = field(default_factory=list)
    equity_curve: list[dict] = field(default_factory=list)
    metrics: dict = field(default_factory=dict)


def run_backtest(
    candles: list[CandleDTO],
    timeframe: str,
    symbol: str = "",
    range_window: int | None = None,
    displacement_k: float | None = None,
    atr_period: int | None = None,
    sl_buffer_atr: float | None = None,
    min_rr: float | None = None,
    tf_overrides: dict | None = None,
    lookforward_bars: int = 8,
    window_size: int | None = None,
    min_confidence: float = 0.0,
    initial_capital: float = 10000.0,
    risk_per_trade_pct: float = 1.0,
) -> BacktestResult:
    """Run the CRT strategy over historical candles.

    Strategy: at each candle `t`, detect setups on the window ending at `t`.
    A setup is "tradeable" at `t` if its displacement candle == candle `t`
    (i.e. the pattern just completed). We then resolve the trade against the
    next `lookforward_bars` candles.

    Equity is tracked in account-currency terms: each trade risks
    `risk_per_trade_pct` of current equity, so R-multiples map to real P&L
    and drawdown is meaningful.
    """
    n = len(candles)
    # minimum candles to form one pattern: range_window + sweep + displacement + confirm
    rw = range_window or 6
    min_window = rw + 4
    if n < min_window:
        return BacktestResult(symbol=symbol, timeframe=timeframe)

    # window caps how far back detect_setups looks at each anchor. Larger = more
    # range context but slower; must be >= min_window.
    win = max(min_window, window_size or (rw + 12))

    trades: list[BacktestTrade] = []
    seen_keys: set[tuple] = set()  # (candle_ts, direction) dedup within a run

    # start at the first candle where a full pattern can complete
    for t in range(min_window - 1, n):
        window = candles[max(0, t - win + 1): t + 1]
        setups = detect_setups(
            window,
            timeframe=timeframe,
            range_window=range_window,
            displacement_k=displacement_k,
            atr_period=atr_period,
            sl_buffer_atr=sl_buffer_atr,
            min_rr=min_rr,
            tf_overrides=tf_overrides,
        )
        # only act on setups whose CONFIRM candle is the LAST candle of the window.
        # (The pattern is [range][sweep][displacement][confirm]; the trade triggers
        # once the confirm candle closes and the FVG is confirmed.)
        future_candles = candles[t + 1: t + 1 + lookforward_bars]
        for s in setups:
            if s.displacement_idx + 1 != len(window) - 1:
                continue  # not anchored at candle t
            if s.confidence < min_confidence:
                continue
            key = (s.candle_ts, s.direction)
            if key in seen_keys:
                continue
            seen_keys.add(key)

            is_long = s.direction == "LONG"
            result, hit_price, hit_ts, r = resolve_trade(
                entry=s.entry, sl=s.sl, tp=s.tp, is_long=is_long,
                future=future_candles, risk_hint=abs(s.entry - s.sl) or 1e-9,
            )
            bars = 0
            for i, c in enumerate(future_candles, start=1):
                if hit_ts is not None and c.ts >= hit_ts:
                    bars = i
                    break
            trades.append(BacktestTrade(
                candle_ts=s.candle_ts,
                direction=s.direction,
                entry=s.entry, sl=s.sl, tp=s.tp,
                confidence=s.confidence,
                premium_discount=s.premium_discount,
                killzone=s.killzone,
                result=result,
                r_multiple=round(r, 3),
                hit_ts=hit_ts,
                bars_to_resolve=bars,
            ))

    # sort trades chronologically for the equity curve
    trades.sort(key=lambda x: x.candle_ts)

    # --- equity curve (compounded, risk-based position sizing) ---
    equity = initial_capital
    peak = equity
    max_dd = 0.0
    curve: list[dict] = [{"t": candles[0].ts.isoformat() if candles else "", "equity": round(equity, 2)}]
    rs = []
    for tr in trades:
        risk_amount = equity * (risk_per_trade_pct / 100.0)
        pnl = tr.r_multiple * risk_amount
        equity += pnl
        peak = max(peak, equity)
        dd = (peak - equity) / peak if peak > 0 else 0.0
        max_dd = max(max_dd, dd)
        rs.append(tr.r_multiple)
        curve.append({
            "t": (tr.hit_ts or tr.candle_ts).isoformat(),
            "equity": round(equity, 2),
            "r": tr.r_multiple,
        })

    metrics = _compute_metrics(trades, rs, equity, initial_capital, max_dd)
    return BacktestResult(
        symbol=symbol, timeframe=timeframe,
        trades=trades, equity_curve=curve, metrics=metrics,
    )


def _compute_metrics(
    trades: list[BacktestTrade], rs: list[float],
    final_equity: float, initial_capital: float, max_dd: float,
) -> dict:
    n = len(trades)
    if n == 0:
        return {
            "trades": 0, "win_rate": 0.0, "avg_r": 0.0, "profit_factor": 0.0,
            "max_drawdown_pct": 0.0, "expectancy_r": 0.0, "sharpe_r": 0.0,
            "final_equity": round(final_equity, 2), "return_pct": 0.0,
        }
    wins = [t for t in trades if t.result == "win"]
    losses = [t for t in trades if t.result == "loss"]
    expired = [t for t in trades if t.result == "expired"]
    decided = wins + losses
    win_rate = (len(wins) / len(decided) * 100.0) if decided else 0.0
    gross_win = sum(t.r_multiple for t in wins)
    gross_loss = abs(sum(t.r_multiple for t in losses))
    profit_factor = (gross_win / gross_loss) if gross_loss > 0 else (float("inf") if gross_win > 0 else 0.0)
    avg_r = sum(rs) / len(rs) if rs else 0.0
    # sharpe-ish: mean R / std R (per-trade, not annualized)
    if len(rs) > 1:
        mean_r = sum(rs) / len(rs)
        var = sum((r - mean_r) ** 2 for r in rs) / (len(rs) - 1)
        std_r = var ** 0.5
        sharpe_r = (mean_r / std_r) if std_r > 0 else 0.0
    else:
        sharpe_r = 0.0
    return_pct = ((final_equity - initial_capital) / initial_capital) * 100.0
    return {
        "trades": n,
        "wins": len(wins),
        "losses": len(losses),
        "expired": len(expired),
        "win_rate": round(win_rate, 1),
        "avg_r": round(avg_r, 3),
        "profit_factor": round(profit_factor, 2) if profit_factor != float("inf") else None,
        "max_drawdown_pct": round(max_dd * 100.0, 2),
        "expectancy_r": round(avg_r, 3),
        "sharpe_r": round(sharpe_r, 3),
        "final_equity": round(final_equity, 2),
        "return_pct": round(return_pct, 2),
    }
