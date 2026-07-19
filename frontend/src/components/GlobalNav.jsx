import React from "react";
import { Link, useLocation } from "react-router-dom";

// Black 44px global nav bar (per Style.md `global-nav`).
export default function GlobalNav() {
  const { pathname } = useLocation();
  return (
    <nav className="global-nav">
      <div className="global-nav__inner">
        <span className="global-nav__brand">◆ CRT</span>
        <Link to="/" className={`global-nav__link ${pathname === "/" ? "global-nav__link--active" : ""}`}>
          Signals
        </Link>
        <Link to="/history" className={`global-nav__link ${pathname === "/history" ? "global-nav__link--active" : ""}`}>
          History
        </Link>
        <Link to="/backtest" className={`global-nav__link ${pathname === "/backtest" ? "global-nav__link--active" : ""}`}>
          Backtest
        </Link>
        <span className="global-nav__spacer" />
        <a
          href="https://z.ai/model-api"
          target="_blank"
          rel="noreferrer"
          className="global-nav__link"
        >
          ZAI GLM
        </a>
      </div>
      <style>{`
        .global-nav {
          position: sticky;
          top: 0;
          z-index: 100;
          height: var(--nav-height);
          background: var(--color-surface-black);
          color: var(--color-body-on-dark);
          display: flex;
          align-items: center;
        }
        .global-nav__inner {
          width: 100%;
          max-width: var(--grid-max);
          margin: 0 auto;
          padding: 0 var(--space-lg);
          display: flex;
          align-items: center;
          gap: var(--space-md);
          font-size: 12px;
          letter-spacing: -0.12px;
        }
        .global-nav__brand {
          font-weight: 600;
          color: var(--color-primary-on-dark);
        }
        .global-nav__title {
          opacity: 0.85;
        }
        .global-nav__spacer {
          flex: 1;
        }
        .global-nav__link {
          color: rgba(255, 255, 255, 0.75);
          text-decoration: none;
          font-weight: 500;
        }
        .global-nav__link:hover { color: #fff; text-decoration: none; }
        .global-nav__link--active { color: var(--color-primary-on-dark); }
        .global-nav__link:hover {
          text-decoration: underline;
        }
      `}</style>
    </nav>
  );
}
