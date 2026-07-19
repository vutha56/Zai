import React, { useEffect, useState } from "react";
import { useParams, Link } from "react-router-dom";
import ReactMarkdown from "react-markdown";
import GlobalNav from "../components/GlobalNav";
import SubNav from "../components/SubNav";
import Chart from "../components/Chart";
import ErrorBoundary from "../components/ErrorBoundary";
import { api } from "../api";
import { fmtPrice, fmtTime, rrOf } from "../components/helpers";

export default function SignalDetail() {
  const { id } = useParams();
  const [signal, setSignal] = useState(null);
  const [candles, setCandles] = useState([]);
  const [smc, setSmc] = useState(null);
  const [context, setContext] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  useEffect(() => {
    let alive = true;
    (async () => {
      setLoading(true);
      setError("");
      try {
        const s = await api.signal(id);
        const tf = s.timeframe || "5min";
        const sym = s.symbol || "XAU/USD";
        const [c, smcData, ctxData] = await Promise.all([
          api.candles(200, tf, sym),
          api.smc(300, tf, sym).catch(() => null),
          api.context(300, tf, sym).catch(() => null),
        ]);
        if (!alive) return;
        setSignal(s);
        setCandles(c);
        setSmc(smcData);
        setContext(ctxData);
      } catch (e) {
        if (alive) setError(e.message);
      } finally {
        if (alive) setLoading(false);
      }
    })();
    return () => {
      alive = false;
    };
  }, [id]);

  if (loading)
    return (
      <>
        <GlobalNav />
        <div className="center-msg">Loading…</div>
        <style>{`.center-msg { padding: var(--space-section); text-align: center; color: var(--color-ink-muted-48); }`}</style>
      </>
    );

  if (error || !signal)
    return (
      <>
        <GlobalNav />
        <div className="center-msg">
          <p>Could not load this signal.</p>
          <Link to="/" className="btn-secondary" style={{ marginTop: 16, display: "inline-flex" }}>
            Back to dashboard
          </Link>
        </div>
        <style>{`.center-msg { padding: var(--space-section); text-align: center; color: var(--color-ink-muted-48); }`}</style>
      </>
    );

  const isLong = signal.direction === "LONG";
  const rr = rrOf(signal.entry, signal.sl, signal.tp);
  const a = signal.analysis;
  const o = signal.outcome;

  return (
    <>
      <GlobalNav />
      <SubNav health={{ provider: true }} />

      <section className={`tile ${isLong ? "tile--light" : "tile--dark"} detail-hero`}>
        <div className="tile__inner detail-hero__inner">
          <Link to="/" className={`detail-hero__back ${isLong ? "" : "detail-hero__back--dark"}`}>
            ← Back
          </Link>
          <p className="eyebrow" style={isLong ? {} : { color: "var(--color-primary-on-dark)" }}>
            Signal #{signal.id} · {fmtTime(signal.candle_ts)}
          </p>
          <h1 className="detail-hero__title">
            {isLong ? "Buy" : "Sell"} XAUUSD · {signal.timeframe}
          </h1>
          <div className="detail-hero__tags">
            <span className={`tag ${isLong ? "tag--long" : "tag--short"}`}>
              {isLong ? "▲ Long" : "▼ Short"}
            </span>
            <span className="tag tag--tf">{signal.timeframe}</span>
            <span className={`tag ${signal.premium_discount === "discount" ? "tag--long" : signal.premium_discount === "premium" ? "tag--short" : ""}`}>
              {signal.premium_discount}
            </span>
            {signal.in_killzone ? (
              <span className="tag tag--kz">{signal.killzone.replace("_", " ")} killzone</span>
            ) : (
              <span className="tag tag--expired">outside killzone</span>
            )}
            <span className={`tag tag--${signal.status}`}>{signal.status}</span>
            <span className="tag">{signal.session} session</span>
            {a?.bias && <span className="tag">AI bias: {a.bias}</span>}
          </div>
        </div>
        <DetailHeroStyles dark={!isLong} />
      </section>

      <section className="tile tile--parchment">
        <div className="tile__inner detail-grid">
          <div className="detail-grid__left">
            <div className="detail-card">
              <h3 className="detail-card__h">Trade plan</h3>
              <div className="plan-rows mono">
                <Row label="Entry" value={fmtPrice(signal.entry)} />
                <Row label="Stop loss" value={fmtPrice(signal.sl)} tone="bad" />
                <Row label="Take profit" value={fmtPrice(signal.tp)} tone="good" />
                <Row label="Reward : Risk" value={`${rr.toFixed(2)} : 1`} />
                <Row label="Confidence" value={`${Math.round(signal.confidence)}/100`} />
              </div>
            </div>

            <div className="detail-card">
              <h3 className="detail-card__h">CRT structure</h3>
              <div className="plan-rows mono">
                <Row label="Range high" value={fmtPrice(signal.range_high)} />
                <Row label="Range low" value={fmtPrice(signal.range_low)} />
                <Row label="Equilibrium" value={fmtPrice((signal.range_high + signal.range_low) / 2)} />
                <Row label="Sweep level" value={fmtPrice(signal.sweep_level)} />
                <Row label="FVG bottom" value={fmtPrice(signal.fvg_bottom)} />
                <Row label="FVG top" value={fmtPrice(signal.fvg_top)} />
                <Row label="ATR(14)" value={fmtPrice(signal.atr)} />
              </div>
            </div>

            <div className="detail-card">
              <h3 className="detail-card__h">Strategy context</h3>
              <div className="plan-rows mono">
                <Row label="Timeframe" value={signal.timeframe} />
                <Row label="Premium/Discount" value={signal.premium_discount}
                  tone={signal.premium_discount === (isLong ? "discount" : "premium") ? "good" : "bad"} />
                <Row label="Killzone" value={signal.in_killzone ? signal.killzone.replace("_", " ") : "none"}
                  tone={signal.in_killzone ? "good" : ""} />
                <Row label="Entry model" value={signal.entry_model.replace("_", " ")} />
                <Row label="Session" value={signal.session} />
              </div>
              <p className="detail-card__note">
                ICT enhancement: longs from discount + shorts from premium, scored higher inside the
                London/NY killzones.
              </p>
            </div>

            {o && (
              <div className="detail-card">
                <h3 className="detail-card__h">Outcome</h3>
                <div className="plan-rows mono">
                  <Row label="Result" value={o.result.toUpperCase()} tone={o.result === "win" ? "good" : o.result === "loss" ? "bad" : ""} />
                  <Row label="R-multiple" value={`${o.r_multiple >= 0 ? "+" : ""}${o.r_multiple.toFixed(2)}R`} tone={o.r_multiple >= 0 ? "good" : "bad"} />
                  <Row label="Hit price" value={o.hit_price ? fmtPrice(o.hit_price) : "—"} />
                  <Row label="Resolved" value={fmtTime(o.resolved_at)} />
                </div>
              </div>
            )}
          </div>

          <div className="detail-grid__right">
            <div className="detail-card detail-card--analysis">
              <h3 className="detail-card__h">AI analysis {a ? `· ${a.llm_model}` : ""}</h3>
              {a ? (
                <>
                  {a.llm_confidence > 0 && (
                    <div className="detail-card__conf mono">
                      <span>AI confidence</span>
                      <strong>{Math.round(a.llm_confidence)}/100</strong>
                    </div>
                  )}
                  <div className="markdown">
                    <ReactMarkdown>
                      {a.reasoning_md || `**Bias: ${a.bias}**`}
                    </ReactMarkdown>
                  </div>
                </>
              ) : (
                <p className="muted">
                  No AI analysis available. Add a <code>ZAI_API_KEY</code> to{" "}
                  <code>backend/.env</code> and click re-analyze.
                </p>
              )}
              <button
                className="btn-secondary detail-card__reanalyze"
                onClick={async () => {
                  try {
                    await api.analyze(signal.id);
                    const s = await api.signal(id);
                    setSignal(s);
                  } catch (e) {
                    alert("Analysis failed: " + e.message);
                  }
                }}
              >
                Re-run AI analysis
              </button>
            </div>
          </div>
        </div>
        <DetailGridStyles />
      </section>

      <section className="tile tile--light">
        <div className="tile__inner" style={{ maxWidth: "var(--grid-max)" }}>
          <p className="eyebrow">Chart with setup levels</p>
          <h2 className="detail-chart__title">XAUUSD {signal.timeframe} · Signal #{signal.id}</h2>
          <div className="chart-tile__mount" style={{ marginTop: "var(--space-lg)" }}>
            <ErrorBoundary>
              <Chart candles={candles} signal={signal} smc={smc} context={context} height={460} />
            </ErrorBoundary>
          </div>
        </div>
        <style>{`
          .detail-chart__title { font-size: 32px; letter-spacing: -0.02em; text-align: center; }
          .chart-tile__mount { width: 100%; background: var(--color-canvas); border: 1px solid var(--color-hairline); border-radius: var(--radius-lg); padding: var(--space-md); }
        `}</style>
      </section>

      <FooterLite />
    </>
  );
}

function Row({ label, value, tone }) {
  return (
    <div className={`plan-row ${tone ? `plan-row--${tone}` : ""}`}>
      <span className="plan-row__label">{label}</span>
      <span className="plan-row__value">{value}</span>
    </div>
  );
}

function FooterLite() {
  return (
    <footer className="footer">
      <div className="footer__inner">
        <p className="footer__legal" style={{ maxWidth: 640 }}>
          Educational tool, not financial advice. Trading XAUUSD carries substantial risk.
        </p>
      </div>
      <style>{`
        .footer { background: var(--color-canvas-parchment); padding: var(--space-lg); }
        .footer__inner { max-width: var(--grid-max); margin: 0 auto; }
        .footer__legal { font-size: 12px; color: var(--color-ink-muted-48); line-height: 1.4; }
      `}</style>
    </footer>
  );
}

function DetailHeroStyles({ dark }) {
  return (
    <style>{`
      .detail-hero__inner { max-width: var(--grid-max); align-items: flex-start; text-align: left; }
      .detail-hero__back { color: var(--color-primary); font-size: 14px; text-decoration: none; margin-bottom: var(--space-md); display: inline-block; }
      .detail-hero__back--dark { color: var(--color-primary-on-dark); }
      .detail-hero__title { font-size: 48px; line-height: 1.07; letter-spacing: -0.028em; margin-top: var(--space-xs); }
      .detail-hero__tags { display: flex; gap: var(--space-xs); margin-top: var(--space-md); flex-wrap: wrap; }
      .tile.detail-hero { padding-top: var(--space-xxl); padding-bottom: var(--space-xxl); }
      @media (max-width: 734px) { .detail-hero__title { font-size: 32px; } }
    `}</style>
  );
}

function DetailGridStyles() {
  return (
    <style>{`
      .detail-grid { max-width: var(--grid-max); display: grid; grid-template-columns: 380px 1fr; gap: var(--space-lg); align-items: start; }
      .detail-grid__left { display: flex; flex-direction: column; gap: var(--space-lg); }
      .detail-card { background: var(--color-canvas); border: 1px solid var(--color-hairline); border-radius: var(--radius-lg); padding: var(--space-lg); }
      .detail-card__h { font-size: 14px; text-transform: uppercase; letter-spacing: 0.04em; color: var(--color-ink-muted-48); margin: 0 0 var(--space-md); font-weight: 600; }
      .plan-rows { display: flex; flex-direction: column; gap: var(--space-xs); }
      .plan-row { display: flex; justify-content: space-between; align-items: center; padding: 6px 0; border-bottom: 1px solid var(--color-divider-soft); }
      .plan-row:last-child { border-bottom: none; }
      .plan-row__label { font-size: 14px; color: var(--color-ink-muted-80); }
      .plan-row__value { font-size: 17px; font-weight: 600; color: var(--color-ink); }
      .plan-row--good .plan-row__value { color: var(--color-long); }
      .plan-row--bad .plan-row__value { color: var(--color-short); }
      .detail-card--analysis { min-height: 240px; }
      .detail-card__conf { display: flex; justify-content: space-between; padding: var(--space-sm) var(--space-md); background: var(--color-canvas-parchment); border-radius: var(--radius-md); margin-bottom: var(--space-md); font-size: 14px; }
      .detail-card__conf strong { color: var(--color-primary); font-size: 17px; }
      .detail-card__reanalyze { margin-top: var(--space-lg); align-self: flex-start; padding: 8px 18px; font-size: 14px; }
      .detail-card__note { margin: var(--space-sm) 0 0; font-size: 12px; color: var(--color-ink-muted-48); line-height: 1.4; }
      @media (max-width: 834px) { .detail-grid { grid-template-columns: 1fr; } }
    `}</style>
  );
}
