import React, { useEffect, useState, useMemo } from "react";
import GlobalNav from "../components/GlobalNav";
import SubNav from "../components/SubNav";
import { Link } from "react-router-dom";
import { api } from "../api";
import { fmtPrice, fmtTime, fmtRelative, rrOf } from "../components/helpers";

// Signal history — focused on resolved outcomes (TP hit / SL hit / expired).
const STATUS_META = {
  win:     { label: "TP hit",   tone: "good", icon: "✓", desc: "Take profit reached" },
  loss:    { label: "SL hit",   tone: "bad",  icon: "✕", desc: "Stop loss hit" },
  expired: { label: "Expired",  tone: "meh",  icon: "—", desc: "Neither TP nor SL within window" },
  open:    { label: "Open",     tone: "live", icon: "•", desc: "Awaiting outcome" },
};

export default function History() {
  const [health, setHealth] = useState(null);
  const [signals, setSignals] = useState([]);
  const [filter, setFilter] = useState("closed"); // all | closed | win | loss | expired | open
  const [symbol, setSymbol] = useState("XAU/USD");
  const [loading, setLoading] = useState(true);

  const refresh = async () => {
    setLoading(true);
    try {
      const h = await api.health();
      setHealth(h);
      // "closed" = resolved (win/loss/expired). We fetch a larger pool then filter client-side
      // so the status chips can slice it without extra round-trips.
      const all = await api.signals(undefined, 200, undefined, symbol);
      setSignals(all);
    } catch {
      /* ignore */
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { refresh(); /* eslint-disable-next-line */ }, [symbol]);

  const filtered = useMemo(() => {
    if (filter === "all") return signals;
    if (filter === "closed") return signals.filter((s) => s.outcome);
    if (filter === "open") return signals.filter((s) => s.status === "open");
    return signals.filter((s) => s.outcome?.result === filter);
  }, [signals, filter]);

  // summary stats across resolved (closed) signals
  const stats = useMemo(() => {
    const closed = signals.filter((s) => s.outcome);
    const tp = closed.filter((s) => s.outcome.result === "win");
    const sl = closed.filter((s) => s.outcome.result === "loss");
    const exp = closed.filter((s) => s.outcome.result === "expired");
    const decided = tp.length + sl.length;
    const totalR = closed.reduce((a, s) => a + (s.outcome.r_multiple || 0), 0);
    return {
      total: closed.length, tp: tp.length, sl: sl.length, expired: exp.length,
      open: signals.filter((s) => s.status === "open").length,
      winRate: decided ? Math.round((tp.length / decided) * 100) : 0,
      totalR: +totalR.toFixed(2),
    };
  }, [signals]);

  return (
    <>
      <GlobalNav />
      <SubNav
        health={health}
        symbol={symbol}
        onSymbol={setSymbol}
      />

      <section className="tile tile--dark hist-hero">
        <div className="tile__inner hist-hero__inner">
          <p className="eyebrow eyebrow--dark">Signal History</p>
          <h1 className="hist-hero__title">TP &amp; SL outcomes</h1>
          <p className="hist-hero__sub">
            Every closed signal resolved against live candles — did it hit take profit or stop loss?
          </p>

          <div className="hist-statgrid">
            <HeroStat label="TP hit" value={stats.tp} tone="good" />
            <HeroStat label="SL hit" value={stats.sl} tone="bad" />
            <HeroStat label="Expired" value={stats.expired} tone="meh" />
            <HeroStat label="Win rate" value={`${stats.winRate}%`} tone={stats.winRate >= 50 ? "good" : "bad"} />
            <HeroStat label="Total R" value={`${stats.totalR >= 0 ? "+" : ""}${stats.totalR}R`} tone={stats.totalR >= 0 ? "good" : "bad"} />
            <HeroStat label="Still open" value={stats.open} tone="live" />
          </div>
        </div>
        <HistHeroStyles />
      </section>

      <section className="tile tile--parchment">
        <div className="tile__inner hist-list-inner">
          <div className="hist-filterbar">
            {[
              ["closed", `Closed (${stats.total})`],
              ["win", `TP hit (${stats.tp})`],
              ["loss", `SL hit (${stats.sl})`],
              ["expired", `Expired (${stats.expired})`],
              ["open", `Open (${stats.open})`],
              ["all", `All (${signals.length})`],
            ].map(([key, label]) => (
              <button
                key={key}
                className={`hist-filter ${filter === key ? "hist-filter--active" : ""}`}
                onClick={() => setFilter(key)}
              >
                {label}
              </button>
            ))}
          </div>

          {loading ? (
            <p className="muted hist-empty">Loading…</p>
          ) : filtered.length === 0 ? (
            <div className="hist-empty">
              <p className="hist-empty__title">No signals in this view yet</p>
              <p className="muted">
                The scanner resolves outcomes as candles close. Closed signals will
                accumulate here automatically — run a <strong>Scan now</strong> to
                backfill, or wait for the daily resolution job.
              </p>
            </div>
          ) : (
            <div className="hist-table">
              <div className="hist-table__head">
                <span>Outcome</span><span>Signal</span><span>Entry / SL / TP</span>
                <span>Hit price</span><span>R</span><span>Symbol · TF</span><span>When</span>
              </div>
              {filtered.map((s) => {
                const meta = STATUS_META[s.outcome?.result || s.status] || STATUS_META.open;
                return (
                  <Link to={`/signal/${s.id}`} key={s.id} className={`hist-row hist-row--${meta.tone}`}>
                    <span className={`hist-outcome hist-outcome--${meta.tone}`}>
                      <span className="hist-outcome__icon">{meta.icon}</span>
                      <span>{meta.label}</span>
                    </span>
                    <span className="hist-sig">
                      <span className={`tag ${s.direction === "LONG" ? "tag--long" : "tag--short"}`}>
                        {s.direction === "LONG" ? "▲ Long" : "▼ Short"}
                      </span>
                      <span className="muted hist-sig__conf">{Math.round(s.confidence)}/100</span>
                    </span>
                    <span className="mono hist-levels">
                      <span>E {fmtPrice(s.entry)}</span>
                      <span className="hist-level--sl">SL {fmtPrice(s.sl)}</span>
                      <span className="hist-level--tp">TP {fmtPrice(s.tp)}</span>
                    </span>
                    <span className="mono hist-hit">
                      {s.outcome?.hit_price ? fmtPrice(s.outcome.hit_price) : "—"}
                    </span>
                    <span className={`mono hist-r hist-r--${(s.outcome?.r_multiple ?? 0) >= 0 ? "pos" : "neg"}`}>
                      {s.outcome ? `${s.outcome.r_multiple >= 0 ? "+" : ""}${s.outcome.r_multiple}R` : "—"}
                    </span>
                    <span className="hist-symtf">
                      <strong>{(s.symbol || "").replace("/", "")}</strong>
                      <span className="muted">{s.timeframe}</span>
                    </span>
                    <span className="muted hist-when" title={s.outcome?.resolved_at ? fmtTime(s.outcome.resolved_at) : fmtTime(s.created_at)}>
                      {s.outcome?.resolved_at ? fmtRelative(s.outcome.resolved_at) : fmtRelative(s.created_at)}
                    </span>
                  </Link>
                );
              })}
            </div>
          )}
        </div>
        <HistListStyles />
      </section>

      <p className="hist-foot">
        Outcomes resolve when a follow-on candle touches TP or SL. Same-candle ambiguous
        hits are scored as a loss (conservative). Neither hit within the look-forward
        window = Expired.
      </p>
    </>
  );
}

function HeroStat({ label, value, tone }) {
  return (
    <div className={`hist-hero__stat hist-hero__stat--${tone}`}>
      <span className="hist-hero__stat-label">{label}</span>
      <strong className="hist-hero__stat-value mono">{value}</strong>
    </div>
  );
}

function HistHeroStyles() {
  return (
    <style>{`
      .hist-hero__inner { text-align: center; align-items: center; max-width: var(--grid-max); }
      .eyebrow--dark { color: var(--color-primary-on-dark); }
      .hist-hero__title { font-size: 48px; line-height: 1.07; letter-spacing: -0.028em; margin-top: var(--space-xs); }
      .hist-hero__sub { font-size: 21px; color: var(--color-body-muted); margin: var(--space-sm) 0 var(--space-lg); max-width: 580px; }
      .hist-statgrid { display: grid; grid-template-columns: repeat(6, 1fr); gap: var(--space-sm); width: 100%; max-width: 900px; }
      .hist-hero__stat { background: var(--color-surface-tile-2); border-radius: var(--radius-md); padding: var(--space-sm) var(--space-md); display: flex; flex-direction: column; gap: 4px; align-items: flex-start; }
      .hist-hero__stat-label { font-size: 11px; text-transform: uppercase; letter-spacing: 0.04em; color: var(--color-body-muted); font-weight: 600; }
      .hist-hero__stat-value { font-size: 26px; font-weight: 600; color: var(--color-body-on-dark); }
      .hist-hero__stat--good .hist-hero__stat-value { color: #34c759; }
      .hist-hero__stat--bad .hist-hero__stat-value { color: #ff453a; }
      .hist-hero__stat--meh .hist-hero__stat-value { color: var(--color-body-muted); }
      .hist-hero__stat--live .hist-hero__stat-value { color: var(--color-primary-on-dark); }
      @media (max-width: 734px) { .hist-hero__title { font-size: 32px; } .hist-statgrid { grid-template-columns: repeat(3, 1fr); } }
    `}</style>
  );
}

function HistListStyles() {
  return (
    <style>{`
      .hist-list-inner { max-width: var(--grid-max); text-align: left; }
      .hist-filterbar { display: flex; gap: var(--space-xs); flex-wrap: wrap; margin-bottom: var(--space-lg); }
      .hist-filter { background: var(--color-canvas); border: 1px solid var(--color-hairline); color: var(--color-ink-muted-80); padding: 7px 16px; border-radius: var(--radius-pill); font-size: 13px; font-weight: 600; cursor: pointer; font-family: inherit; transition: all 0.12s ease; }
      .hist-filter:hover { color: var(--color-ink); }
      .hist-filter--active { background: var(--color-primary); color: #fff; border-color: var(--color-primary); }
      .hist-empty { text-align: center; padding: var(--space-xxl) var(--space-md); }
      .hist-empty__title { font-size: 18px; font-weight: 600; margin: 0 0 var(--space-sm); color: var(--color-ink); }
      .hist-table { background: var(--color-canvas); border: 1px solid var(--color-hairline); border-radius: var(--radius-lg); overflow: hidden; }
      .hist-table__head, .hist-row { display: grid; grid-template-columns: 130px 130px 1fr 110px 70px 110px 90px; align-items: center; gap: var(--space-sm); padding: 10px var(--space-md); }
      .hist-table__head { background: var(--color-canvas-parchment); font-size: 11px; text-transform: uppercase; letter-spacing: 0.04em; color: var(--color-ink-muted-48); font-weight: 600; border-bottom: 1px solid var(--color-hairline); }
      .hist-row { text-decoration: none; color: inherit; border-bottom: 1px solid var(--color-divider-soft); transition: background 0.1s ease; }
      .hist-row:last-child { border-bottom: none; }
      .hist-row:hover { background: var(--color-canvas-parchment); text-decoration: none; }
      .hist-outcome { display: inline-flex; align-items: center; gap: 6px; font-size: 13px; font-weight: 600; padding: 4px 10px; border-radius: var(--radius-pill); width: fit-content; }
      .hist-outcome__icon { font-size: 14px; }
      .hist-outcome--good { background: rgba(26,143,58,0.14); color: var(--color-long); }
      .hist-outcome--bad { background: rgba(194,54,75,0.14); color: var(--color-short); }
      .hist-outcome--meh { background: var(--color-divider-soft); color: var(--color-ink-muted-48); }
      .hist-outcome--live { background: rgba(0,102,204,0.12); color: var(--color-primary); }
      .hist-sig { display: flex; align-items: center; gap: var(--space-xs); }
      .hist-sig__conf { font-size: 12px; }
      .hist-levels { display: flex; flex-direction: column; gap: 2px; font-size: 13px; }
      .hist-level--sl { color: var(--color-short); }
      .hist-level--tp { color: var(--color-long); }
      .hist-hit { font-size: 14px; font-weight: 600; }
      .hist-r { font-size: 16px; font-weight: 700; }
      .hist-r--pos { color: var(--color-long); }
      .hist-r--neg { color: var(--color-short); }
      .hist-symtf { display: flex; flex-direction: column; font-size: 13px; }
      .hist-symtf .muted { font-size: 11px; }
      .hist-when { font-size: 12px; }
      .hist-foot { padding: var(--space-lg); text-align: center; color: var(--color-ink-muted-48); font-size: 12px; max-width: 700px; margin: 0 auto; line-height: 1.5; }
      @media (max-width: 1068px) {
        .hist-table__head { display: none; }
        .hist-row { grid-template-columns: 1fr 1fr; gap: var(--space-xs); padding: var(--space-md); }
        .hist-levels { grid-column: 1 / -1; flex-direction: row; flex-wrap: wrap; gap: var(--space-sm); }
      }
    `}</style>
  );
}
