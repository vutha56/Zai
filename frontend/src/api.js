// Thin fetch wrapper for the backend API.
const BASE = "/api";

async function get(path, params) {
  const url = new URL(`${BASE}${path}`, window.location.origin);
  if (params) {
    Object.entries(params).forEach(([k, v]) => {
      if (v !== undefined && v !== null) url.searchParams.set(k, v);
    });
  }
  const resp = await fetch(url);
  if (!resp.ok) throw new Error(`${resp.status} ${resp.statusText} on ${path}`);
  return resp.json();
}

async function post(path, body) {
  const opts = { method: "POST" };
  if (body !== undefined) {
    opts.headers = { "Content-Type": "application/json" };
    opts.body = JSON.stringify(body);
  }
  const resp = await fetch(`${BASE}${path}`, opts);
  if (!resp.ok) throw new Error(`${resp.status} ${resp.statusText} on ${path}`);
  return resp.json();
}

export const api = {
  health: () => get("/health"),
  candles: (limit = 200, timeframe = "5min", symbol = "XAU/USD") =>
    get("/candles", { limit, timeframe, symbol }),
  smc: (limit = 300, timeframe = "5min", symbol = "XAU/USD") =>
    get("/smc", { limit, timeframe, symbol }),
  context: (limit = 300, timeframe = "5min", symbol = "XAU/USD") =>
    get("/context", { limit, timeframe, symbol }),
  quote: (symbol = "XAU/USD") => get("/quote", { symbol }),
  signals: (status, limit = 50, timeframe, symbol) =>
    get("/signals", { status, limit, timeframe, symbol }),
  signal: (id) => get(`/signals/${id}`),
  performance: () => get("/performance"),
  scan: (timeframe, symbol) =>
    post(
      timeframe || symbol
        ? `/scan?${[
            timeframe ? `timeframe=${timeframe}` : "",
            symbol ? `symbol=${encodeURIComponent(symbol)}` : "",
          ]
            .filter(Boolean)
            .join("&")}`
        : "/scan"
    ),
  analyze: (id) => post(`/signals/${id}/analyze`),
  backtestOptions: () => get("/backtest/options"),
  backtest: (config) => post("/backtest", config),
};

// SSE event stream for live signals
export function subscribeEvents(onEvent) {
  const es = new EventSource(`${BASE}/events`);
  es.addEventListener("message", (e) => {
    try {
      onEvent(JSON.parse(e.data));
    } catch {
      /* ignore malformed */
    }
  });
  es.addEventListener("ping", () => {});
  return es;
}
