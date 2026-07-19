# XAUUSD CRT-4H Trading Signal App

A locally-run web app that detects **Candle Range Theory (CRT)** setups on
**XAUUSD (gold) 4-hour candles**, generates **AI textual analysis** via the
**ZAI GLM** model, **stores every signal and its outcome** to learn from, and
pushes **signal alerts** to an Apple-style web dashboard **and Telegram**.

> ⚠️ **Educational tool, not financial advice.** CRT detection is a rules-based
> heuristic and the LLM provides narrative, not a predictive edge. Trading
> XAUUSD carries substantial risk and signals may lose money. See the
> [Disclaimer](#disclaimer) below.

---

## Features

- **Real XAUUSD 4h data** from Twelve Data (pluggable provider interface).
- **CRT detection engine** — Range → Manipulation (sweep) → Distribution
  (displacement + Fair Value Gap). Computes entry, stop-loss, take-profit,
  R:R, and a confidence score.
- **AI analysis** with **ZAI GLM** — each setup gets a structured
  bias / confidence / reasoning write-up.
- **Daily-improvement feedback loop** — outcomes are resolved daily and a
  performance summary (win rate, avg R, best/worst session & direction) is
  injected into every new LLM analysis, so the narrative adapts as data
  accumulates.
- **Apple-style dashboard** (built from `Style.md`) — dark hero tile for the
  active signal, candlestick chart with entry/SL/TP/FVG levels, signal grid,
  and a performance tile.
- **Live updates** via Server-Sent Events — new signals appear instantly.
- **Telegram alerts** — every new signal is pushed to your chat/channel.
- **Persistent storage** — SQLite keeps candles, signals, analyses, outcomes,
  and performance summaries.

---

## Architecture

```
Twelve Data ──▶ fetch 4h candles ──▶ CRT engine ──▶ new Signal (SQLite)
                                                    │
                            ┌───────────────────────┼───────────────────────┐
                            ▼                       ▼                       ▼
                     ZAI GLM analysis        Telegram alert          SSE → Dashboard
                    (uses recent perf)       (if configured)         (Apple-style UI)
                            │
                            ▼
                     stored Analysis
                            │
            daily job: resolve outcomes ──▶ rebuild PerfSummary ──▶ feeds next analysis
```

**Stack:** Python 3.12 · FastAPI · SQLAlchemy · APScheduler · SQLite ·
openai SDK (→ ZAI) · React 18 + Vite · lightweight-charts · vanilla CSS.

---

## Project layout

```
ZaiAgentTrading/
├─ backend/
│  ├─ app/
│  │  ├─ main.py            FastAPI app + scheduler + lifespan
│  │  ├─ config.py          env-driven settings (pydantic-settings)
│  │  ├─ db.py              engine, session, init_db()
│  │  ├─ models.py          Candle, Signal, Analysis, Outcome, PerfSummary
│  │  ├─ schemas.py         pydantic response models
│  │  ├─ events.py          in-process SSE event bus
│  │  ├─ scheduler.py       APScheduler scan + daily jobs
│  │  ├─ api/               chart, signals, performance, control, events routers
│  │  ├─ strategy/          crt.py (detection), scanner.py (pipeline)
│  │  ├─ data/              twelvedata.py (provider), sync.py (upsert)
│  │  ├─ ai/                llm.py (ZAI client), analyzer.py, prompts.py
│  │  ├─ feedback/          outcomes.py (resolve + perf summary)
│  │  └─ notify/            telegram_bot.py
│  ├─ requirements.txt
│  └─ .env.example          ← copy to .env and fill in
├─ frontend/
│  ├─ src/
│  │  ├─ main.jsx, App routes
│  │  ├─ api.js             fetch wrapper + SSE subscriber
│  │  ├─ styles/            tokens.css (Style.md → CSS vars), global.css
│  │  ├─ components/        GlobalNav, SubNav, HeroSignal, SignalCard, Chart, PerfStats
│  │  └─ pages/             Dashboard.jsx, SignalDetail.jsx
│  └─ package.json, vite.config.js
├─ data/                    xauusd.db (created at runtime)
└─ Style.md                 Apple-inspired design system (design source)
```

---

## Setup

### 1. Get API keys

| Service | Where | Needed for |
|---|---|---|
| **Twelve Data** | https://twelvedata.com/pricing (free tier) | Live XAUUSD 4h candles |
| **ZAI (GLM)** | https://z.ai/model-api | AI textual analysis |
| **Telegram bot** | @BotFather → token; chat id via @userinfobot | Signal alerts (optional) |

### 2. Configure environment

```bash
cd backend
cp .env.example .env
# then edit .env and fill in your keys
```

Minimum for a working app: `TWELVE_DATA_API_KEY`. Without it the app runs but
can't fetch candles. Without `ZAI_API_KEY`, signals are still detected and
alerted — only the AI text is skipped.

### 3. Install & run

Two terminals:

```bash
# Terminal 1 — backend (http://localhost:8000)
cd backend
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000

# Terminal 2 — frontend (http://localhost:5173)
cd frontend
npm install
npm run dev
```

Open **http://localhost:5173**.

On startup the scheduler immediately runs one scan and then re-scans every 15
minutes (catching each 4h candle close). You can also click **Scan now** in the
sub-nav.

---

## API reference

Interactive docs at **http://localhost:8000/docs** once running.

| Method | Endpoint | Description |
|---|---|---|
| GET | `/api/health` | Provider/LLM/Telegram status + row counts |
| GET | `/api/candles?limit=200` | 4h OHLCV for the chart |
| GET | `/api/quote` | Latest price (best-effort) |
| GET | `/api/signals?status=open&limit=50` | Signal list |
| GET | `/api/signals/{id}` | Signal + analysis + outcome |
| GET | `/api/performance` | Latest performance summary |
| POST | `/api/scan` | Manually trigger a fetch + CRT scan |
| POST | `/api/signals/{id}/analyze` | Re-run AI analysis for a signal |
| GET | `/api/events` | SSE stream of new signals / performance updates |

---

## How the CRT strategy works

A CRT setup is **Range → Manipulation → Distribution**:

1. **Range** — a tight consolidation of the last `CRT_RANGE_WINDOW` (default 6)
   4h candles. Liquidity rests above the range high and below the range low.
2. **Sweep (manipulation)** — the next candle pokes beyond a range extreme to
   grab liquidity, then closes back inside the range.
   - Poke below range low + close back in → **bullish (LONG)** setup.
   - Poke above range high + close back in → **bearish (SHORT)** setup.
3. **Displacement** — a strong impulsive reversal candle (body ≥
   `CRT_DISPLACEMENT_K` × ATR).
4. **Fair Value Gap** — the standard 3-candle imbalance straddling the
   displacement: the sweep candle's wick and the confirm candle's wick don't
   overlap, leaving a gap.
5. **Trade plan** — Entry at the FVG midpoint, stop beyond the sweep wick (+
   buffer), target the opposite range liquidity with a minimum
   `CRT_MIN_RR` (default 2.0) reward:risk.

**Confidence** is a heuristic 0–100 blending displacement strength, FVG size vs
ATR, sweep depth, and R:R quality.

### The daily-improvement loop

Each signal is resolved after `CRT_LOOKFORWARD_CANDLES` (default 3 = 12h):
**WIN** if TP hit before SL, **LOSS** if SL hit first, else **EXPIRED**, with an
R-multiple. A daily job (06:05 UTC) rebuilds a performance summary — win rate
(last 20 / last 50), avg R, breakdowns by session and direction — and that
summary is injected into every new LLM prompt. As stored history grows, the AI's
analysis adapts to what's actually working. This is the "improve every day"
requirement.

---

## Tuning

All strategy knobs are env vars (see `backend/.env.example`):

| Variable | Default | Meaning |
|---|---|---|
| `CRT_RANGE_WINDOW` | 6 | candles forming the consolidation |
| `CRT_DISPLACEMENT_K` | 1.0 | displacement body ≥ k × ATR |
| `CRT_ATR_PERIOD` | 14 | ATR lookback |
| `CRT_SL_BUFFER_ATR` | 0.15 | SL buffer beyond sweep wick, in ATR |
| `CRT_MIN_RR` | 2.0 | minimum reward:risk for TP |
| `CRT_LOOKFORWARD_CANDLES` | 3 | candles to wait for TP/SL |
| `CRT_SCAN_LOOKBACK` | 30 | candles re-scanned each cycle |
| `SCAN_CRON_MINUTES` | `*/15` | fetch+scan cron minute field |

---

## Disclaimer

This software is for **educational and research purposes only**. It is **not
financial advice** and makes **no claim of profitability**. Candle Range Theory
is a discretionary trading framework; the detection here is a rules-based
approximation, and LLM analysis is narrative, not a prediction. Trading foreign
exchange and gold on margin carries a high level of risk and may not be
suitable for all investors. You are solely responsible for any trading
decisions you make. **Never risk more than you can afford to lose.**
