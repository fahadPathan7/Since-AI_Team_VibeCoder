import { Dataset, fmtDay, fmtTime, HOUR } from "./data.js";
import { disposeAll } from "./charts.js";
import { renderNow, renderNext, renderHindsight, renderAbout } from "./views.js";
import { renderRun } from "./upload.js";

window.DRIVER_NAMES = {
  spot: "Spot price level", spot_dev_day: "Spot vs daily average", spot_drange: "Daily spot range", spot_chg_prev_h: "Spot change, previous hour",
  net_fc: "Net demand forecast", wind_fc: "Wind power forecast", cons_fc: "Consumption forecast", net_ramp_prev_h: "Net demand ramp",
  hour: "Time of day", is_weekend: "Weekend", step: "Forecast horizon", sp_last: "Latest gap to spot", sp_med_4h: "Gap to spot, last 4 h",
  sp_med_24h: "Gap to spot, last 24 h", dir_last: "Latest direction", up_6h: "Up-regulation share, 6 h", up_24h: "Up-regulation share, 24 h",
  mfrr_up_prem_4h: "mFRR up premium, 4 h", mfrr_dn_prem_4h: "mFRR down premium, 4 h", afrr_up_prem_4h: "aFRR up premium, 4 h",
  afrr_dn_prem_4h: "aFRR down premium, 4 h", cons_err_1h: "Consumption vs forecast", net_export: "Cross-border net flow",
  gap_h: "Data age", sp_last_decay: "Latest gap, faded", sp_mix: "Latest gap, faded to 4 h median",
};

const store = (() => { try { return window.localStorage; } catch { return null; } })();
const remember = (k, v) => { try { store?.setItem(k, v); } catch {} };
const recall = (k) => { try { return store?.getItem(k); } catch { return null; } };

window.state = { view: "now", tz: "Europe/Helsinki", reveal: false, showPrev: true, window: "week", datasets: [], ds: 0, i: 0, playing: null, speed: 1, animate: true };
const S = window.state;
const VIEWS = { now: renderNow, next: renderNext, hindsight: renderHindsight, run: renderRun, about: renderAbout };

const $ = (id) => document.getElementById(id);

// Light or dark theme: ?theme= in the address, then the remembered choice, then the system setting
function applyTheme(theme) {
  document.documentElement.dataset.theme = theme === "dark" ? "dark" : "light";
}
const systemDark = window.matchMedia?.("(prefers-color-scheme: dark)").matches;
applyTheme(new URLSearchParams(location.search).get("theme") || recall("theme") || (systemDark ? "dark" : "light"));
$("theme").onclick = () => {
  const next = document.documentElement.dataset.theme === "dark" ? "light" : "dark";
  applyTheme(next); remember("theme", next); render();
};

const current = () => S.datasets[S.ds];

// A spike-risk alert that covers the coming hour at an origin, so the Now view is not calm there
function spikeNow(ds, k, kind) {
  return ds.alerts(k).find((a) => a.kind === kind && a.start < ds.origins[k] + HOUR);
}

// Spike risk in the coming hour at each origin: 1 = above spot, 0 = below spot, with the peak as weight
function alertHeat(ds) {
  ds.heat ||= ds.origins.map((_, k) => {
    const hi = spikeNow(ds, k, "spike_high"), lo = spikeNow(ds, k, "spike_low");
    return hi ? [1, Math.min(1, hi.peak / 0.5)] : lo ? [0, Math.min(1, lo.peak / 0.6)] : null;
  });
  return ds.heat;
}

// Ribbon above the time slider: where in the period alerts were raised
let ribbonKey = "";
function ribbon(ds) {
  const cv = $("ribbon"), w = cv.clientWidth, h = cv.clientHeight, theme = document.documentElement.dataset.theme;
  const key = `${S.ds}:${w}:${theme}`;
  if (!w || key === ribbonKey) return;
  ribbonKey = key;
  const dpr = window.devicePixelRatio || 1, css = getComputedStyle(document.documentElement);
  const color = ["--low", "--high"].map((n) => css.getPropertyValue(n).trim());
  cv.width = w * dpr; cv.height = h * dpr;
  const g = cv.getContext("2d");
  g.scale(dpr, dpr);
  const n = ds.origins.length, pad = 7, span = w - 2 * pad, bar = Math.max(1.5, span / n + 0.5);
  const x = (k) => pad + (k / Math.max(1, n - 1)) * span;
  alertHeat(ds).forEach((v, k) => {
    if (!v) return;
    g.globalAlpha = 0.35 + 0.65 * v[1];
    g.fillStyle = color[v[0]];
    g.fillRect(x(k) - bar / 2, 0, bar, h);
  });
  g.globalAlpha = 1;
  g.fillStyle = css.getPropertyValue("--text").trim();
  for (let k = 1; k < n; k++) if (ds.raw.period?.[k] !== ds.raw.period?.[k - 1]) g.fillRect(x(k) - 1, 0, 2, h);
}
window.addEventListener("resize", () => S.datasets.length && ribbon(current()));

// Header: time control, freshness line and data set list
function header() {
  const ds = current();
  const o = ds.origins[S.i], cut = ds.cutoff(S.i);
  $("origin-day").textContent = fmtDay(o, S.tz);
  $("origin-time").textContent = fmtTime(o, S.tz);
  $("origin-slider").max = ds.origins.length - 1;
  $("origin-slider").value = S.i;
  $("origin-slider").style.setProperty("--fill", `${(S.i / Math.max(1, ds.origins.length - 1)) * 100}%`);
  $("range-start").textContent = fmtDay(ds.origins[0], S.tz).replace(/^\w+ /, "");
  $("range-end").textContent = fmtDay(ds.origins[ds.origins.length - 1], S.tz).replace(/^\w+ /, "");
  const period = ds.period(S.i);
  const kind = ds.raw.meta.source === "upload" ? "upload" : period?.name === "Test" ? "test" : "val";
  const age = Math.round((o - cut) / 60000);
  $("freshness").innerHTML = `<span class="tag" title="Latest measured data used by this forecast"><span class="dot"></span>Data to <b>${fmtTime(cut, S.tz)}</b> · ${age} min old</span>
    <span class="tag" title="${period ? period.model : "Final model"}">${kind === "upload" ? "Uploaded run · final model" : kind === "val" ? "Model trained to 6 Sep" : "Final model · trained to 4 Oct"}</span>`;
  $("dataset").innerHTML = S.datasets.map((d, k) => `<option value="${k}" ${k === S.ds ? "selected" : ""}>${d.label}</option>`).join("");
  document.querySelectorAll("#tabs button").forEach((b) => b.classList.toggle("on", b.dataset.view === S.view));
  ribbon(ds);
}

// Draw the current view. Cards and charts animate in only when the view changes, not on every time step
let shown = "", enterTimer = null;
function render() {
  if (!S.datasets.length) return;
  header();
  disposeAll();
  const root = $("view");
  const ds = current();
  S.animate = shown !== S.view && !S.playing;
  shown = S.view;
  if (S.animate) {
    clearTimeout(enterTimer);
    root.classList.remove("enter");
    void root.offsetWidth;
    root.classList.add("enter");
    enterTimer = setTimeout(() => root.classList.remove("enter"), 900);
  }
  Promise.resolve(VIEWS[S.view](root, ds, S.i)).catch((e) => { root.innerHTML = `<div class="card error">Something went wrong: ${e.message}</div>`; console.error(e); });
  const iso = new Date(ds.origins[S.i]).toISOString().slice(0, 16);
  history.replaceState(null, "", `#${S.view}/${iso}`);
}
window.render = render;

// Jump to an origin by position
function moveTo(i) {
  const ds = current();
  S.i = Math.max(0, Math.min(ds.origins.length - 1, i));
  render();
}

// Move by hours, landing on the nearest available origin
function shift(hours) {
  const ds = current(), target = ds.origins[S.i] + hours * HOUR;
  let best = S.i;
  for (let k = 0; k < ds.origins.length; k++) if (Math.abs(ds.origins[k] - target) < Math.abs(ds.origins[best] - target)) best = k;
  moveTo(best);
}

document.querySelectorAll("[data-shift]").forEach((b) => (b.onclick = () => shift(Number(b.dataset.shift))));
$("origin-slider").oninput = (e) => moveTo(Number(e.target.value));
document.querySelectorAll("#tabs button").forEach((b) => (b.onclick = () => { S.view = b.dataset.view; render(); }));
$("dataset").onchange = (e) => { S.ds = Number(e.target.value); S.i = Math.min(S.i, current().origins.length - 1); render(); };

// Replay: step forward one origin at a time, at 1, 2 or 4 steps per second
function replay(on) {
  clearInterval(S.playing);
  S.playing = on ? setInterval(() => { if (S.i >= current().origins.length - 1) replay(false); else moveTo(S.i + 1); }, 900 / S.speed) : null;
  $("play").textContent = on ? "❚❚ Pause" : "▶ Replay";
  document.body.classList.toggle("playing", on);
}
$("play").onclick = () => replay(!S.playing);
$("speed").onclick = () => {
  S.speed = { 1: 2, 2: 4, 4: 1 }[S.speed];
  $("speed").textContent = `${S.speed}×`;
  if (S.playing) replay(true);
};

// Jump to the next (or previous) time a spike-risk alert starts to cover the coming hour
function jumpToAlert(dir) {
  const ds = current();
  const hot = (k) => k >= 0 && Boolean(spikeNow(ds, k, "spike_high") || spikeNow(ds, k, "spike_low"));
  for (let k = S.i + dir; k >= 0 && k < ds.origins.length; k += dir) if (hot(k) && !hot(k - 1)) return moveTo(k);
  const b = $("next-alert");
  b.classList.remove("none"); void b.offsetWidth; b.classList.add("none");
}
$("next-alert").onclick = (e) => jumpToAlert(e.shiftKey ? -1 : 1);

document.addEventListener("keydown", (e) => {
  if (["INPUT", "SELECT", "TEXTAREA"].includes(e.target.tagName) || e.metaKey || e.ctrlKey || e.altKey) return;
  const view = Object.keys(VIEWS)[Number(e.key) - 1];
  if (e.key === "ArrowLeft") shift(e.shiftKey ? -24 : -1);
  else if (e.key === "ArrowRight") shift(e.shiftKey ? 24 : 1);
  else if (e.key === " " && e.target.tagName !== "BUTTON") { e.preventDefault(); replay(!S.playing); }
  else if (e.key.toLowerCase() === "n") jumpToAlert(e.shiftKey ? -1 : 1);
  else if (e.key.toLowerCase() === "t") $("theme").click();
  else if (view && !(S.static && view === "run")) { S.view = view; render(); }
});

// Add a data set, such as an uploaded run, and switch to it
window.addDataset = (raw, label) => {
  S.datasets.push(new Dataset(raw, label));
  S.ds = S.datasets.length - 1;
  S.i = 0;
  S.view = "next";
  render();
};

// Load the precomputed periods and restore the view and time from the address
async function start() {
  $("view").innerHTML = `<div class="skeleton" aria-label="Loading forecasts"><div style="height:150px"></div>
    <div class="s-row">${`<div style="height:160px"></div>`.repeat(5)}</div><div style="height:380px"></div></div>`;
  const [raw, spot, api] = await Promise.all([
    fetch("data/dashboard.json").then((r) => r.json()),
    fetch("api/spot").then((r) => (r.ok ? r.json() : null)).catch(() => null),
    fetch("api/config").then((r) => r.ok && (r.headers.get("content-type") || "").includes("json")).catch(() => false),
  ]);
  // Without the API (a static host) the precomputed views still work; forecasts from uploaded files need the API
  S.static = !api;
  if (S.static) document.querySelector('#tabs [data-view="run"]').hidden = true;
  if (spot) window.spotAt = (t) => spot.values[Math.round((t - spot.t0) / spot.step)] ?? null;
  S.datasets.push(new Dataset(raw, "Validation + test periods"));
  const [view, iso] = location.hash.slice(1).split("/");
  if (VIEWS[view] && !(S.static && view === "run")) S.view = view;
  const ds = current();
  const wanted = iso ? Date.parse(iso + ":00Z") : NaN;
  const testStart = (raw.meta.periods || []).find((p) => p.name === "Test")?.from ?? ds.origins[0];
  const lively = ds.origins.findIndex((o, k) => o >= testStart && ds.alerts(k).some((a) => a.kind === "spike_high") && ds.alerts(k).length >= 3);
  const target = Number.isFinite(wanted) ? wanted : lively >= 0 ? ds.origins[lively] : ds.origins[ds.origins.length - 1];
  S.i = Math.max(0, ds.origins.findIndex((o) => o >= target));
  render();
}
start().catch((e) => ($("view").innerHTML = `<div class="card error">Couldn't load the forecasts: ${e.message}</div>`));
