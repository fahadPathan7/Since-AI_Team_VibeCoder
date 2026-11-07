import { Dataset, fmtFull, fmtTime, HOUR } from "./data.js";
import { disposeAll } from "./charts.js";
import { renderNow, renderNext, renderHindsight, renderInsights, renderAbout } from "./views.js";
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

window.state = { view: "now", tz: "Europe/Helsinki", reveal: false, showPrev: true, window: "week", datasets: [], ds: 0, i: 0, playing: null };
const S = window.state;
const VIEWS = { now: renderNow, next: renderNext, hindsight: renderHindsight, insights: renderInsights, run: renderRun, about: renderAbout };

const $ = (id) => document.getElementById(id);

// Light or dark theme, remembered per browser
function applyTheme(theme) {
  if (theme) document.documentElement.dataset.theme = theme;
  else delete document.documentElement.dataset.theme;
}
applyTheme(recall("theme"));
$("theme").onclick = () => {
  const next = document.documentElement.dataset.theme === "light" ? "dark" : "light";
  applyTheme(next); remember("theme", next); render();
};

const current = () => S.datasets[S.ds];

// Header: time control, freshness line and data set list
function header() {
  const ds = current();
  const o = ds.origins[S.i], cut = ds.cutoff(S.i);
  $("origin-label").textContent = fmtFull(o, S.tz);
  $("origin-label").title = "Forecast made at this time. Every view shows only what was known then.";
  $("origin-slider").max = ds.origins.length - 1;
  $("origin-slider").value = S.i;
  const period = ds.period(S.i);
  const kind = ds.raw.meta.source === "upload" ? "upload" : period?.name === "Test" ? "test" : "val";
  const age = Math.round((o - cut) / 60000);
  $("freshness").innerHTML = `<span class="tag ${kind}">${period ? period.name.toUpperCase() : "UPLOADED RUN"}</span>
    <span class="tag" title="Latest measured data used by this forecast"><span class="dot"></span>Data to <b>${fmtTime(cut, S.tz)}</b> · ${age} min old</span>
    <span class="tag" title="${period ? period.model : "Final model"}">${kind === "val" ? "Model trained to 6 Sep" : "Final model · trained to 4 Oct"}</span>`;
  $("dataset").innerHTML = S.datasets.map((d, k) => `<option value="${k}" ${k === S.ds ? "selected" : ""}>${d.label}</option>`).join("");
  document.querySelectorAll("#tabs button").forEach((b) => b.classList.toggle("on", b.dataset.view === S.view));
  }

// Draw the current view
function render() {
  if (!S.datasets.length) return;
  header();
  disposeAll();
  const root = $("view");
  const ds = current();
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
$("play").onclick = () => {
  if (S.playing) { clearInterval(S.playing); S.playing = null; $("play").textContent = "▶ Replay"; return; }
  $("play").textContent = "❚❚ Pause";
  S.playing = setInterval(() => { if (S.i >= current().origins.length - 1) $("play").click(); else moveTo(S.i + 1); }, 900);
};
document.addEventListener("keydown", (e) => {
  if (e.target.tagName === "INPUT" || e.target.tagName === "SELECT") return;
  if (e.key === "ArrowLeft") shift(e.shiftKey ? -24 : -1);
  if (e.key === "ArrowRight") shift(e.shiftKey ? 24 : 1);
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
  $("view").innerHTML = `<div class="card">Loading forecasts…</div>`;
  const raw = await (await fetch("data/dashboard.json")).json();
  S.datasets.push(new Dataset(raw, "Validation + test periods"));
  const [view, iso] = location.hash.slice(1).split("/");
  if (VIEWS[view]) S.view = view;
  const ds = current();
  const wanted = iso ? Date.parse(iso + ":00Z") : NaN;
  const testStart = (raw.meta.periods || []).find((p) => p.name === "Test")?.from ?? ds.origins[0];
  const lively = ds.origins.findIndex((o, k) => o >= testStart && ds.alerts(k).some((a) => a.kind === "spike_high") && ds.alerts(k).length >= 3);
  const target = Number.isFinite(wanted) ? wanted : lively >= 0 ? ds.origins[lively] : ds.origins[ds.origins.length - 1];
  S.i = Math.max(0, ds.origins.findIndex((o) => o >= target));
  render();
}
start().catch((e) => ($("view").innerHTML = `<div class="card error">Couldn't load the forecasts: ${e.message}</div>`));
