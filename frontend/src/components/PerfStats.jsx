import React from "react";

// Performance summary tile — win rates, avg R, narrative feedback.
export default function PerfStats({ perf }) {
  const bySession = perf.by_session || {};
  const byDir = perf.by_direction || {};
  const sessionRows = Object.entries(bySession).sort(
    (a, b) => b[1].win_rate - a[1].win_rate
  );

  return (
    <section className="tile tile--parchment">
      <div className="tile__inner perf">
        <p className="eyebrow">Strategy Performance</p>
        <h2 className="perf__title">How the CRT engine is doing</h2>
        <p className="perf__sub">
          Tracked outcomes from live signals — fed back into every new AI analysis.
        </p>

        <div className="perf__grid">
          <Stat
            label="Win rate (last 20)"
            value={`${(perf.win_rate_20 ?? 0).toFixed(1)}%`}
          />
          <Stat
            label="Win rate (last 50)"
            value={`${(perf.win_rate_50 ?? 0).toFixed(1)}%`}
          />
          <Stat
            label="Avg R-multiple"
            value={`${(perf.avg_r ?? 0) >= 0 ? "+" : ""}${(perf.avg_r ?? 0).toFixed(2)}R`}
            tone={(perf.avg_r ?? 0) >= 0 ? "good" : "bad"}
          />
          <Stat label="Resolved setups" value={perf.sample_size ?? 0} />
        </div>

        {sessionRows.length > 0 && (
          <div className="perf__breakdown">
            <h3 className="perf__h3">By session</h3>
            <div className="perf__bars">
              {sessionRows.map(([name, s]) => (
                <Bar key={name} label={name} pct={s.win_rate} n={s.n} />
              ))}
            </div>
            {byDir.LONG || byDir.SHORT ? (
              <>
                <h3 className="perf__h3">By direction</h3>
                <div className="perf__bars">
                  {byDir.LONG && (
                    <Bar label="Long" pct={byDir.LONG.win_rate} n={byDir.LONG.n} />
                  )}
                  {byDir.SHORT && (
                    <Bar label="Short" pct={byDir.SHORT.win_rate} n={byDir.SHORT.n} />
                  )}
                </div>
              </>
            ) : null}
          </div>
        )}

        {perf.narrative && (
          <blockquote className="perf__narrative">{perf.narrative}</blockquote>
        )}
      </div>
      <PerfStyles />
    </section>
  );
}

function Stat({ label, value, tone }) {
  return (
    <div className={`perf__stat ${tone ? `perf__stat--${tone}` : ""}`}>
      <span className="perf__stat-label">{label}</span>
      <strong className="perf__stat-value mono">{value}</strong>
    </div>
  );
}

function Bar({ label, pct, n }) {
  const width = Math.max(2, Math.min(100, pct));
  return (
    <div className="perf__bar">
      <div className="perf__bar-head">
        <span>{label}</span>
        <span className="perf__bar-pct mono">
          {pct.toFixed(0)}% · n{n}
        </span>
      </div>
      <div className="perf__bar-track">
        <div
          className={`perf__bar-fill ${pct >= 50 ? "good" : "bad"}`}
          style={{ width: `${width}%` }}
        />
      </div>
    </div>
  );
}

function PerfStyles() {
  return (
    <style>{`
      .perf { max-width: var(--content-max); text-align: center; align-items: center; }
      .perf__title {
        font-size: 40px; line-height: 1.1; letter-spacing: -0.02em;
        margin-top: var(--space-xs);
      }
      .perf__sub {
        font-size: 21px; color: var(--color-ink-muted-48); margin: var(--space-sm) 0 var(--space-lg);
      }
      .perf__grid {
        display: grid; grid-template-columns: repeat(4, 1fr); gap: var(--space-sm);
        width: 100%; margin-bottom: var(--space-lg);
      }
      .perf__stat {
        background: var(--color-canvas); border: 1px solid var(--color-hairline);
        border-radius: var(--radius-lg); padding: var(--space-md);
        display: flex; flex-direction: column; gap: 6px; align-items: flex-start;
      }
      .perf__stat-label {
        font-size: 12px; text-transform: uppercase; letter-spacing: 0.04em;
        color: var(--color-ink-muted-48); font-weight: 600;
      }
      .perf__stat-value { font-size: 28px; font-weight: 600; color: var(--color-ink); }
      .perf__stat--good .perf__stat-value { color: var(--color-long); }
      .perf__stat--bad .perf__stat-value { color: var(--color-short); }
      .perf__breakdown { width: 100%; text-align: left; margin-top: var(--space-md); }
      .perf__h3 { font-size: 14px; text-transform: uppercase; letter-spacing: 0.04em; color: var(--color-ink-muted-48); margin: var(--space-lg) 0 var(--space-sm); }
      .perf__bars { display: flex; flex-direction: column; gap: var(--space-xs); }
      .perf__bar { width: 100%; }
      .perf__bar-head { display: flex; justify-content: space-between; font-size: 14px; margin-bottom: 4px; color: var(--color-ink-muted-80); }
      .perf__bar-pct { font-weight: 600; color: var(--color-ink); }
      .perf__bar-track { height: 8px; background: var(--color-divider-soft); border-radius: var(--radius-pill); overflow: hidden; }
      .perf__bar-fill { height: 100%; border-radius: var(--radius-pill); }
      .perf__bar-fill.good { background: var(--color-long); }
      .perf__bar-fill.bad { background: var(--color-short); }
      .perf__narrative {
        margin: var(--space-lg) 0 0; padding: var(--space-lg);
        background: var(--color-canvas); border: 1px solid var(--color-hairline);
        border-radius: var(--radius-lg); font-size: 17px; line-height: 1.5;
        color: var(--color-ink-muted-80); text-align: left; width: 100%;
        font-style: italic;
      }
      @media (max-width: 734px) {
        .perf__title { font-size: 32px; }
        .perf__grid { grid-template-columns: repeat(2, 1fr); }
      }
    `}</style>
  );
}
