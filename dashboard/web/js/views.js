import { Q, HOUR, fmt, fmtTime, fmtDay, fmtFull, pct, eur, esc, scoreWindow, alertHistory } from "./data.js";
import { priceChart, riskChart, directionChart, trackChart, barChart, heatmap, reliabilityChart, gaugeChart, contextChart, colors, draw } from "./charts.js";

const KIND = {
  spike_high: { name: "Spike risk above spot", icon: "▲", color: "--high" },
  spike_low: { name: "Spike risk below spot", icon: "▼", color: "--low" },
  direction_up: { name: "Up-regulation", icon: "⇡", color: "--up" },
  conflict: { name: "Conflicting signals", icon: "⇄", color: "--warn" },
  moved: { name: "Forecast moved", icon: "↕", color: "--accent" },
  uncertainty: { name: "High uncertainty", icon: "≈", color: "--warn" },
};
const info = (text) => `<span class="info" title="${esc(text)}">i</span>`;
const mix = (v, p) => `color-mix(in srgb, var(${v}) ${Math.round(Math.max(0, Math.min(1, p)) * 100)}%, var(--panel-2))`;

// Hindsight values for the forecast window, only when the user asks for them
function hindsight(ds, rows, show) {
  if (!show) return {};
  const price = rows.map((r) => [r.t, ds.outcome(r.t)?.price ?? null]);
  if (!price.some((p) => p[1] != null)) return {};
  const spikes = rows.filter((r) => { const a = ds.outcome(r.t); return a && (a.hi || a.lo); }).map((r) => [r.t, ds.outcome(r.t).hi ? 1 : -1]);
  const dir = rows.map((r) => ds.outcome(r.t)?.dir ?? null);
  return { price, spikes, dir };
}

// Overall state for the next 10 hours, from the alerts shown
function overall(alerts) {
  const has = (k) => alerts.find((a) => a.kind === k);
  if (has("spike_high")) return { word: "Spike risk above spot", icon: "▲", color: "--high", why: has("spike_high").title };
  if (has("spike_low")) return { word: "Spike risk below spot", icon: "▼", color: "--high", why: has("spike_low").title };
  if (alerts.length) return { word: "Watch", icon: "◎", color: "--warn", why: alerts[0].title };
  return { word: "Calm", icon: "✓", color: "--ok", why: "Nothing unusual in the next 10 hours" };
}

// Colour lanes: one cell per quarter-hour for direction and the two spike risks
function lanes(rows, tz) {
  const cell = (r, bg, tip) => `<i style="background:${bg}" title="${fmtTime(r.t, tz)} · ${tip}"></i>`;
  const lane = (name, cells) => `<div class="lane"><div class="name">${name}</div><div class="cells">${cells}</div></div>`;
  const hi = rows.map((r) => cell(r, mix("--high", r.hi / 0.45), `spike above spot ${pct(r.hi)}`)).join("");
  const lo = rows.map((r) => cell(r, mix("--low", r.lo / 0.55), `spike below spot ${pct(r.lo)}`)).join("");
  const dir = rows.map((r) => cell(r, r.up >= 0.5 ? mix("--up", (r.up - 0.5) * 4) : mix("--down", (0.5 - r.up) * 4),
    `up ${pct(r.up)} · down ${pct(r.down)}`)).join("");
  const hours = Array.from({ length: rows.length / 4 }, (_, h) => `<span>${fmtTime(rows[h * 4].t, tz)}</span>`).join("");
  return `${lane("Direction", dir)}${lane("▲ Spike above", hi)}${lane("▼ Spike below", lo)}
    <div class="hours"><span></span><div>${hours}</div></div>
    <div class="legend"><span style="--c:var(--up)">Up-regulation</span><span style="--c:var(--down)">Down-regulation</span>
    <span style="--c:var(--high)">Spike &gt; 50 € above spot</span><span style="--c:var(--low)">Spike &gt; 50 € below spot</span><span class="hint">Stronger colour = more likely</span></div>`;
}

// One alert: a compact line that opens to the message, drivers and suggestions
function alertCard(a, tz) {
  const k = KIND[a.kind];
  const peak = a.kind === "moved" ? `${eur(a.peak)}<small>€/MWh</small>` : a.kind === "uncertainty" ? `${eur(a.peak)}<small>€ wide</small>` : `${pct(a.peak)}<small>peak</small>`;
  return `<details class="alert" style="--k:var(${k.color})">
    <summary><div class="ico">${k.icon}</div>
      <div><div class="t">${k.name}</div><div class="when">${fmtDay(a.start, tz)} · ${fmtTime(a.start, tz)}–${fmtTime(a.end, tz)}</div></div>
      <div class="peak">${peak}</div></summary>
    <div class="body"><p>${esc(a.message)}</p>
      ${a.drivers?.length ? `<div class="chips">${a.drivers.map((d) => `<span class="chip">${esc(d)}</span>`).join("")}</div>` : ""}
      <ul>${a.review.map((r) => `<li>${esc(r)}</li>`).join("")}</ul></div>
  </details>`;
}

// One quarter-hour of the coming hour: price, range, risks and direction
function quarterCard(r, tz) {
  const dirUp = r.up >= r.down;
  const spot = window.spotAt ? window.spotAt(r.t) : null;
  return `<div class="q">
    <div class="qt">${fmtTime(r.t, tz)}</div>
    <div class="qp">${eur(r.p50)}<small>€/MWh</small></div>
    <div class="qr">P10–P90 ${eur(r.p10)} to ${eur(r.p90)}${spot != null ? ` · spot ${eur(spot)}` : ""}</div>
    <div class="qb">
      <span style="background:${mix("--high", r.hi / 0.45)}" title="Chance of a spike more than 50 €/MWh above spot">▲ ${pct(r.hi)}</span>
      <span style="background:${mix("--low", r.lo / 0.55)}" title="Chance of a spike more than 50 €/MWh below spot">▼ ${pct(r.lo)}</span>
      <span style="background:${mix(dirUp ? "--up" : "--down", Math.abs(r.up - 0.5) * 4)}" title="Regulation direction">${dirUp ? "Up" : "Down"} ${pct(dirUp ? r.up : r.down)}</span>
    </div></div>`;
}

// What is worth checking right now: the coming hour only
export function renderNow(root, ds, i) {
  const tz = window.state.tz, rows = ds.rows(i), origin = ds.origins[i], rates = ds.raw.base_rates, c = colors();
  const hour = rows.slice(0, 4);
  const all = ds.alerts(i);
  const now = all.filter((a) => a.start < origin + HOUR);
  const later = all.filter((a) => a.start >= origin + HOUR);
  const st = now.length ? overall(now) : { word: "Calm", icon: "✓", color: "--ok", why: later.length ? `Next: ${later[0].title}` : "Nothing unusual ahead" };
  const avg = (k) => hour.reduce((a, r) => a + r[k], 0) / hour.length;
  const hi = hour.reduce((a, b) => (b.hi > a.hi ? b : a)), lo = hour.reduce((a, b) => (b.lo > a.lo ? b : a));
  const up = avg("up"), down = avg("down"), none = avg("none");
  const past = [];
  for (let t = origin - 3 * HOUR; t < origin; t += Q) { const a = ds.outcome(t, origin); if (a) past.push([t, a.price]); }
  const recent = past.filter((p) => p[0] >= (past.length ? past[past.length - 1][0] : origin) - 2 * HOUR + Q);
  const lastKnown = past.length ? past[past.length - 1] : null;
  root.innerHTML = `
    <div class="card hero" style="--state:var(${st.color})">
      <div class="state"><div class="badge">${st.icon}</div><div><div class="word">${st.word}</div><div class="why">${esc(st.why)}</div></div></div>
      <div class="quarters">${hour.map((r) => quarterCard(r, tz)).join("")}</div>
    </div>
    <div class="tiles">
      <div class="card tile"><div class="label">Last published price ${info("The most recent actual imbalance price known at this moment. Prices are published with about an hour's delay.")}</div>
        <div class="big">${lastKnown ? eur(lastKnown[1]) : "–"}<small>€/MWh</small></div>
        <div class="foot">${lastKnown ? `for ${fmtTime(lastKnown[0], tz)} · ${Math.round((origin - lastKnown[0]) / 60000)} min ago` : "none published yet"}</div></div>
      <div class="card tile ${hi.hi >= 0.25 ? "accent-high" : ""}"><div class="label">▲ Spike risk above spot ${info("Highest chance this hour that the price is over 50 €/MWh above spot. The tick marks the typical level.")}</div>
        <div class="big">${pct(hi.hi)}</div><div class="foot">highest this hour, at ${fmtTime(hi.t, tz)} · typical ${pct(rates.high)}</div><div class="gauge" id="g-hi"></div></div>
      <div class="card tile ${lo.lo >= 0.35 ? "accent-high" : ""}"><div class="label">▼ Spike risk below spot ${info("Highest chance this hour that the price is over 50 €/MWh below spot.")}</div>
        <div class="big">${pct(lo.lo)}</div><div class="foot">highest this hour, at ${fmtTime(lo.t, tz)} · typical ${pct(rates.low)}</div><div class="gauge" id="g-lo"></div></div>
      <div class="card tile"><div class="label">Regulation this hour ${info("Average p_up, p_down and p_none over the coming hour, as in the forecast file.")}</div>
        <div class="big"><span class="arrow" style="background:${mix(up >= down ? "--up" : "--down", 0.25)};color:var(${up >= down ? "--up" : "--down"})">${up >= down ? "▲" : "▼"}</span>${up >= down ? "Up" : "Down"}</div>
        <div class="meter"><i style="width:${up * 100}%;background:var(--up)"></i><i style="width:${down * 100}%;background:var(--down)"></i><i style="width:${none * 100}%;background:var(--faint)"></i></div>
        <div class="foot">average this hour: up ${pct(up)} · down ${pct(down)} · none ${pct(none, 1)}</div></div>
      <div class="card tile"><div class="label">Uncertainty this hour ${info("Average width of the P10–P90 range for the coming hour. Wider means the model is less sure.")}</div>
        <div class="big">${eur(avg("p90") - avg("p10"))}<small>€ wide</small></div>
        <div class="foot">average width this hour · lowest P10 ${eur(Math.min(...hour.map((r) => r.p10)))}, highest P90 ${eur(Math.max(...hour.map((r) => r.p90)))}</div></div>
    </div>
    <div class="grid split">
      <div class="card"><div class="card-head"><h2>Worth checking now</h2><span class="hint">${now.length ? "tap for details" : ""}</span></div>
        <div class="alerts">${now.length ? now.map((a) => alertCard(a, tz)).join("") :
          `<div class="calm"><div class="badge">✓</div><b>Nothing for the coming hour</b></div>`}</div>
        ${later.length ? `<div class="card-head mt"><h2 class="muted">Later today</h2><button class="btn ghost" id="to-next">Next 10 h →</button></div>
          <div class="alerts">${later.map((a) => alertCard(a, tz)).join("")}</div>` : ""}</div>
      <div class="card"><div class="card-head"><h2>Recent prices → coming hours</h2><span class="hint">last 2 h published · prices appear about an hour late · forecast from now</span></div>
        <div class="chart tall" id="now-ctx"></div></div>
    </div>`;
  gaugeChart(document.getElementById("g-hi"), hi.hi, { color: hi.hi >= 0.25 ? c.high : c.muted, typical: rates.high });
  gaugeChart(document.getElementById("g-lo"), lo.lo, { color: lo.lo >= 0.35 ? c.high : c.muted, typical: rates.low });
  contextChart(document.getElementById("now-ctx"), recent, rows.slice(0, 8), { tz, origin });
  const go = document.getElementById("to-next");
  if (go) go.onclick = () => { window.state.view = "next"; window.render(); };
}

// Hourly heat table: colour carries the numbers, drivers in the tooltip
function hourTable(rows, tz) {
  const out = [];
  for (let h = 0; h < rows.length / 4; h++) {
    const q = rows.slice(h * 4, h * 4 + 4);
    const avg = (k) => q.reduce((a, r) => a + r[k], 0) / q.length;
    const max = (k) => Math.max(...q.map((r) => r[k]));
    const drivers = [...new Set(q.flatMap((r) => r.drivers))].slice(0, 3);
    const up = avg("up");
    out.push(`<tr title="Drivers: ${esc(drivers.join("; "))}"><td>${fmtTime(q[0].t, tz)}</td>
      <td class="num"><b>${eur(avg("p50"))}</b></td>${window.spotAt ? `<td class="num" style="color:var(--spot)">${eur(q.reduce((a, r) => a + (window.spotAt(r.t) ?? 0), 0) / q.length)}</td>` : ""}<td class="num muted">${eur(Math.min(...q.map((r) => r.p10)))} – ${eur(max("p90"))}</td>
      <td class="heat" style="background:${mix("--high", max("hi") / 0.45)}">${pct(max("hi"))}</td>
      <td class="heat" style="background:${mix("--low", max("lo") / 0.55)}">${pct(max("lo"))}</td>
      <td class="heat" style="background:${up >= 0.5 ? mix("--up", (up - 0.5) * 4) : mix("--down", (0.5 - up) * 4)}">${up >= 0.5 ? "▲" : "▼"} ${pct(up >= 0.5 ? up : 1 - up)}</td>
      <td><span class="chip">${esc(drivers[0] || "")}</span></td></tr>`);
  }
  return `<div class="tablewrap"><table><thead><tr><th>Hour</th><th class="num">P50</th>${window.spotAt ? `<th class="num">Spot</th>` : ""}<th class="num">P10–P90</th><th>▲ Spike above</th><th>▼ Spike below</th>
    <th>Direction</th><th>Top driver</th></tr></thead><tbody>${out.join("")}</tbody></table></div>`;
}

// What direction actually happened, one cell per quarter-hour, aligned with the chart
function actualLane(rows, dirs, tz) {
  const name = { 1: "up", "-1": "down", 0: "none" };
  const color = { 1: "var(--up)", "-1": "var(--down)", 0: "var(--faint)" };
  const cells = rows.map((r, k) => `<i style="background:${dirs[k] == null ? "var(--panel-2)" : color[dirs[k]]}" title="${fmtTime(r.t, tz)} · actual: ${dirs[k] == null ? "not known" : name[dirs[k]]}"></i>`).join("");
  return `<div class="lane" style="grid-template-columns:52px 1fr;margin:2px 18px 0 0"><div class="name">Actual</div><div class="cells">${cells}</div></div>`;
}

// The full 10-hour forecast in 15-minute steps
export function renderNext(root, ds, i) {
  const tz = window.state.tz, rows = ds.rows(i), show = window.state.reveal;
  const h = hindsight(ds, rows, show);
  const prevI = ds.index.get(ds.origins[i] - HOUR);
  root.innerHTML = `
    <div class="toolbar">
      <label class="switch"><input type="checkbox" id="reveal" ${show ? "checked" : ""}> Show what happened ${info("Hindsight: adds the real price, spikes and direction that followed. They were not known when the forecast was made.")}</label>
      <label class="switch"><input type="checkbox" id="showprev" ${window.state.showPrev ? "checked" : ""}> Forecast 1 h earlier ${info("The forecast the same model made one hour before, for the same quarter-hours. A big gap means the outlook changed.")}</label>
      <span class="spacer"></span>
      <button class="btn ghost" id="dl">⤓ CSV</button>
    </div>
    <div class="card" style="margin-bottom:14px"><div class="card-head"><h2>Next 10 hours at a glance</h2><span class="hint">hover a cell for its value</span></div>${lanes(rows, tz)}</div>
    <div class="card"><div class="card-head"><h2>Imbalance price</h2><span class="hint">blue: forecast now · shaded: P10–P90 (8 in 10 prices fall inside)${window.spotAt ? " · amber: spot" : ""} · dashed: forecast 1 h earlier</span></div>
      <div class="chart tall" id="next-price"></div></div>
    <div class="grid cols-2 mt">
      <div class="card"><div class="card-head"><h2>Spike risk</h2><span class="hint">chance of a spike more than 50 €/MWh ▲ above or ▼ below spot · dotted: typical</span></div>
        <div class="chart mid" id="next-risk"></div></div>
      <div class="card"><div class="card-head"><h2>Regulation direction</h2><span class="hint">p_up · p_down · p_none, as in the forecast file</span></div>
        <div class="chart mid" id="next-dir"></div>${h.dir ? actualLane(rows, h.dir, tz) : ""}</div>
    </div>
    <div class="card mt"><div class="card-head"><h2>Hour by hour</h2><span class="hint">hover a row for its drivers</span></div>${hourTable(rows, tz)}</div>`;
  priceChart(document.getElementById("next-price"), rows, { tz, actual: h.price, previous: window.state.showPrev && prevI !== undefined ? ds.rows(prevI).filter((r) => r.t >= rows[0].t) : null });
  riskChart(document.getElementById("next-risk"), rows, { tz, base: ds.raw.base_rates, actual: h.spikes });
  directionChart(document.getElementById("next-dir"), rows, { tz });
  document.getElementById("reveal").onchange = (e) => { window.state.reveal = e.target.checked; window.render(); };
  document.getElementById("showprev").onchange = (e) => { window.state.showPrev = e.target.checked; window.render(); };
  document.getElementById("dl").onclick = () => {
    const iso = (t) => new Date(t).toISOString().replace(".000", "");
    const lines = ["forecast_origin_utc,delivery_start_utc,step,p10,p50,p90,p_up,p_down,p_none,p_spike_high,p_spike_low,data_cutoff_utc,top_drivers",
      ...rows.map((r) => [iso(ds.origins[i]), iso(r.t), r.step, r.p10, r.p50, r.p90, r.up, r.down, r.none, r.hi, r.lo, iso(ds.cutoff(i)), r.names.join(";")].join(","))];
    const a = document.createElement("a");
    a.href = URL.createObjectURL(new Blob([lines.join("\n")], { type: "text/csv" }));
    a.download = `forecast_${iso(ds.origins[i]).replace(/[:]/g, "")}.csv`;
    a.click();
  };
}

const WINDOWS = { day: ["Last day", 24], week: ["Last week", 168], month: ["Last month", 720], custom: ["Custom", 0] };

// Midnight in Finnish time for a yyyy-mm-dd date
function finnishMidnight(date) {
  const [y, m, d] = date.split("-").map(Number);
  for (const offset of [3, 2]) {
    const t = Date.UTC(y, m - 1, d) - offset * HOUR;
    if (fmt(t, "Europe/Helsinki", { hour: "2-digit", hour12: false }) % 24 === 0) return t;
  }
  return Date.UTC(y, m - 1, d);
}
const isoDay = (t) => fmt(t, "Europe/Helsinki", { year: "numeric", month: "2-digit", day: "2-digit" }).split("/").reverse().join("-");

// How the forecast performed, using only outcomes known at the selected time
export function renderHindsight(root, ds, i) {
  const tz = window.state.tz, asOf = ds.origins[i], win = window.state.window, c = colors();
  const custom = window.state.custom || { from: isoDay(asOf - 3 * 24 * HOUR), to: isoDay(asOf) };
  const from = win === "custom" ? finnishMidnight(custom.from) : asOf - WINDOWS[win][1] * HOUR;
  const to = win === "custom" ? Math.min(asOf, finnishMidnight(custom.to) + 24 * HOUR) : asOf;
  const s = from < to ? scoreWindow(ds, asOf, from, to) : null;
  const tabs = Object.entries(WINDOWS).map(([k, [label]]) => `<button data-w="${k}" class="${k === win ? "on" : ""}">${label}</button>`).join("");
  const picker = win === "custom" ? `<label class="small muted">From <input type="date" id="c-from" value="${custom.from}" max="${custom.to}"></label>
    <label class="small muted">to <input type="date" id="c-to" value="${custom.to}" min="${custom.from}" max="${isoDay(asOf)}"></label>` : "";
  const head = `<div class="toolbar"><div class="seg" id="win">${tabs}</div>${picker}
    <span class="hint">Only prices published by ${fmtFull(asOf, tz)} ${info("As a user would have seen it then: outcomes published after this time are not used.")}</span></div>`;
  if (!s) {
    root.innerHTML = head + `<div class="card calm"><div class="badge">…</div>No published outcomes yet. Move the time later.</div>`;
  } else {
    const hist = alertHistory(ds, asOf, from, to).filter((a) => ["spike_high", "spike_low", "direction_up"].includes(a.kind)).slice(0, 14);
    const points = [];
    for (let t = Math.max(from, to - 7 * 24 * HOUR); t < to; t += Q) {
      const a = ds.outcome(t, asOf);
      if (!a) continue;
      const f1 = ds.aheadRow(t, 1), f6 = ds.aheadRow(t, 6);
      points.push({ t, y: a.price, p50_1: f1?.p50 ?? null, p10_1: f1?.p10 ?? null, p90_1: f1?.p90 ?? null, p50_6: f6?.p50 ?? null });
    }
    const covGood = Math.abs(s.coverage - 0.8) <= 0.06;
    root.innerHTML = head + `
      <div class="tiles">
        <div class="card tile"><div class="label">MAE ${info("Mean absolute error of P50, €/MWh. Lower is better.")}</div><div class="big">${eur(s.mae, 1)}<small>€/MWh</small></div><div class="foot">${s.n.toLocaleString()} forecasts</div></div>
        <div class="card tile"><div class="label">Coverage ${info("Share of prices inside P10–P90. Target about 80%.")}</div><div class="big" style="color:var(${covGood ? "--ok" : "--warn"})">${pct(s.coverage)}</div>
          <div class="meter"><i style="width:${s.coverage * 100}%;background:var(${covGood ? "--ok" : "--warn"})"></i></div><div class="foot">target 80%</div></div>
        <div class="card tile"><div class="label">Pinball ${info("Mean pinball loss of P10 and P90. Lower is better.")}</div><div class="big">${eur(s.pinball, 2)}</div><div class="foot">P10 + P90</div></div>
        <div class="card tile"><div class="label">Spike Brier ${info("Brier score of the two spike probabilities (above and below spot). Lower is better.")}</div><div class="big">${s.spike.toFixed(3)}</div><div class="foot">above + below spot</div></div>
        <div class="card tile"><div class="label">Direction Brier ${info("Three-class Brier score of up, down and none. Lower is better.")}</div><div class="big">${s.direction.toFixed(3)}</div><div class="foot">up / down / none</div></div>
      </div>
      <div class="card"><div class="card-head"><h2>Forecast vs actual</h2><span class="hint">${(to - from) > 7 * 24 * HOUR ? "last 7 days of the range" : "the whole range"} · forecasts made 1 h and 6 h ahead · drag to zoom</span></div>
        <div class="chart tall" id="track"></div></div>
      <div class="grid cols-2 mt">
        <div class="card"><div class="card-head"><h2>Error by hours ahead</h2><span class="hint">MAE €/MWh</span></div><div class="chart mid" id="byhour"></div></div>
        <div class="card"><div class="card-head"><h2>Alerts → outcome</h2><span class="hint">each event once</span></div>
          <div class="tablewrap" style="max-height:250px;overflow:auto">${alertTable(hist, tz)}</div></div>
      </div>`;
    trackChart(document.getElementById("track"), points, { tz });
    barChart(document.getElementById("byhour"), s.maeByHour.map((_, h) => `${h + 1}h`), s.maeByHour, { name: "", color: c.accent });
  }
  root.querySelectorAll("#win button").forEach((b) => (b.onclick = () => { window.state.window = b.dataset.w; window.render(); }));
  for (const id of ["c-from", "c-to"]) {
    const el = document.getElementById(id);
    if (el) el.onchange = () => {
      let from = document.getElementById("c-from").value, to = document.getElementById("c-to").value;
      if (from && to && to < from) [from, to] = id === "c-from" ? [from, from] : [to, to];
      window.state.custom = { from, to };
      window.render();
    };
  }
}

// Past alerts with what followed
function alertTable(list, tz) {
  if (!list.length) return `<div class="calm small">No price-risk or direction alerts in this window</div>`;
  return `<table><tbody>${list.map((a) => {
    const k = KIND[a.kind];
    const res = !a.known ? `<span class="no-mark">pending</span>` : a.events ? `<span class="ok-mark">✓ ${a.events}/${a.known}</span>` : `<span class="no-mark">✗ none</span>`;
    return `<tr><td style="color:var(${k.color});width:24px">${k.icon}</td><td>${k.name}</td><td class="muted">${fmtDay(a.start, tz)} ${fmtTime(a.start, tz)}–${fmtTime(a.end, tz)}</td>
      <td class="num">${pct(a.peak)}</td><td class="num">${res}</td></tr>`;
  }).join("")}</tbody></table>`;
}

// Insights over everything known at the selected time
export function renderInsights(root, ds, i) {
  const tz = window.state.tz, asOf = ds.origins[i], from = asOf - 30 * 24 * HOUR, c = colors();
  const stats = (ds.raw.meta.alert_stats || []).filter((s) => s.inside != null);
  const days = [], cells = [], marks = [], dayIndex = new Map();
  const bins = { hi: Array.from({ length: 10 }, () => [0, 0, 0]), lo: Array.from({ length: 10 }, () => [0, 0, 0]) };
  const width = [];
  for (let t = Math.max(from, ds.origins[0] + HOUR); t < asOf; t += Q) {
    const f = ds.aheadRow(t, 1);
    if (!f) continue;
    const day = fmt(t, tz, { day: "numeric", month: "short" }), hour = Number(fmt(t, tz, { hour: "2-digit", hour12: false })) % 24;
    if (!dayIndex.has(day)) { dayIndex.set(day, days.length); days.push(day); }
    cells.push([hour, dayIndex.get(day), f.hi, `${dayIndex.get(day)}:${hour}`]);
    const a = ds.outcome(t, asOf);
    if (!a) continue;
    if (a.hi) marks.push([hour, dayIndex.get(day)]);
    for (const [k, p, o] of [["hi", f.hi, a.hi], ["lo", f.lo, a.lo]]) {
      const b = bins[k][Math.min(9, Math.floor(p * 10))];
      b[0] += p; b[1] += o; b[2] += 1;
    }
    width.push([f.p90 - f.p10, Math.abs(a.price - f.p50)]);
  }
  const merged = new Map();
  for (const [h, d, p, key] of cells) { const m = merged.get(key) || [h, d, 0, 0]; m[2] += p; m[3] += 1; merged.set(key, m); }
  const heat = [...merged.values()].map(([h, d, s, n]) => [h, d, s / n]);
  const rel = (k) => bins[k].filter((b) => b[2] >= 10).map((b) => [b[0] / b[2], b[1] / b[2], b[2]]);
  width.sort((a, b) => a[0] - b[0]);
  const fifths = Array.from({ length: 5 }, (_, q) => width.slice(Math.floor((q * width.length) / 5), Math.floor(((q + 1) * width.length) / 5)));
  const mae = fifths.map((f) => (f.length ? f.reduce((a, b) => a + b[1], 0) / f.length : 0));
  const ratio = mae[0] ? mae[4] / mae[0] : null;
  const best = stats.find((s) => s.kind === "spike_high" && s.period === "Test") || stats[0];
  root.innerHTML = `
    <div class="tiles" style="grid-template-columns:repeat(3,minmax(0,1fr))">
      <div class="card tile"><div class="label">Wide band = big error</div><div class="big">${ratio ? `${ratio.toFixed(0)}×` : "–"}</div><div class="foot">MAE of widest vs narrowest fifth, last 30 days</div></div>
      <div class="card tile"><div class="label">Spike-above alerts hit</div><div class="big" style="color:var(--high)">${best ? `${(best.inside / best.overall).toFixed(1)}×` : "–"}</div><div class="foot">more spikes inside alerts than average (test)</div></div>
      <div class="card tile"><div class="label">Spikes caught in window</div><div class="big">${best ? pct(best.window_hit) : "–"}</div><div class="foot">of spike-above alerts saw a spike (test)</div></div>
    </div>
    <div class="grid cols-2">
      <div class="card"><div class="card-head"><h2>When does spike risk above spot build?</h2><span class="hint">1 h ahead · last 30 days · dots: actual spikes</span></div><div class="chart tall" id="heat"></div></div>
      <div class="card"><div class="card-head"><h2>Wider band, bigger error</h2><span class="hint">MAE by band-width fifth</span></div><div class="chart tall" id="width"></div></div>
    </div>
    <div class="grid cols-2 mt">
      <div class="card"><div class="card-head"><h2>Are the probabilities honest?</h2><span class="hint">on the dashed line = calibrated</span></div><div class="chart" id="rel"></div></div>
      <div class="card"><div class="card-head"><h2>Do alerts point to events?</h2><span class="hint">event rate inside alert ÷ overall rate</span></div><div class="chart" id="lift"></div></div>
    </div>
    <div class="card mt"><div class="card-head"><h2>What moves the price forecast</h2><span class="hint">mean SHAP contribution to P50, €/MWh</span></div><div class="chart" id="imp" style="height:400px"></div></div>`;
  heatmap(document.getElementById("heat"), days, Array.from({ length: 24 }, (_, h) => h), heat, { max: 0.4, color: c.high, name: "Spike risk above spot", marks, tz });
  barChart(document.getElementById("width"), ["Narrowest", "2", "3", "4", "Widest"], mae, { name: "", color: c.warn });
  const chart = reliabilityChart(document.getElementById("rel"), rel("hi"), { color: c.high });
  chart.setOption({ legend: { show: true, top: 0, right: 0, data: ["▲ Spikes above spot", "▼ Spikes below spot"], textStyle: { color: c.muted } },
    series: [{}, { name: "▲ Spikes above spot" }, { name: "▼ Spikes below spot", type: "line", data: rel("lo"), symbol: "circle", lineStyle: { color: c.low }, itemStyle: { color: c.low }, symbolSize: 8 }] });
  if (stats.length) {
    const kinds = ["spike_high", "spike_low", "direction_up"];
    const val = kinds.map((k) => { const s = stats.find((x) => x.kind === k && x.period === "Validation"); return s ? +(s.inside / s.overall).toFixed(2) : null; });
    const test = kinds.map((k) => { const s = stats.find((x) => x.kind === k && x.period === "Test"); return s ? +(s.inside / s.overall).toFixed(2) : null; });
    draw(document.getElementById("lift"), {
      animation: false, textStyle: { color: c.text }, grid: { left: 130, right: 44, top: 30, bottom: 24 },
      legend: { top: 0, right: 0, textStyle: { color: c.muted }, data: ["Validation", "Test"] },
      tooltip: { trigger: "axis", backgroundColor: c.panel, borderColor: c.line, textStyle: { color: c.text }, valueFormatter: (v) => `${v}×` },
      xAxis: { type: "value", axisLabel: { color: c.muted, formatter: "{value}×" }, splitLine: { lineStyle: { color: c.line } } },
      yAxis: { type: "category", inverse: true, data: kinds.map((k) => `${KIND[k].icon} ${KIND[k].name}`), axisLabel: { color: c.muted } },
      series: [
        { name: "Validation", type: "bar", data: val, itemStyle: { color: c.accent, borderRadius: 4 }, barGap: "20%", label: { show: true, position: "right", color: c.muted, formatter: "{c}×" } },
        { name: "Test", type: "bar", data: test, itemStyle: { color: c.muted, borderRadius: 4 }, label: { show: true, position: "right", color: c.muted, formatter: "{c}×" } },
      ],
    });
  } else document.getElementById("lift").innerHTML = `<div class="calm small">Shown for the validation and test periods</div>`;
  const imp = (ds.raw.meta.importance || []).slice(0, 12);
  if (imp.length) barChart(document.getElementById("imp"), imp.map((r) => window.DRIVER_NAMES[r.feature] || r.feature), imp.map((r) => r.mean_abs_contribution),
    { name: "", horizontal: true, format: (v) => v.toFixed(2) });
  else document.getElementById("imp").innerHTML = `<div class="calm small">Shown for the validation and test periods</div>`;
}

// Model, data rule and API
export function renderAbout(root) {
  const host = location.origin;
  const item = (icon, title, text) => `<div class="card tile"><div class="label">${icon} ${title}</div><p class="small muted" style="margin-top:8px">${text}</p></div>`;
  root.innerHTML = `
    <div class="tiles" style="grid-template-columns:repeat(4,minmax(0,1fr))">
      ${item("↗", "Every hour", "P50 with a P10–P90 range, spike risk, regulation direction and drivers for the next 40 quarter-hours.")}
      ${item("◉", "Only what matters", "Alerts for spike risk, up-regulation, conflicting signals, big changes and unusual uncertainty. Suggestions to review, never instructions.")}
      ${item("↺", "Travel in time", "The time control shows only what was known then. Reveal actual adds hindsight, clearly marked.")}
      ${item("⛨", "No peeking", "At each forecast time the model reads only rows whose first_usable_origin_utc has passed.")}
    </div>
    <div class="grid cols-2">
      <div class="card"><div class="card-head"><h2>Data sets</h2></div>
        <table><tbody>
          <tr><td><span class="tag val">VALIDATION</span></td><td>7 Sep – 4 Oct</td><td class="muted">model trained to 6 Sep</td></tr>
          <tr><td><span class="tag test">TEST</span></td><td>5 Oct – 1 Nov</td><td class="muted">submitted forecast</td></tr>
          <tr><td><span class="tag upload">UPLOADED</span></td><td>your files</td><td class="muted">from Run a forecast</td></tr>
        </tbody></table></div>
      <div class="card"><div class="card-head"><h2>API</h2><a class="btn ghost" href="api/docs" target="_blank">Open docs ↗</a></div>
        <table><tbody>
          <tr><td><code>GET /api/forecast?origin=…</code></td><td class="muted">40 quarter-hours + drivers</td></tr>
          <tr><td><code>GET /api/alerts?origin=…</code></td><td class="muted">what to check</td></tr>
          <tr><td><code>GET /api/origins</code></td><td class="muted">available times</td></tr>
          <tr><td><code>POST /api/jobs</code></td><td class="muted">forecast your files</td></tr>
        </tbody></table>
        <pre>curl "${host}/api/forecast?origin=2026-10-08T02:00:00Z"</pre></div>
    </div>`;
}
