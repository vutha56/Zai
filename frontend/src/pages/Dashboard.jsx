import React, { useEffect, useState, useCallback } from "react";
import GlobalNav from "../components/GlobalNav";
import SubNav from "../components/SubNav";
import HeroSignal from "../components/HeroSignal";
import SignalCard from "../components/SignalCard";
import PerfStats from "../components/PerfStats";
import Chart from "../components/Chart";
import ErrorBoundary from "../components/ErrorBoundary";
import { api, subscribeEvents } from "../api";

export default function Dashboard() {
  const [health, setHealth] = useState(null);
  const [price, setPrice] = useState(null);
  const [candles, setCandles] = useState([]);
  const [signals, setSignals] = useState([]);
  const [perf, setPerf] = useState({ win_rate_20: 0, win_rate_50: 0, avg_r: 0, sample_size: 0, narrative: "" });
  const [scanning, setScanning] = useState(false);
  const [flash, setFlash] = useState("");
  const [timeframe, setTimeframe] = useState("5min");
  const [symbol, setSymbol] = useState("XAU/USD");
  const [smc, setSmc] = useState(null);
  const [context, setContext] = useState(null);

  const refreshAll = useCallback(async () => {
    const [h, s, p] = await Promise.all([
      api.health(),
      api.signals(undefined, 24, timeframe, symbol),
      api.performance(),
    ]);
    setHealth(h);
    setSignals(s);
    setPerf(p);
    try {
      const c = await api.candles(200, timeframe, symbol);
      setCandles(c);
    } catch { /* ignore */ }
    try {
      const smcData = await api.smc(300, timeframe, symbol);
      setSmc(smcData);
    } catch { /* ignore */ }
    try {
      const ctx = await api.context(300, timeframe, symbol);
      setContext(ctx);
    } catch { /* ignore */ }
    try {
      const q = await api.quote(symbol);
      if (q.price) setPrice(q.price);
    } catch { /* ignore */ }
  }, [timeframe, symbol]);

  useEffect(() => {
    refreshAll();
    const es = subscribeEvents((evt) => {
      if (evt.type === "signal") {
        const tf = evt.data?.timeframe;
        const sym = evt.data?.symbol;
        if (sym && sym !== symbol) {
          setFlash(`New ${sym.replace("/", "")} ${tf || ""} signal`);
        } else if (tf && tf !== timeframe) {
          setFlash(`New ${tf} signal — switch to view`);
        } else {
          setFlash("New signal detected");
        }
        setTimeout(() => setFlash(""), 4000);
        refreshAll();
      } else if (evt.type === "performance" || evt.type === "analysis") {
        refreshAll();
      }
    });
    const poll = setInterval(refreshAll, 60000); // gentle polling as a fallback
    return () => {
      es.close();
      clearInterval(poll);
    };
  }, [refreshAll]);

  const handleScan = async () => {
    setScanning(true);
    try {
      await api.scan();
      await refreshAll();
    } catch (e) {
      setFlash("Scan failed: " + e.message);
    } finally {
      setScanning(false);
      setTimeout(() => setFlash(""), 4000);
    }
  };

  const active = signals.find((s) => s.status === "open") || null;
  const recent = signals.slice(0, 12);

  return (
    <>
      <GlobalNav />
      <SubNav
        price={price}
        health={health}
        onScan={handleScan}
        scanning={scanning}
        timeframe={timeframe}
        onTimeframe={setTimeframe}
        symbol={symbol}
        onSymbol={setSymbol}
      />

      {flash && (
        <div className="flash">
          {flash}
          <style>{`
            .flash {
              position: fixed; top: calc(var(--nav-height) + 8px); right: 16px; z-index: 200;
              background: var(--color-primary); color: #fff; padding: 10px 18px;
              border-radius: var(--radius-pill); font-size: 14px; font-weight: 600;
              box-shadow: 0 4px 16px rgba(0,102,204,0.3); animation: flashIn 0.2s ease;
            }
            @keyframes flashIn { from { transform: translateY(-8px); opacity: 0; } to { transform: none; opacity: 1; } }
          `}</style>
        </div>
      )}

      <HeroSignal signal={active} />

      <section className="tile tile--light">
        <div className="tile__inner chart-tile">
          <p className="eyebrow">{timeframe} Chart · {(symbol || "").replace("/", "")}</p>
          <h2 className="chart-tile__title">Smart Money structure</h2>
          <p className="chart-tile__sub">
            Order blocks, FVG / iFVG zones, daily bias, market structure, volume profile & Power of 3.
          </p>
          <div className="chart-legend">
            <Legend color="rgba(0,150,199,0.5)" label="OB" />
            <Legend color="rgba(88,86,214,0.5)" label="Breaker" />
            <Legend color="rgba(26,143,58,0.5)" label="FVG ▲" />
            <Legend color="rgba(194,54,75,0.5)" label="FVG ▼" />
            <Legend color="rgba(26,143,58,0.8)" label="PDH" line />
            <Legend color="rgba(194,54,75,0.8)" label="PDL" line />
            <Legend color="rgba(255,159,0,0.85)" label="POC" line />
            <Legend color="rgba(0,102,204,0.55)" label="VAH/VAL" line />
            <Legend color="rgba(88,86,214,0.7)" label="BOS" line />
            <Legend color="rgba(255,149,0,0.75)" label="CHoCH" line />
            <Legend color="rgba(194,54,75,0.85)" label="MSS" line />
          </div>
          <div className="chart-tile__mount">
            <ErrorBoundary>
              <Chart candles={candles} signal={active} smc={smc} context={context} height={440} />
            </ErrorBoundary>
          </div>
          {!candles.length && (
            <p className="muted chart-tile__empty">
              No chart data yet — add your Twelve Data API key and run a scan.
            </p>
          )}
        </div>
        <ChartTileStyles />
      </section>

      <section className="tile tile--parchment">
        <div className="tile__inner grid-section">
          <p className="eyebrow">Signals</p>
          <h2 className="grid-section__title">Recent CRT setups</h2>
          {recent.length ? (
            <div className="grid">
              {recent.map((s) => (
                <SignalCard key={s.id} signal={s} />
              ))}
            </div>
          ) : (
            <div className="empty">
              <p className="empty__title">No signals yet</p>
              <p className="muted">
                The scanner runs every 4-hour candle close. Add your API keys in
                <code> backend/.env</code> and click <strong>Scan now</strong>.
              </p>
            </div>
          )}
        </div>
        <GridSectionStyles />
      </section>

      <PerfStats perf={perf} />

      <Footer />
    </>
  );
}

function Legend({ color, label, line }) {
  return (
    <span className="chart-legend__item">
      <span
        className={`chart-legend__swatch ${line ? "chart-legend__swatch--line" : ""}`}
        style={line ? { background: color } : { background: color }}
      />
      {label}
    </span>
  );
}

function Footer() {
  return (
    <footer className="footer">
      <div className="footer__inner">
        <p>
          XAUUSD CRT-4H Signals · Candle Range Theory detection + ZAI GLM analysis.
        </p>
        <p className="footer__legal">
          Educational tool, not financial advice. Trading XAUUSD carries
          substantial risk. Signals are heuristic and may lose money.
        </p>
      </div>
      <style>{`
        .footer { background: var(--color-canvas-parchment); padding: 48px var(--space-lg); border-top: 1px solid var(--color-hairline); }
        .footer__inner { max-width: var(--grid-max); margin: 0 auto; }
        .footer p { font-size: 12px; color: var(--color-ink-muted-48); margin: 4px 0; line-height: 1.4; }
        .footer__legal { max-width: 640px; }
      `}</style>
    </footer>
  );
}

function ChartTileStyles() {
  return (
    <style>{`
      .chart-tile { max-width: var(--grid-max); text-align: center; align-items: center; }
      .chart-tile__title { font-size: 40px; line-height: 1.1; letter-spacing: -0.02em; margin-top: var(--space-xs); }
      .chart-tile__sub { font-size: 21px; color: var(--color-ink-muted-48); margin: var(--space-sm) 0 var(--space-md); }
      .chart-legend { display: flex; gap: var(--space-md); flex-wrap: wrap; justify-content: center; margin-bottom: var(--space-md); }
      .chart-legend__item { display: inline-flex; align-items: center; gap: 6px; font-size: 12px; color: var(--color-ink-muted-80); font-weight: 600; }
      .chart-legend__swatch { display: inline-block; width: 14px; height: 10px; border-radius: 2px; }
      .chart-legend__swatch--line { height: 2px; border-radius: 1px; }
      .chart-tile__mount { width: 100%; background: var(--color-canvas); border: 1px solid var(--color-hairline); border-radius: var(--radius-lg); padding: var(--space-md); }
      .chart-tile__empty { margin-top: var(--space-md); }
      @media (max-width: 734px) { .chart-tile__title { font-size: 32px; } }
    `}</style>
  );
}

function GridSectionStyles() {
  return (
    <style>{`
      .grid-section { max-width: var(--grid-max); }
      .grid-section__title { font-size: 40px; line-height: 1.1; letter-spacing: -0.02em; margin: var(--space-xs) 0 var(--space-lg); text-align: center; }
      .grid { display: grid; grid-template-columns: repeat(3, 1fr); gap: var(--space-lg); }
      .empty { text-align: center; padding: var(--space-xxl) var(--space-md); background: var(--color-canvas); border: 1px dashed var(--color-hairline); border-radius: var(--radius-lg); }
      .empty__title { font-size: 21px; font-weight: 600; margin: 0 0 var(--space-sm); color: var(--color-ink); }
      .empty code { background: var(--color-divider-soft); padding: 1px 6px; border-radius: 4px; font-family: monospace; font-size: 14px; }
      @media (max-width: 1068px) { .grid { grid-template-columns: repeat(2, 1fr); } }
      @media (max-width: 640px) { .grid { grid-template-columns: 1fr; } .grid-section__title { font-size: 32px; } }
    `}</style>
  );
}
