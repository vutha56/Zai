// Small formatting helpers shared across components.

export function fmtPrice(n) {
  if (n == null || Number.isNaN(n)) return "—";
  return Number(n).toFixed(2);
}

export function fmtTime(iso) {
  if (!iso) return "";
  const d = new Date(iso);
  return d.toLocaleString(undefined, {
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

export function fmtRelative(iso) {
  if (!iso) return "";
  const then = new Date(iso).getTime();
  const now = Date.now();
  const mins = Math.round((now - then) / 60000);
  if (mins < 1) return "just now";
  if (mins < 60) return `${mins}m ago`;
  const hrs = Math.round(mins / 60);
  if (hrs < 24) return `${hrs}h ago`;
  return `${Math.round(hrs / 24)}d ago`;
}

export function rrOf(entry, sl, tp) {
  const risk = Math.abs(entry - sl);
  if (!risk) return 0;
  return Math.abs(tp - entry) / risk;
}
