import React, { useEffect, useState } from "react";
import GlobalNav from "../components/GlobalNav";
import SubNav from "../components/SubNav";
import EquityChart from "../components/EquityChart";
import ErrorBoundary from "../components/ErrorBoundary";
import { api } from "../api";
import { fmtPrice, fmtTime } from "../components/helpers";

export default function Backtest() {
  const [options, setOptions] = useState(null);
  const [form, setForm] = useState({
    symbol: "XAU/USD",
    timeframe: "4h",
    candles_limit: 500,
    lookforward_bars: 8,
    min_confidence: 0,
    initial_capital: 10000,
    risk_per_trade_pct: 1,
  });
  const [result, setResult] = useState(null);
  const [running, setRunning] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    api
      .backtestOptions()
      .then((o) => {
        setOptions(o);
        if (o.defaults) setForm((f) => ({ ...f, ...o.defaults, symbol: o.symbols[0] || f.symbol }));
      })
      .catch(() => {});
  }, []);

  const run = async () => {
    setRunning(true);
    setError("");
    setResult(null);
    try {
      const r = await api.backtest(form);
      setResult(r);
    } catch (e) {
      setError(e.message);
    } finally {
      setRunning(false);
    }
  };

  const m = result?.metrics || {};

  return (
    <>
      <GlobalNav />
      <SubNav health={options ? { provider: true, symbols: options.symbols, timeframes: options.timeframes } : null} />

      <section className="tile tile--light">
        <div className="tile__inner bt-inner">
          <p className="eyebrow">Backtest</p>
          <h1 className="bt-title">Strategy backtester</h1>
          <p className="bt-sub">
            Replays historical candles through the CRT engine with risk-based position sizing.
            For research only — past performance does not guarantee future results.
          </p>

          <div className="bt-form">
            <Field label="Symbol">
              <select value={form.symbol} onChange={(e) => setForm({ ...form, symbol: e.target.value })}>
                {(options?.symbols || ["XAU/USD", "BTC/USD"]).map((s) => (
                  <option key={s} value={s}>{s}</option>
                ))}
              </select>
            </Field>
            <Field label="Timeframe">
              <select value={form.timeframe} onChange={(e) => setForm({ ...form, timeframe: e.target.value })}>
                {(options?.timeframes || ["5min", "15min", "1h", "4h"]).map((t) => (
                  <option key={t} value={t}>{t}</option>
                ))}
              </select>
            </Field>
            <Field label="Candles">
              <input type="number" min={50} max={5000} value={form.candles_limit}
                onChange={(e) => setForm({ ...form, candles_limit: +e.target.value })} />
            </Field>
            <Field label="Lookforward (bars)">
              <input type="number" min={1} max={50} value={form.lookforward_bars}
                onChange={(e) => setForm({ ...form, lookforward_bars: +e.target.value })} />
            </Field>
            <Field label="Min confidence">
              <input type="number" min={0} max={100} value={form.min_confidence}
                onChange={(e) => setForm({ ...form, min_confidence: +e.target.value })} />
            </Field>
            <Field label="Capital">
              <input type="number" min={1} value={form.initial_capital}
                onChange={(e) => setForm({ ...form, initial_capital: +e.target.value })} />
            </Field>
            <Field label="Risk / trade %">
              <input type="number" min={0.1} max={10} step={0.1} value={form.risk_per_trade_pct}
                onChange={(e) => setForm({ ...form, risk_per_trade_pct: +e.target.value })} />
            </Field>
            <button className="btn-primary bt-run" onClick={run} disabled={running}>
              {running ? "Running…" : "Run backtest"}
            </button>
          </div>

          {error && <p className="bt-error">Error: {error}</p>}
          {m.error && <p className="bt-error">{m.error}</p>}
        </div>
        <BtFormStyles />
      </section>

      {result && m.trades !== undefined && (
        <>
          <section className="tile tile--parchment">
            <div className="tile__inner bt-inner">
              <p className="eyebrow">Results</p>
              <h2 className="bt-title">Performance</h2>
              <div className="bt-stats">
                <Stat label="Trades" value={m.trades} sub={`${m.wins || 0}W / ${m.losses || 0}L / ${m.expired || 0}exp`} />
                <Stat label="Win rate" value={`${m.win_rate}%`} tone={m.win_rate >= 50 ? "good" : "bad"} />
                <Stat label="Avg R" value={`${m.avg_r >= 0 ? "+" : ""}${m.avg_r}R`} tone={m.avg_r >= 0 ? "good" : "bad"} />
                <Stat label="Profit factor" value={m.profit_factor == null ? "∞" : m.profit_factor} tone={m.profit_factor == null || m.profit_factor >= 1 ? "good" : "bad"} />
                <Stat label="Max drawdown" value={`${m.max_drawdown_pct}%`} tone={m.max_drawdown_pct < 15 ? "good" : "bad"} />
                <Stat label="Return" value={`${m.return_pct >= 0 ? "+" : ""}${m.return_pct}%`} tone={m.return_pct >= 0 ? "good" : "bad"} />
                <Stat label="Sharpe (R)" value={m.sharpe_r} />
                <Stat label="Final equity" value={`$${(m.final_equity || 0).toLocaleString()}`} />
              </div>
            </div>
          </section>

          <section className="tile tile--light">
            <div className="tile__inner bt-inner">
              <p className="eyebrow">Equity curve</p>
              <div className="bt-chart">
                <ErrorBoundary>
                  <EquityChart equity={result.equity_curve} height={380} />
                </ErrorBoundary>
              </div>
            </div>
          </section>

          <section className="tile tile--parchment">
            <div className="tile__inner bt-inner">
              <p className="eyebrow">Trades ({result.trades.length})</p>
              <div className="bt-trades">
                <table>
                  <thead>
                    <tr>
                      <th>Date</th><th>Dir</th><th>Entry</th><th>SL</th><th>TP</th>
                      <th>Conf</th><th>P/D</th><th>KZ</th><th>Result</th><th>R</th><th>Bars</th>
                    </tr>
                  </thead>
                  <tbody>
                    {result.trades.map((t, i) => (
                      <tr key={i}>
                        <td>{fmtTime(t.candle_ts)}</td>
                        <td className={t.direction === "LONG" ? "tg-long" : "tg-short"}>{t.direction}</td>
                        <td className="mono">{fmtPrice(t.entry)}</td>
                        <td className="mono">{fmtPrice(t.sl)}</td>
                        <td className="mono">{fmtPrice(t.tp)}</td>
                        <td>{Math.round(t.confidence)}</td>
                        <td>{t.premium_discount}</td>
                        <td>{t.killzone ? t.killzone.replace("_", " ") : "—"}</td>
                        <td className={`res-${t.result}`}>{t.result}</td>
                        <td className={`mono ${t.r_multiple >= 0 ? "pos" : "neg"}`}>{t.r_multiple >= 0 ? "+" : ""}{t.r_multiple}</td>
                        <td>{t.bars_to_resolve}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          </section>

          <p className="bt-disclaimer">
            ⚠️ Educational tool. Backtests on small samples (under ~30 trades) are not statistically
            meaningful and over-fitting to a single run is easy. This validates internal consistency
            of the strategy logic — it is not a predictor of future returns.
          </p>
        </>
      )}
    </>
  );
}

function Field({ label, children }) {
  return (
    <label className="bt-field">
      <span>{label}</span>
      {children}
    </label>
  );
}

function Stat({ label, value, sub, tone }) {
  return (
    <div className={`bt-stat ${tone ? `bt-stat--${tone}` : ""}`}>
      <span className="bt-stat-label">{label}</span>
      <strong className="bt-stat-value mono">{value}</strong>
      {sub && <span className="bt-stat-sub">{sub}</span>}
    </div>
  );
}

function BtFormStyles() {
  return (
    <style>{`
      .bt-inner { max-width: var(--grid-max); align-items: center; text-align: center; }
      .bt-title { font-size: 40px; line-height: 1.1; letter-spacing: -0.02em; margin-top: var(--space-xs); }
      .bt-sub { font-size: 17px; color: var(--color-ink-muted-48); margin: var(--space-sm) 0 var(--space-lg); max-width: 600px; }
      .bt-form { display: grid; grid-template-columns: repeat(4, minmax(0,1fr)) auto; gap: var(--space-md); align-items: end; width: 100%; max-width: 900px; }
      .bt-field { display: flex; flex-direction: column; gap: 6px; text-align: left; font-size: 12px; color: var(--color-ink-muted-48); font-weight: 600; text-transform: uppercase; letter-spacing: 0.03em; }
      .bt-field select, .bt-field input { font-family: inherit; font-size: 15px; padding: 8px 12px; border: 1px solid var(--color-hairline); border-radius: var(--radius-md); background: var(--color-canvas); color: var(--color-ink); text-transform: none; letter-spacing: 0; }
      .bt-run { height: 38px; padding: 0 24px; }
      .bt-error { color: var(--color-short); margin-top: var(--space-md); }
      .bt-stats { display: grid; grid-template-columns: repeat(4, 1fr); gap: var(--space-sm); width: 100%; margin-top: var(--space-lg); }
      .bt-stat { background: var(--color-canvas); border: 1px solid var(--color-hairline); border-radius: var(--radius-lg); padding: var(--space-md); display: flex; flex-direction: column; gap: 4px; align-items: flex-start; }
      .bt-stat-label { font-size: 11px; text-transform: uppercase; letter-spacing: 0.04em; color: var(--color-ink-muted-48); font-weight: 600; }
      .bt-stat-value { font-size: 26px; font-weight: 600; color: var(--color-ink); }
      .bt-stat-sub { font-size: 11px; color: var(--color-ink-muted-48); }
      .bt-stat--good .bt-stat-value { color: var(--color-long); }
      .bt-stat--bad .bt-stat-value { color: var(--color-short); }
      .bt-chart { width: 100%; background: var(--color-canvas); border: 1px solid var(--color-hairline); border-radius: var(--radius-lg); padding: var(--space-md); margin-top: var(--space-md); }
      .bt-trades { width: 100%; overflow-x: auto; margin-top: var(--space-md); background: var(--color-canvas); border: 1px solid var(--color-hairline); border-radius: var(--radius-lg); }
      .bt-trades table { width: 100%; border-collapse: collapse; font-size: 13px; }
      .bt-trades th { text-align: left; padding: 10px 12px; background: var(--color-canvas-parchment); color: var(--color-ink-muted-48); font-weight: 600; font-size: 11px; text-transform: uppercase; letter-spacing: 0.04em; border-bottom: 1px solid var(--color-hairline); }
      .bt-trades td { padding: 8px 12px; border-bottom: 1px solid var(--color-divider-soft); }
      .bt-trades .tg-long { color: var(--color-long); font-weight: 600; }
      .bt-trades .tg-short { color: var(--color-short); font-weight: 600; }
      .bt-trades .res-win { color: var(--color-long); font-weight: 600; }
      .bt-trades .res-loss { color: var(--color-short); font-weight: 600; }
      .bt-trades .pos { color: var(--color-long); }
      .bt-trades .neg { color: var(--color-short); }
      .bt-disclaimer { padding: var(--space-lg); text-align: center; color: var(--color-ink-muted-48); font-size: 13px; max-width: 700px; margin: 0 auto; }
      @media (max-width: 834px) { .bt-form { grid-template-columns: 1fr 1fr; } .bt-stats { grid-template-columns: 1fr 1fr; } .bt-title { font-size: 30px; } }
    `}</style>
  );
}
