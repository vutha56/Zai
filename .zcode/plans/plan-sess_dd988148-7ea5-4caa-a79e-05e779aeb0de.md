# Multi-Symbol (BTCUSD) + Backtest Engine

## Goal
1. **Add BTCUSD** alongside XAUUSD — scanner runs both symbols across all timeframes; dashboard lets you pick which to view.
2. **XAUUSD as capital.com commodity CFD** — already what Twelve Data's `XAU/USD` symbol returns (commodity exchange); this is a confirmation, not a code change. I'll document it.
3. **Backtest engine** — interactive `/backtest` page: pick symbol + timeframe + date range + params, run over historical candles, see equity curve + win rate + profit factor + max drawdown + trade list. Ephemeral (not persisted).

Perf tracking stays **global** (your choice). Backtest is **ephemeral** (your choice).

## Research basis
- **Twelve Data symbol format**: `BTC/USD` (crypto) and `XAU/USD` (commodity) both use the slashed BASE/QUOTE form — same as we already use. Same `/time_series` endpoint, same intervals. Adding BTC is config + multi-symbol plumbing, not a new provider. ([Twelve Data API docs](https://twelvedata.com/docs), [Commodity exchange](https://twelvedata.com/exchanges/COMMODITY), [Crypto exchange](https://twelvedata.com/exchanges/digital_currency))
- **Backtest methodology**: reuse the existing pure `detect_setups` on rolling historical windows; extract a pure `resolve_trade` from `outcomes._evaluate` so live and backtest share identical win/loss/R logic. Compute win rate, profit factor, max drawdown, R-distribution, equity curve. Self-contained (pandas/numpy we have) — no `backtesting.py`/`vectorbt` (their strategy interfaces don't match CRT detection). ([CRT strategy](https://tradingwyckoff.com/en/crt/), [walk-forward concept](https://blog.quantinsti.com/walk-forward-optimization-introduction/))

---

## Backend changes

### 1. Multi-symbol plumbing

**`config.py`**
- Add `symbols: str = "XAU/USD,BTC/USD"` (comma-separated, mirror of `scan_timeframes`).
- Add `symbols` property → `list[str]` (mirror of `timeframes`).
- Keep `symbol: str = "XAU/USD"` as the dashboard default view symbol.

**`strategy/scanner.py`** — add the outer symbol loop
- `run_scan(db, provider=None, fetch=True, timeframe=None, symbol=None)`:
  - If `symbol` passed → scan just that one.
  - Else loop `settings.symbols` × `settings.timeframes`, constructing `TwelveDataProvider(symbol=sym, interval=tf)` per pair.
  - Dedup key already includes symbol (DB unique index `uq_signal_key`).
- Fix the redundant double-provider-construction cosmetic bug noted by explore.

**`data/sync.py`** — `load_candles(db, limit, symbol, timeframe)`: already has both params; the default `"XAU/USD"` is fine. No change needed — callers just need to pass the symbol.

**`feedback/outcomes.py`** — fix the multi-TF/multi-symbol correctness bug
- `HOURS_PER_CANDLE = 4` hardcoded → derive lookforward from each signal's own timeframe via `bar_seconds(sig.timeframe)`.
- `load_candles(db, limit=400)` (defaults to XAU/USD 4h) → load candles per signal's `(symbol, timeframe)`.
- Perf stays global (your choice) — `rebuild_perf_summary` unchanged in scope.

### 2. Generalize LLM + Telegram to be symbol-aware (correctness)

**`ai/prompts.py`** — `SYSTEM_PROMPT` currently says "XAUUSD (gold) analyst". Refactor to a **symbol-conditional system prompt**:
- Keep one CRT/ICT methodology core.
- Add a short symbol-context preamble selected by symbol: gold → FX-session/killzone guidance; BTC → 24/7 market, note that FX killzones are weaker signals for crypto, higher volatility → wider stops.
- `build_user_prompt` already interpolates `{symbol}` and `{timeframe}` — no change there.

**`notify/telegram_bot.py`** — replace hardcoded `"XAUUSD · CRT 4H"` and `"XAUUSD CRT — Daily Summary"` with `signal.symbol` / dynamic timeframe. Trivial.

### 3. Backtest engine (new)

**`backtest/engine.py`** (new) — pure backtester
- Extract `resolve_trade(entry, sl, tp, is_long, future_candles) -> (result, hit_price, hit_ts, r_multiple)` as a **pure function** from `outcomes._evaluate` + `_r_multiple`. Both live outcomes and backtest call it → identical semantics.
- `run_backtest(candles: list[CandleDTO], params, lookforward_bars) -> BacktestResult`:
  - Slide a window; at each anchor `t` call `detect_setups(candles[max(0,t-window):t+1], timeframe=..., **params)`.
  - For each setup whose displacement candle == candle `t`, simulate the trade via `resolve_trade` against the next `lookforward_bars` candles.
  - Track equity (R-based, starting at 1.0 × initial_capital, 1R = risk amount), trade list, drawdown.
  - Optionally filter setups by confidence threshold / killzone / P/D (configurable).
- Metrics: total trades, win rate, profit factor (gross win R / gross loss R), avg R, max drawdown %, Sharpe-ish (mean R / std R), expectancy, equity curve points.

**`api/backtest.py`** (new router)
- `POST /backtest` (sync for typical runs) — body: `{symbol, timeframe, candles_limit, params, lookforward_bars, min_confidence}`. Loads candles from DB (must be synced first), runs engine, returns `BacktestResultOut`.
- `GET /backtest/symbols` + `/backtest/timeframes` — convenience for the form (reads from settings + DB).
- Register in `main.py`.

**`schemas.py`** — `BacktestResultOut`: metrics dict + equity curve `[{t, equity}]` + trades list (entry/exit/ts/dir/r). `CandleOut` gets a `symbol` field (currently missing — charts need it for multi-symbol).

### 4. API multi-symbol params
- `chart.get_candles(limit, timeframe, symbol)` — thread symbol to `load_candles`.
- `chart.get_quote(symbol)` — per-symbol cache (dict keyed by symbol).
- `signals.list_signals(status, timeframe, symbol, limit)` — add symbol filter.
- `control.health` — return `symbols` list (mirror `timeframes`).
- `control.trigger_scan(symbol?)` — optional symbol param.

---

## Frontend changes

### 1. Symbol selector
- `components/SubNav.jsx` — add a **symbol toggle** (XAU · BTC) next to the timeframe toggle. Props: `symbol`, `onSymbol`.
- `pages/Dashboard.jsx` — new `symbol` state; thread into `refreshAll` (api.candles/signals/quote). SSE handler shows "New signal on BTCUSD" hint when the symbol differs from the view.
- `api.js` — `candles(limit, timeframe, symbol)`, `signals(status, limit, timeframe, symbol)`, `quote(symbol)`, `scan(symbol?)`.

### 2. Backtest page (new route)
- `main.jsx` — add `<Route path="/backtest" element={<Backtest />} />`.
- `components/GlobalNav.jsx` — add an internal nav link "Backtest" (currently only has external link).
- `pages/Backtest.jsx` — form (symbol, timeframe, candle count, min confidence, optional param overrides) → "Run backtest" button → results: summary stat cards (win rate, profit factor, max DD, avg R, trades), equity curve, trade list table.
- `components/EquityChart.jsx` (new) — sibling of `Chart.jsx` using `addLineSeries` for the equity curve. ~50 lines, reuses the createChart lifecycle pattern.
- `api.js` — extend `post()` to accept a JSON body; add `backtest(config)`.

---

## Build / verify order
1. **Multi-symbol backend**: config + scanner loop + sync/outcomes fixes → verify scan produces BTC + XAU signals.
2. **Symbol-aware LLM/Telegram**: generalize prompts + telegram headers → re-analyze a BTC signal, confirm glm-5.2 doesn't say "gold".
3. **Backtest engine**: pure `resolve_trade` extraction + `run_backtest` → unit-test on the known synthetic bullish/bearish patterns (expect known win/loss).
4. **Backtest API**: `/backtest` endpoint → curl a real run on stored 4h XAU candles, confirm metrics sane.
5. **API multi-symbol params**: candles/signals/quote/health/scan.
6. **Frontend**: symbol toggle in SubNav + Backtest page + EquityChart + nav link.
7. **Headless smoke test**: dashboard renders with BTC selected; backtest page runs and shows equity curve; 0 console errors.

## Data / quota notes
- BTC needs candles synced: the first scan after deploy fetches BTC × 4 timeframes. Free-tier budget: 2 symbols × 4 TFs × 12 scans/hour (every 5 min) = 96 req/hour, ~2300/day — **exceeds the 800/day free limit.** I'll set the BTC scan cadence conservatively (scan BTC on 15m/1h/4h only, skip 5m, or scan every 10 min) and document the tradeoff. The quote cache already protects `/quote`.
- Backtest reads from DB candles (already synced by the scanner) — no extra API hits during a backtest run.

## Honest caveats
- **BTC ≠ gold behaviorally.** The ICT killzones (London/NY FX hours) are weaker signals for 24/7 crypto. The LLM prompt will note this, but expect BTC signals to be noisier until the feedback loop accumulates BTC-specific history.
- **Backtests on small samples mislead.** A backtest over 200 4h candles (~33 days) may show 5 trades — not statistically meaningful. I'll surface the sample size prominently and the README will caution against over-fitting to a single run.
- **Backtest is a model of the past, not the future.** It validates that the detection + trade-plan logic is internally consistent and shows historical R-distribution; it does not guarantee forward performance.

Sources: [Twelve Data API docs](https://twelvedata.com/docs), [Twelve Data Commodity exchange](https://twelvedata.com/exchanges/COMMODITY), [Twelve Data Crypto exchange](https://twelvedata.com/exchanges/digital_currency), [CRT strategy explained](https://tradingwyakoff.com/en/crt/), [Walk-forward optimization (QuantInsti)](https://blog.quantinsti.com/walk-forward-optimization-introduction/).