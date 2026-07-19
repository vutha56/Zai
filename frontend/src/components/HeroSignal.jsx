import React from "react";
import { Link } from "react-router-dom";
import { fmtPrice, fmtRelative, fmtTime, rrOf } from "./helpers";

// Dark hero tile showing the latest active signal (per Style.md `product-tile-dark`).
export default function HeroSignal({ signal }) {
  if (!signal) {
    return (
      <section className="tile tile--dark hero">
        <div className="tile__inner hero__inner">
          <p className="eyebrow eyebrow--dark">Latest Signal</p>
          <h1 className="hero__title">No active signal right now.</h1>
          <p className="hero__sub">
            The CRT engine scans every 4-hour candle close. The next setup will
            appear here automatically.
          </p>
        </div>
        <HeroStyles />
      </section>
    );
  }

  const isLong = signal.direction === "LONG";
  const rr = rrOf(signal.entry, signal.sl, signal.tp);

  return (
    <section className="tile tile--dark hero">
      <div className="tile__inner hero__inner">
        <p className="eyebrow eyebrow--dark">
          Latest Signal · {fmtRelative(signal.created_at)}
        </p>
        <h1 className="hero__title">
          {isLong ? "Buy" : "Sell"} XAUUSD
          <span className={`hero__dir ${isLong ? "hero__dir--long" : "hero__dir--short"}`}>
            {isLong ? "▲" : "▼"}
          </span>
        </h1>
        <p className="hero__sub">
          {signal.timeframe} · {signal.session} session · {Math.round(signal.confidence)}/100 confidence
          {signal.analysis?.bias ? ` · AI bias ${signal.analysis.bias}` : ""}
        </p>
        <div className="hero__tags">
          <span className={`tag ${signal.premium_discount === "discount" ? "tag--long" : signal.premium_discount === "premium" ? "tag--short" : ""}`}>
            {signal.premium_discount}
          </span>
          {signal.in_killzone ? (
            <span className="tag tag--kz">{signal.killzone.replace("_", " ")} killzone</span>
          ) : (
            <span className="tag tag--expired">outside killzone</span>
          )}
          <span className="tag">{signal.entry_model.replace("_", " ")}</span>
        </div>

        <div className="hero__plan mono">
          <PlanCell label="Entry" value={fmtPrice(signal.entry)} />
          <PlanCell label="Stop Loss" value={fmtPrice(signal.sl)} danger />
          <PlanCell label="Take Profit" value={fmtPrice(signal.tp)} good />
          <PlanCell label="Reward:Risk" value={`${rr.toFixed(1)} : 1`} />
        </div>

        {signal.one_liner && (
          <p className="hero__oneliner">{signal.one_liner}</p>
        )}

        <div className="hero__cta">
          <Link to={`/signal/${signal.id}`} className="btn-primary hero__btn">
            View analysis
          </Link>
          <span className="hero__ts muted">
            Triggered {fmtTime(signal.candle_ts)}
          </span>
        </div>
      </div>
      <HeroStyles />
    </section>
  );
}

function PlanCell({ label, value, good, danger }) {
  return (
    <div className={`hero__plan-cell ${good ? "hero__plan-cell--good" : ""} ${danger ? "hero__plan-cell--danger" : ""}`}>
      <span className="hero__plan-label">{label}</span>
      <strong>{value}</strong>
    </div>
  );
}

function HeroStyles() {
  return (
    <style>{`
      .hero__inner {
        text-align: center;
        align-items: center;
      }
      .eyebrow--dark {
        color: var(--color-primary-on-dark);
      }
      .hero__title {
        font-size: 56px;
        font-weight: 600;
        line-height: 1.07;
        letter-spacing: -0.028em;
        margin-top: var(--space-xs);
        display: inline-flex;
        align-items: center;
        gap: var(--space-sm);
      }
      .hero__dir {
        font-size: 40px;
      }
      .hero__dir--long { color: #34c759; }
      .hero__dir--short { color: #ff453a; }
      .hero__sub {
        font-size: 28px;
        font-weight: 400;
        line-height: 1.14;
        letter-spacing: 0.196px;
        color: var(--color-body-muted);
        margin: var(--space-sm) 0 0;
        max-width: 640px;
      }
      .hero__tags {
        display: flex;
        gap: var(--space-xs);
        flex-wrap: wrap;
        justify-content: center;
        margin-top: var(--space-sm);
      }
      .hero__tags .tag--kz { background: rgba(41, 151, 255, 0.18); }
      .hero__plan {
        display: grid;
        grid-template-columns: repeat(4, minmax(0, 1fr));
        gap: var(--space-sm);
        width: 100%;
        max-width: 720px;
        margin: var(--space-lg) 0;
      }
      .hero__plan-cell {
        background: var(--color-surface-tile-2);
        border-radius: var(--radius-md);
        padding: var(--space-sm) var(--space-md);
        display: flex;
        flex-direction: column;
        gap: 4px;
        align-items: flex-start;
      }
      .hero__plan-cell--good strong { color: #34c759; }
      .hero__plan-cell--danger strong { color: #ff453a; }
      .hero__plan-label {
        font-size: 11px;
        text-transform: uppercase;
        letter-spacing: 0.05em;
        color: var(--color-body-muted);
        font-weight: 600;
      }
      .hero__plan-cell strong {
        font-size: 22px;
        font-weight: 600;
        color: var(--color-body-on-dark);
      }
      .hero__oneliner {
        font-size: 17px;
        color: var(--color-body-muted);
        max-width: 640px;
        margin: 0 0 var(--space-md);
        line-height: 1.5;
      }
      .hero__cta {
        display: flex;
        align-items: center;
        gap: var(--space-lg);
        margin-top: var(--space-xs);
      }
      .hero__btn {
        text-decoration: none;
      }
      .hero__ts {
        font-size: 14px;
        color: var(--color-body-muted);
      }
      @media (max-width: 734px) {
        .hero__title { font-size: 40px; }
        .hero__dir { font-size: 28px; }
        .hero__sub { font-size: 21px; }
        .hero__plan { grid-template-columns: repeat(2, 1fr); }
        .tile.hero { padding: var(--space-xl) var(--space-md); }
      }
    `}</style>
  );
}
