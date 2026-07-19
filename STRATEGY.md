# Strategy Guide — CRT + ICT Smart Money Dashboard

This is the **strategy companion** to the XAUUSD/BTCUSD signal app. It explains
what the dashboard detects, how to read the chart, and the concepts behind each
layer. For setup, install, and API reference, see the [main README](./README.md).

> ⚠️ **Educational tool, not financial advice.** Everything below describes a
> rules-based heuristic layered onto a discretionary framework (ICT/Smart Money
> + Candle Range Theory). It makes **no claim of profitability**. The LLM gives
> narrative, not prediction. Trading gold and crypto on margin carries
> substantial risk. **Never risk more than you can afford to lose.**

---

## 1. Overview

The dashboard fuses two related schools of price-action thought:

- **Candle Range Theory (CRT)** — every setup is a three-act play:
  *Range → Manipulation (sweep) → Distribution (displacement + Fair Value Gap)*.
  This is the core engine and the source of every Entry / SL / TP plan.
- **ICT / Smart Money Concepts (SMC)** — the institutional overlay: premium vs
  discount, killzones, daily bias, draw on liquidity, market structure, order
  blocks, breakers, volume profile.

Four institutional layers sit on top of the original CRT + SMC engine:

| Layer | Module | Adds |
|---|---|---|
| Daily Bias + Draw on Liquidity | `backend/app/strategy/bias.py` | Daily directional lean + next liquidity target |
| Market Structure | `backend/app/strategy/structure.py` | BOS / CHoCH / MSS / MSNR labels + trend state |
| Volume Profile | `backend/app/strategy/volumeprofile.py` | POC, Value Area, HVN/LVN |
| Power of 3 | `backend/app/strategy/bias.py` | Asian range → London Judas sweep → reclaim |

The CRT engine still generates the trade plan; the new layers **score, filter,
and annotate** it. **Philosophy:** institutions leave footprints (sweeps,
imbalances, displacement, volume nodes); the dashboard detects them mechanically
so you can review faster — interpretation remains yours.

---

## 2. How to read the chart

| Element | Visual | Meaning |
|---|---|---|
| **Candlestick** | Green (`#1a8f3a`) = close > open; red (`#c2364b`) = close < open | Standard OHLC |
| **Order Block (OB)** | Cyan rectangle = bullish OB; orange = bearish OB; `OB` label | Last opposite-color candle before a strong displacement — likely re-entry zone |
| **Breaker (BKR)** | Purple rectangle (both directions); `BKR` label | An OB that was violated and flipped polarity |
| **Fair Value Gap (FVG)** | Green/red shaded band; `FVG` label | 3-candle imbalance *with* the local trend — price may return to fill it |
| **Inverse FVG (iFVG)** | Same shading, slightly lighter; `iFVG` label | The same gap forming *against* the trend — a counter-trend fade zone |
| **Mitigated zones** | Any zone drawn very dim | A later candle already returned into the zone — no longer "fresh" |
| **Previous Day H/L** | Solid full-width green `PDH` / red `PDL` | Yesterday's UTC extremes — major liquidity magnets |
| **Today's H/L** | Lighter green/red full-width lines | Current UTC day's developing extremes |
| **Volume Profile** | Horizontal histogram on the right edge (~22% width) | Traded volume across price bins |
| — POC | Bright orange bar + solid orange `POC` line | Point of Control — bin with the most volume |
| — Value Area | Medium blue bars + solid blue `VAH`/`VAL` lines | The 70% Value Area (range holding 70% of volume) |
| — Outside VA | Dim grey bars | Low-acceptance prices; transition zones |
| **Bias badge** | Top-left pill: green = bullish, red = bearish, grey = neutral; `BULLISH · DOL <price> <conf>%` | Daily lean + Draw-on-Liquidity target + confidence |
| **BOS line** | Dashed purple `BOS ▲`/`▼` | Break of Structure — trend continuation |
| **CHoCH line** | Dashed orange `CHoCH ▲`/`▼` | Change of Character — first counter-trend break (early reversal hint) |
| **MSS line** | Dashed red `MSS ▲`/`▼` | Market Structure Shift — CHoCH *with* displacement (higher conviction) |
| **MSNR flag** | Trailing `*` (e.g. `CHoCH*`) | Break rejected by the MSNR filter — likely fake |
| **PO3 Asian range** | Rectangle 00:00–07:00 UTC; green/red/grey tint | Asian accumulation range London is expected to sweep |
| **Entry / SL / TP** | Dashed blue / red / green lines | Active signal's trade plan |

> The backend also returns High/Low Volume Nodes (see §3.6), but the histogram
> is coloured by Value-Area membership (orange/blue/grey), not node type. You
> can still spot HVNs as the tallest bars and LVNs as the troughs.

---

## 3. Strategy concepts

### 3.1 CRT (Candle Range Theory) — the core

A CRT setup is *Range → Manipulation (sweep) → Distribution (displacement +
FVG)*. The engine slides a `CRT_RANGE_WINDOW`-candle window (default 6) and
checks the next three candles:

1. **Range** — high/low of the window. Liquidity rests above the high and below
   the low.
2. **Sweep** — next candle pokes beyond a range extreme but closes back inside.
   Poke below low + close back in → **LONG**; above high + close back in →
   **SHORT**.
3. **Displacement** — the following candle's body is ≥ `CRT_DISPLACEMENT_K ×
   ATR` (default 1.0), in the reversal direction.
4. **FVG** — the sweep wick and confirm wick don't overlap, leaving a 3-candle
   gap.

**Trade plan:** Entry at the FVG midpoint; SL just beyond the sweep wick (+ `CRT_SL_BUFFER_ATR × ATR`, default 0.15); TP at the opposite range liquidity,
floored to `CRT_MIN_RR` (default 2.0R). Confidence is a 0–100 heuristic blending
displacement strength, FVG size vs ATR, sweep depth, and R:R. **CRT is the only
layer that emits an actual entry/SL/TP.**

### 3.2 Premium / Discount

Split the CRT range at its midpoint (**equilibrium**). Upper half = **premium**
(expensive, institutions sell); lower half = **discount** (cheap, institutions
buy). A LONG whose entry is below equilibrium (or SHORT above it) is aligned;
misaligned entries take a `CRT_PD_PENALTY` hit (default –20), or are dropped
entirely when `CRT_PD_STRICT=true`. **Use:** longs from discount and shorts from
premium have a structural edge; a high-confidence LONG in premium is fighting
gravity.

### 3.3 Killzones

Intraday UTC windows of concentrated institutional flow (ICT "Silver Bullet"):

| Killzone | UTC | What happens |
|---|---|---|
| **London** | 07:00–10:00 | Open sweeps Asian liquidity, sets day direction |
| **New York AM** | 14:00–17:00 | NY cash open — strongest US displacement |
| **New York PM** | 18:00–21:00 | London close — reversals and profit-taking |

A setup whose displacement candle is inside a killzone gets `CRT_KILLZONE_BONUS`
(+15 default); outside any killzone takes `CRT_KILLZONE_OFF_PENALTY` (–8). Asia
(00:00–07:00) is excluded for gold. Killzones identify *when* institutions act,
not *whether* your setup works.

### 3.4 Daily Bias + Draw on Liquidity (DOL)

A single daily directional lean plus the next magnetic price target. **Rule Set
A (close-based):** using the last *closed* daily candle vs the prior day's
range —

- Close **above prior day high** → **bullish**.
- Close **below prior day low** → **bearish**.
- Close **inside the prior range** → **neutral**.

Confidence starts at 40 and rises with how far beyond the range price closed
(capped 80). Two amplifiers add +10 each: (a) bias agrees with the 4h trend
(up/down candle count over the last 20 H4 candles), (b) the bias formed inside a
killzone. **DOL** = nearest *unswept* swing high (bullish) or low (bearish)
beyond current price.

**Use:** bias is a **gate**. A LONG CRT setup is far more trustworthy when
daily bias is bullish and the DOL sits above entry. Counter-bias trades should
be down-scored in your head regardless of the CRT confidence number.

### 3.5 Market Structure — BOS / CHoCH / MSS / MSNR

- **Swing** — a fractal pivot: a candle whose high (or low) is the strict
  extreme of the surrounding `swing_length=2` candles each side (5-candle
  window).
- **BOS (Break of Structure)** — close beyond the last *same-direction* swing =
  **continuation**.
- **CHoCH (Change of Character)** — close beyond the last *counter-trend* swing
  = first reversal hint.
- **MSS (Market Structure Shift)** — a CHoCH *with displacement*: body ≥ 1.5 ×
  ATR **and** body ratio ≥ 0.6, **or** the break leaves an FVG. The
  higher-conviction reversal.
- **MSNR (Market Structure No Run)** — rejection filter flagging a break as
  likely fake if **any** hold: (a) no prior sweep within 3 bars, (b) weak close
  (< 0.2 × ATR beyond the swing), (c) closes back inside within 2 bars.

**Reading labels:** `BOS` confirms the trend; `CHoCH` is a heads-up that
momentum may be turning; `MSS` is the version of CHoCH you should actually act
on. A trailing `*` means MSNR-rejected — treat as suspect. Only MSS and BOS
update the prevailing trend; plain non-displaced CHoCH does not.

### 3.6 Volume Profile — POC / VAH / VAL / HVN / LVN

A horizontal histogram of traded volume per price level. Each candle's volume is
distributed uniformly across its `[low, high]` range, then bucketed (1.0
quote-unit bins for XAU/USD, 50.0 for BTC/USD, else 0.1% of median; capped at
100 bins).

- **POC (Point of Control)** — bin with the most volume. A magnet price revisits.
- **Value Area (VA)** — contiguous range holding **70%** of total volume, via the
  classic expand-from-POC algorithm. **VAH / VAL** are its top and bottom.
- **HVN (High Volume Node)** — local maximum of the smoothed histogram; a level
  where the market dwelled. **Pause / acceptance zones.**
- **LVN (Low Volume Node)** — local minimum; price slices through these quickly.
  **Fast-transition zones.**

**Use:** POC is a magnet in ranges; HVNs digest moves, LVNs accelerate them. A
CRT entry on an HVN with DOL beyond an LVN is cleaner than one mid-nowhere. If
the provider reports no volume, the engine falls back to a tick-count proxy.

### 3.7 Power of 3 (Asian range → London)

ICT's daily cycle (Accumulation → Manipulation → Distribution) on sessions. On
the most recent UTC day with both sessions:

1. **Asia (00:00–07:00 UTC)** sets the accumulation range.
2. **London (07:00–10:00 UTC)** performs the "Judas sweep" beyond the Asian
   range.
3. **Reclaim** is the directional signal: London wicked below Asian low **and
   closed back above** → **bullish PO3**; wicked above Asian high **and closed
   back below** → **bearish PO3**.

If the Asian range exceeds `CRT_PO3_MAX_RANGE_PCT` (default 1.0% of Asian low),
the day is treated as a trend day and PO3 is skipped. **Use:** a bullish PO3
reclaim reinforces a bullish daily bias; a PO3 that conflicts with the CRT
setup's direction is a red flag.

### 3.8 FVG / iFVG / Order Blocks / Breakers — the SMC levels

The structural levels drawn on the chart (visuals in §2):

- **FVG** — a 3-candle imbalance *with* the 20-bar EMA slope. Price is expected
  to return and fill it before continuing.
- **iFVG** — same gap geometry but *against* the EMA slope. A counter-trend fade
  zone.
- **Order Block** — last opposite-color candle before a strong displacement
  (body ≥ `displacement_k × ATR`). The institutional re-entry footprint.
- **Breaker** — an OB later violated by a strong opposite displacement, flipping
  its polarity.

All four are flagged `mitigated` once a later candle returns into their price
band — mitigated zones are weaker re-entry references than fresh ones.

---

## 4. The daily improvement loop

Every CRT signal is **resolved** after its look-forward window expires. The
window is derived per signal from its own timeframe (`bar_seconds`), so a
15-minute signal is judged against 15-minute candles, not a global 4h assumption.
For each matured signal, the engine walks candles after entry:

- **WIN** — TP touched before SL.
- **LOSS** — SL touched before TP (a same-candle ambiguous hit is conservatively
  a loss).
- **EXPIRED** — neither hit within the window.

A daily job aggregates outcomes into a **performance summary**: win rate over
the last 20 and last 50 setups, average R, and breakdowns by session and
direction. A short narrative ("LONG setups outperform 58% vs SHORT 41%; best
session London") is injected into every subsequent AI analysis.

The AI analysis is produced by **ZAI GLM (`glm-5.2`)** with a **symbol-aware
system prompt**: gold gets killzone emphasis and tight stops; BTC gets weaker
killzones, wider stops, and discounted weekend moves. The model returns strict
JSON (bias, confidence, summary, reasoning, key levels, risks). As history
grows, the write-ups adapt to what's actually working — this is the "improve
every day" loop.

---

## 5. Backtesting

The **/backtest** page replays historical candles through the *exact same* CRT
detection + trade resolver as the live system — backtest and live win/loss/R
semantics are identical.

**Inputs:** symbol, timeframe, candle count (50–5000, default 500),
look-forward bars (default 8), min-confidence filter, starting capital,
risk-per-trade %, and optional overrides (range window, displacement k, min
RR). Position sizing is risk-based and compounded: each trade risks a fixed % of
*current* equity, so R-multiples map to real P&L.

**Metrics:**

| Metric | Meaning |
|---|---|
| **Trades** | Total, split W / L / expired |
| **Win rate** | Wins ÷ decided (expired excluded) |
| **Avg R** | Mean R-multiple across all trades |
| **Profit factor** | Gross win R ÷ gross loss R (>1 = profitable on this sample) |
| **Max drawdown** | Peak-to-trough equity drop, % |
| **Return** | Total equity change, % |
| **Sharpe (R)** | Mean R ÷ std of R, per-trade (not annualized) |
| **Expectancy** | Same as Avg R here |
| **Final equity** | Ending account value |

An equity curve and per-trade table (P/D, killzone, bars-to-resolve) accompany
the metrics. **Caveat:** backtests under ~30 trades are **not statistically
meaningful** — a 100% win rate over 8 trades tells you almost nothing, and
over-fitting to one lucky run is easy. Backtests validate internal consistency;
they do **not** predict future returns.

---

## 6. Tuning parameters

All knobs are env vars (see `backend/.env.example`); defaults from
`backend/app/config.py`.

| Variable | Default | What it does |
|---|---|---|
| `SYMBOL` | `XAU/USD` | Default dashboard symbol |
| `TIMEFRAME` | `5min` | Default dashboard timeframe |
| `SYMBOLS` | `XAU/USD,BTC/USD` | Symbols scanned each cycle |
| `SCAN_TIMEFRAMES` | `5min,15min,1h,4h` | Timeframes scanned each cycle |
| `SCAN_CRON_MINUTES` | `*/5` | Scheduler minute field |
| `CRT_RANGE_WINDOW` | `6` | Candles forming the consolidation range |
| `CRT_DISPLACEMENT_K` | `1.0` | Displacement body ≥ k × ATR |
| `CRT_ATR_PERIOD` | `14` | ATR lookback |
| `CRT_SL_BUFFER_ATR` | `0.15` | SL buffer beyond sweep wick, in ATR |
| `CRT_MIN_RR` | `2.0` | Min reward:risk floor for TP |
| `CRT_LOOKFORWARD_CANDLES` | `3` | Candles to wait for TP/SL before expiring |
| `CRT_SCAN_LOOKBACK` | `30` | Candles re-scanned each cycle |
| `CRT_PD_PENALTY` | `20.0` | Confidence penalty for misaligned P/D |
| `CRT_PD_STRICT` | `false` | If true, drop P/D-failing setups entirely |
| `CRT_KILLZONE_BONUS` | `15.0` | Confidence bonus inside a killzone |
| `CRT_KILLZONE_OFF_PENALTY` | `8.0` | Penalty when outside any killzone |
| `CRT_PO3_MAX_RANGE_PCT` | `1.0` | Skip PO3 if Asian range exceeds this % (trend-day filter) |
| `CRT_TF_OVERRIDES` | JSON (below) | Per-timeframe range window + displacement k |
| `ZAI_MODEL` | `glm-5.2` | ZAI GLM model for AI analysis |

**Per-timeframe overrides** — lower timeframes get more candles/day, so they're
tuned stricter to avoid over-sensitivity:

```json
{"5min":{"range_window":8,"displacement_k":1.2},
 "15min":{"range_window":7,"displacement_k":1.1},
 "1h":{"range_window":6,"displacement_k":1.0},
 "4h":{"range_window":6,"displacement_k":1.0}}
```

---

## 7. Multi-symbol + multi-timeframe notes

**XAU/USD (gold)** — a commodity CFD with concentrated London/NY liquidity.
Killzones are the cleanest displacement windows and get up-scored; the thin
Asian session is excluded. Gold is fast, so stops are tight relative to ATR.

**BTC/USD (Bitcoin)** — 24/7 with no centralized session structure. FX-style
killzones are a **mild** positive at best. BTC's wicks are large in % terms, so
stops get swept more often — favour wider stops and clearer displacement.
Weekend moves are low-volume and unreliable; the AI prompt explicitly discounts
them. VP bin size is 50 quote units (vs 1.0 for gold).

**Timeframes.**

- **5m / 15m** — more candles/day → more signals → more noise. The engine
  compensates with stricter per-timeframe overrides. Best for active scalpers;
  worst for signal quality.
- **1h / 4h** — fewer, cleaner setups at default params. The original CRT design
  targets the 4h; this is where the strategy is most internally consistent.

---

## 8. Honest limitations

Read this before trusting any signal.

- **No strategy is profitable by definition.** CRT and ICT are discretionary
  frameworks; this is a rules-based approximation. A high confidence score
  reflects pattern quality, not whether the trade will win.
- **The LLM gives narrative, not prediction.** GLM (`glm-5.2`) can be wrong,
  hedged, or invent levels. Treat it as a second opinion, not an oracle.
- **Small samples mislead.** Win rates under ~30 resolved setups are noise; the
  feedback loop and backtest both need substantial history.
- **Lower timeframes are noisier.** 5m signals may backtest well on a lucky
  window and get stopped out more often live.
- **The feedback loop needs weeks of data.** Early deployments should be
  paper-traded.
- **Backtest ≠ future.** Markets regime-shift; what worked last quarter may stop
  working.
- **Killzones and bias are heuristics, not laws.** A bullish bias can fail any
  day.
- **Data quality matters.** Volume profile degrades to a tick-count proxy when
  no volume is reported; free-tier rate limits can leave gaps.

---

## Sources / further reading

- [Inner Circle Trader (ICT) — YouTube](https://www.youtube.com/@InnerCircleTrader)
- [LuxAlgo — Smart Money Concepts overview](https://www.luxalgo.com/blog/smart-money-concepts-smc-explained/)
- [LuxAlgo — Fair Value Gap (FVG) explained](https://www.luxalgo.com/blog/fair-value-gap-fvg-explained/)
- [TradingView — Volume Profile docs (POC/VA terminology)](https://www.tradingview.com/support/solutions/43000595080-volume-profile/)
- [Investopedia — Fair Value Gap](https://www.investopedia.com/terms/f/fair-value-gap.asp)
- Project README — [./README.md](./README.md) (setup, API, architecture)
