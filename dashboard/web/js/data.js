export const Q = 900000;
export const HOUR = 3600000;

// Formatting of times in the chosen time zone
export function fmt(ms, tz, opts) {
  return new Intl.DateTimeFormat("en-GB", { timeZone: tz, ...opts }).format(new Date(ms));
}
export const fmtTime = (ms, tz) => fmt(ms, tz, { hour: "2-digit", minute: "2-digit", hour12: false });
export const fmtDay = (ms, tz) => fmt(ms, tz, { weekday: "short", day: "numeric", month: "short" });
export const fmtFull = (ms, tz) => `${fmtDay(ms, tz)} ${fmtTime(ms, tz)}`;
export const pct = (p, d = 0) => (p == null || isNaN(p) ? "–" : `${(p * 100).toFixed(d)}%`);
export const eur = (v, d = 0) => (v == null || isNaN(v) ? "–" : `${v.toFixed(d)}`);
export const esc = (s) => String(s).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));

// One loaded data set: forecasts by origin, actual outcomes by quarter-hour and their usable times
export class Dataset {
  constructor(raw, label) {
    this.raw = raw;
    this.label = label;
    this.steps = raw.steps;
    this.origins = raw.origins;
    this.index = new Map(raw.origins.map((o, i) => [o, i]));
    this.actual = raw.actual;
  }

  // Forecast rows for one origin
  rows(i) {
    const f = this.raw.f, out = [], o = this.origins[i];
    for (let s = 0; s < this.steps; s++) {
      const r = i * this.steps + s;
      out.push({
        step: s + 1, t: o + s * Q, p10: f.p10[r], p50: f.p50[r], p90: f.p90[r], up: f.up[r], down: f.down[r], none: f.none[r],
        hi: f.hi[r], lo: f.lo[r], drivers: f.drv[r].map((k) => this.raw.phrases[k]), names: f.names[r],
      });
    }
    return out;
  }

  alerts(i) { return this.raw.alerts[i] || []; }
  cutoff(i) { return this.raw.cutoffs[i]; }
  period(i) { return (this.raw.meta.periods || [])[this.raw.period[i]]; }

  // Actual outcome at a quarter-hour, only when it was usable by the given time
  outcome(t, asOf = Infinity) {
    const a = this.actual;
    if (!a) return null;
    const k = Math.round((t - a.t0) / Q);
    if (k < 0 || k >= a.price.length || a.price[k] == null) return null;
    if (a.usable[k] == null || a.usable[k] > asOf) return null;
    return { price: a.price[k], dir: a.dir[k], hi: a.hi[k], lo: a.lo[k], usable: a.usable[k] };
  }

  // Forecast for a delivery made a given number of hours before it, if that origin exists
  aheadRow(t, hours) {
    const origin = Math.floor(t / HOUR) * HOUR - hours * HOUR;
    const i = this.index.get(origin);
    if (i === undefined) return null;
    const s = Math.round((t - origin) / Q);
    if (s < 0 || s >= this.steps) return null;
    return { ...this.rows(i)[s], origin };
  }
}

// Pinball loss at one quantile
const pinball = (y, q, a) => Math.max(a * (y - q), (a - 1) * (y - q));

// Scores of forecasts whose outcomes were usable by asOf, for deliveries in [from, asOf)
export function scoreWindow(ds, asOf, from) {
  const m = { n: 0, ae: 0, pin: 0, cover: 0, spike: 0, dir: 0, byStep: Array.from({ length: ds.steps }, () => [0, 0]) };
  for (let i = 0; i < ds.origins.length; i++) {
    const o = ds.origins[i];
    if (o >= asOf || o + ds.steps * Q <= from) continue;
    const rows = ds.rows(i);
    for (const r of rows) {
      if (r.t < from) continue;
      const a = ds.outcome(r.t, asOf);
      if (!a) continue;
      const y = a.price;
      m.n++;
      m.ae += Math.abs(y - r.p50);
      m.pin += (pinball(y, r.p10, 0.1) + pinball(y, r.p90, 0.9)) / 2;
      m.cover += y >= r.p10 && y <= r.p90 ? 1 : 0;
      m.spike += ((r.hi - a.hi) ** 2 + (r.lo - a.lo) ** 2) / 2;
      const up = a.dir === 1 ? 1 : 0, dn = a.dir === -1 ? 1 : 0, no = a.dir === 0 ? 1 : 0;
      m.dir += (r.up - up) ** 2 + (r.down - dn) ** 2 + (r.none - no) ** 2;
      m.byStep[r.step - 1][0] += Math.abs(y - r.p50);
      m.byStep[r.step - 1][1] += 1;
    }
  }
  if (!m.n) return null;
  return {
    n: m.n, mae: m.ae / m.n, pinball: m.pin / m.n, coverage: m.cover / m.n, spike: m.spike / m.n, direction: m.dir / m.n,
    maeByHour: Array.from({ length: ds.steps / 4 }, (_, h) => {
      const s = m.byStep.slice(h * 4, h * 4 + 4);
      const n = s.reduce((a, b) => a + b[1], 0);
      return n ? s.reduce((a, b) => a + b[0], 0) / n : null;
    }),
  };
}

// The first alert of each distinct event among origins in [from, asOf], with what followed
export function alertHistory(ds, asOf, from) {
  const seen = new Map();
  for (let i = 0; i < ds.origins.length; i++) {
    const o = ds.origins[i];
    if (o < from || o > asOf) continue;
    for (const a of ds.alerts(i)) {
      const key = `${a.kind}:${Math.floor(a.start / (2 * HOUR))}`;
      if (!seen.has(key)) seen.set(key, { ...a, origin: o });
    }
  }
  const out = [];
  for (const a of seen.values()) {
    let known = 0, events = 0, peakPrice = null;
    for (let t = a.start; t < a.end; t += Q) {
      const x = ds.outcome(t, asOf);
      if (!x) continue;
      known++;
      if (a.kind === "spike_high" && x.hi) events++;
      if (a.kind === "spike_low" && x.lo) events++;
      if ((a.kind === "direction_up" || a.kind === "conflict") && x.dir === 1) events++;
      peakPrice = peakPrice == null ? x.price : Math.max(peakPrice, x.price);
    }
    out.push({ ...a, known, events, peakPrice });
  }
  return out.sort((a, b) => b.start - a.start);
}
