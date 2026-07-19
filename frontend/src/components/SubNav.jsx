import React from "react";

const TIMEFRAMES = ["5min", "15min", "1h", "4h"];
const SYMBOLS = ["XAU/USD", "BTC/USD"];

const TF_LABEL = { "5min": "5m", "15min": "15m", "1h": "1h", "4h": "4h" };
const SYM_LABEL = { "XAU/USD": "Gold", "BTC/USD": "BTC" };

// Frosted parchment sub-nav (per Style.md `sub-nav-frosted`).
export default function SubNav({
  price,
  health,
  onScan,
  scanning,
  timeframe = "5min",
  onTimeframe,
  symbol = "XAU/USD",
  onSymbol,
}) {
  const timeframes = health?.timeframes?.length ? health.timeframes : TIMEFRAMES;
  const symbols = health?.symbols?.length ? health.symbols : SYMBOLS;
  return (
    <div className="subnav">
      <div className="subnav__inner">
        <div className="subnav__left">
          {onSymbol ? (
            <div className="sym-toggle" role="group" aria-label="Symbol">
              {symbols.map((sym) => (
                <button
                  key={sym}
                  className={`sym-toggle__btn ${sym === symbol ? "sym-toggle__btn--active" : ""}`}
                  onClick={() => onSymbol(sym)}
                  aria-pressed={sym === symbol}
                  title={sym}
                >
                  {SYM_LABEL[sym] || sym}
                </button>
              ))}
            </div>
          ) : (
            <span className="subnav__category">{(symbol || "").replace("/", "")}</span>
          )}
          {onTimeframe ? (
            <div className="tf-toggle" role="group" aria-label="Timeframe">
              {timeframes.map((tf) => (
                <button
                  key={tf}
                  className={`tf-toggle__btn ${tf === timeframe ? "tf-toggle__btn--active" : ""}`}
                  onClick={() => onTimeframe(tf)}
                  aria-pressed={tf === timeframe}
                >
                  {TF_LABEL[tf] || tf}
                </button>
              ))}
            </div>
          ) : (
            <span className="subnav__meta">· CRT</span>
          )}
        </div>
        <div className="subnav__right">
          {price != null && (
            <span className="subnav__price mono">
              ${price.toFixed(2)}
            </span>
          )}
          {health && (
            <span
              className={`subnav__status ${
                health.provider ? "subnav__status--ok" : "subnav__status--warn"
              }`}
              title={
                health.provider
                  ? "Live data connected"
                  : "Twelve Data key not set"
              }
            >
              {health.provider ? "Live" : "No key"}
            </span>
          )}
          <button
            className="subnav__scan-btn"
            onClick={onScan}
            disabled={scanning}
          >
            {scanning ? "Scanning…" : "Scan now"}
          </button>
        </div>
      </div>
      <style>{`
        .subnav {
          position: sticky;
          top: var(--nav-height);
          z-index: 90;
          height: var(--subnav-height);
          background: rgba(245, 245, 247, 0.8);
          backdrop-filter: saturate(180%) blur(20px);
          -webkit-backdrop-filter: saturate(180%) blur(20px);
          border-bottom: 1px solid rgba(0, 0, 0, 0.04);
        }
        .subnav__inner {
          max-width: var(--grid-max);
          margin: 0 auto;
          padding: 0 var(--space-lg);
          height: 100%;
          display: flex;
          align-items: center;
          justify-content: space-between;
        }
        .subnav__left {
          display: flex;
          align-items: baseline;
          gap: var(--space-xs);
        }
        .subnav__category {
          font-size: 21px;
          font-weight: 600;
          letter-spacing: -0.01em;
          color: var(--color-ink);
        }
        .subnav__meta {
          font-size: 17px;
          color: var(--color-ink-muted-48);
        }
        .sym-toggle {
          display: inline-flex;
          align-items: center;
          background: rgba(0, 0, 0, 0.05);
          border-radius: var(--radius-pill);
          padding: 2px;
          gap: 2px;
          margin-right: var(--space-xs);
        }
        .sym-toggle__btn {
          background: transparent;
          border: none;
          color: var(--color-ink-muted-80);
          font-size: 12px;
          font-weight: 600;
          letter-spacing: -0.01em;
          padding: 4px 14px;
          border-radius: var(--radius-pill);
          cursor: pointer;
          transition: background 0.12s ease, color 0.12s ease, transform 0.1s ease;
          font-family: inherit;
        }
        .sym-toggle__btn:hover { color: var(--color-ink); }
        .sym-toggle__btn--active {
          background: var(--color-ink);
          color: #fff;
        }
        .sym-toggle__btn:active { transform: scale(0.96); }
        .tf-toggle {
          display: inline-flex;
          align-items: center;
          background: rgba(0, 0, 0, 0.05);
          border-radius: var(--radius-pill);
          padding: 2px;
          gap: 2px;
        }
        .tf-toggle__btn {
          background: transparent;
          border: none;
          color: var(--color-ink-muted-80);
          font-size: 12px;
          font-weight: 600;
          letter-spacing: -0.01em;
          padding: 4px 12px;
          border-radius: var(--radius-pill);
          cursor: pointer;
          transition: background 0.12s ease, color 0.12s ease, transform 0.1s ease;
          font-family: inherit;
        }
        .tf-toggle__btn:hover {
          color: var(--color-ink);
        }
        .tf-toggle__btn--active {
          background: var(--color-canvas);
          color: var(--color-primary);
          box-shadow: 0 1px 3px rgba(0, 0, 0, 0.08);
        }
        .tf-toggle__btn:active {
          transform: scale(0.96);
        }
        .subnav__right {
          display: flex;
          align-items: center;
          gap: var(--space-md);
        }
        .subnav__price {
          font-size: 17px;
          font-weight: 600;
          color: var(--color-ink);
        }
        .subnav__status {
          font-size: 12px;
          font-weight: 600;
          padding: 3px 10px;
          border-radius: var(--radius-pill);
        }
        .subnav__status--ok {
          background: rgba(26, 143, 58, 0.12);
          color: var(--color-long);
        }
        .subnav__status--warn {
          background: rgba(194, 54, 75, 0.12);
          color: var(--color-short);
        }
        .subnav__scan-btn {
          background: var(--color-primary);
          color: #fff;
          border: none;
          border-radius: var(--radius-pill);
          padding: 7px 16px;
          font-size: 14px;
          font-family: var(--font-text);
          transition: transform 0.1s ease;
        }
        .subnav__scan-btn:active:not(:disabled) {
          transform: scale(0.95);
        }
        .subnav__scan-btn:disabled {
          opacity: 0.6;
          cursor: default;
        }
        @media (max-width: 640px) {
          .subnav__meta { display: none; }
        }
      `}</style>
    </div>
  );
}
