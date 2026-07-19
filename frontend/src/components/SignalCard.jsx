import React from "react";
import { Link } from "react-router-dom";
import { fmtPrice, fmtRelative, rrOf } from "./helpers";

// White utility card (per Style.md `store-utility-card`, 18px radius + hairline).
export default function SignalCard({ signal }) {
  const isLong = signal.direction === "LONG";
  const rr = rrOf(signal.entry, signal.sl, signal.tp);
  const status = signal.status;

  return (
    <Link to={`/signal/${signal.id}`} className="signal-card utility-card">
      <div className="signal-card__head">
        <span className={`tag ${isLong ? "tag--long" : "tag--short"}`}>
          {isLong ? "▲ Long" : "▼ Short"}
        </span>
        <span className="tag signal-card__tf">{signal.timeframe}</span>
        {signal.in_killzone && signal.killzone && (
          <span className="tag tag--kz">{signal.killzone.replace("_", " ")}</span>
        )}
        <span className={`tag tag--${status}`}>{status}</span>
        {signal.analysis?.bias && (
          <span className="signal-card__bias">AI: {signal.analysis.bias}</span>
        )}
      </div>

      <div className="signal-card__levels mono">
        <div>
          <span className="signal-card__label">Entry</span>
          <strong>{fmtPrice(signal.entry)}</strong>
        </div>
        <div>
          <span className="signal-card__label">Stop</span>
          <strong>{fmtPrice(signal.sl)}</strong>
        </div>
        <div>
          <span className="signal-card__label">Target</span>
          <strong>{fmtPrice(signal.tp)}</strong>
        </div>
        <div>
          <span className="signal-card__label">R:R</span>
          <strong>{rr.toFixed(1)}</strong>
        </div>
      </div>

      {signal.one_liner && (
        <p className="signal-card__oneliner">{signal.one_liner}</p>
      )}

      <div className="signal-card__foot">
        <span className="muted">{signal.session} session</span>
        <span className="muted">{fmtRelative(signal.created_at)}</span>
        <span className="signal-card__conf mono">
          {Math.round(signal.confidence)}/100
        </span>
      </div>

      <style>{`
        .signal-card {
          text-decoration: none;
          color: inherit;
        }
        .signal-card:hover {
          text-decoration: none;
        }
        .signal-card__head {
          display: flex;
          align-items: center;
          gap: var(--space-xs);
          flex-wrap: wrap;
        }
        .signal-card__bias {
          font-size: 12px;
          color: var(--color-ink-muted-48);
          margin-left: auto;
        }
        .signal-card__levels {
          display: grid;
          grid-template-columns: repeat(4, 1fr);
          gap: var(--space-sm);
          margin-top: var(--space-xs);
        }
        .signal-card__levels > div {
          display: flex;
          flex-direction: column;
          gap: 2px;
        }
        .signal-card__label {
          font-size: 11px;
          text-transform: uppercase;
          letter-spacing: 0.04em;
          color: var(--color-ink-muted-48);
          font-weight: 600;
        }
        .signal-card__levels strong {
          font-size: 17px;
          font-weight: 600;
          color: var(--color-ink);
        }
        .signal-card__oneliner {
          font-size: 14px;
          color: var(--color-ink-muted-80);
          margin: 0;
          line-height: 1.4;
          display: -webkit-box;
          -webkit-line-clamp: 2;
          -webkit-box-orient: vertical;
          overflow: hidden;
        }
        .signal-card__foot {
          display: flex;
          align-items: center;
          gap: var(--space-sm);
          font-size: 12px;
          margin-top: auto;
        }
        .signal-card__conf {
          margin-left: auto;
          font-weight: 600;
          color: var(--color-primary);
        }
      `}</style>
    </Link>
  );
}
