import { esc, pct, eur } from "./data.js";

const files = { inputs: null, spot: null, origins: null };
const checked = { inputs: null, spot: null, origins: null };
let config = null;
let running = false;

// Split one CSV line, allowing quoted fields
function splitCsv(line) {
  const out = [];
  let cur = "", quoted = false;
  for (const ch of line) {
    if (ch === '"') quoted = !quoted;
    else if (ch === "," && !quoted) { out.push(cur); cur = ""; }
    else cur += ch;
  }
  out.push(cur);
  return out.map((s) => s.trim());
}

// Check a chosen file in the browser before it is uploaded
async function precheck(kind, file) {
  const name = file.name.toLowerCase();
  if (!name.endsWith(".csv") && !name.endsWith(".parquet")) return { ok: false, msg: "Use a .csv or .parquet file" };
  if (file.size > config.upload_limit_mb * 1e6) return { ok: false, msg: `Larger than ${config.upload_limit_mb} MB` };
  if (name.endsWith(".parquet")) return { ok: true, msg: `${(file.size / 1e6).toFixed(1)} MB · checked on upload` };
  const text = kind === "inputs" ? await file.text() : await file.slice(0, 2e6).text();
  const lines = text.split(/\r?\n/);
  const header = splitCsv(lines[0].replace(/^﻿/, ""));
  if (kind === "origins") {
    if (!header.includes(config.origin_column)) return { ok: false, msg: `Missing column '${config.origin_column}'. Found: ${header.join(", ")}` };
    const col = header.indexOf(config.origin_column);
    const n = new Set(lines.slice(1).filter(Boolean).map((l) => splitCsv(l)[col])).size;
    return { ok: true, msg: `${n} origins` };
  }
  const missing = config.long_columns.filter((c) => !header.includes(c));
  if (missing.length) return { ok: false, msg: `Missing column(s): ${missing.join(", ")}. Found: ${header.join(", ")}` };
  const col = header.indexOf("series_id");
  const series = new Set();
  for (let k = 1; k < lines.length; k++) if (lines[k]) series.add(splitCsv(lines[k])[col]);
  if (kind === "spot") {
    return series.has("fi_spot_price") ? { ok: true, msg: "fi_spot_price found" } : { ok: false, msg: "No fi_spot_price rows" };
  }
  const needed = Object.keys(config.required_series).filter((s) => s !== "fi_spot_price");
  const absent = needed.filter((s) => !series.has(s));
  if (absent.length) return { ok: false, msg: `Missing series: ${absent.join(", ")}` };
  const spotInside = series.has("fi_spot_price");
  return { ok: true, spotInside, msg: `${((lines.length - 1) / 1e6).toFixed(2)} M rows · all ${needed.length} series${spotInside ? " + spot" : ""}` };
}

// One drag-and-drop zone with its check message
function drop(kind, icon, title, help, optional) {
  return `<label class="drop" id="drop-${kind}">${optional ? `<span class="opt">optional</span>` : ""}
    <input type="file" id="file-${kind}" accept=".csv,.parquet">
    <div class="ico">${icon}</div><div class="ttl">${title}</div><div class="sub">${help}</div>
    <div class="msg" id="msg-${kind}">Drop or click</div></label>`;
}

// Upload with progress, to S3 or directly to the API
function put(url, file, onProgress) {
  return new Promise((resolve, reject) => {
    const x = new XMLHttpRequest();
    x.open("PUT", url);
    x.upload.onprogress = (e) => e.lengthComputable && onProgress(e.loaded / e.total);
    x.onload = () => (x.status < 300 ? resolve() : reject(new Error(`Upload failed (${x.status}): ${x.responseText.slice(0, 200)}`)));
    x.onerror = () => reject(new Error("Upload failed: network error"));
    x.send(file);
  });
}

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

// Whether every needed file passed its check
function ready() {
  const originsOk = files.origins ? checked.origins?.ok : document.getElementById("first")?.value && document.getElementById("last")?.value;
  const spotOk = files.spot ? checked.spot?.ok : checked.inputs?.spotInside || files.inputs?.name.toLowerCase().endsWith(".parquet");
  return Boolean(checked.inputs?.ok && spotOk && originsOk && !running);
}

// Enable the run button only when ready
function refresh() {
  const b = document.getElementById("go");
  if (b) b.disabled = !ready();
}

// Summary of a finished run
function resultHtml(info, job) {
  const r = info.report || {};
  const sc = r.score;
  const skipped = (r.skipped || []).slice(0, 8).map((x) => `<li><code>${x.origin}</code> ${esc(x.reason)}</li>`).join("");
  const tile = (label, value, foot = "") => `<div class="card tile"><div class="label">${label}</div><div class="big">${value}</div><div class="foot">${foot}</div></div>`;
  return `<div class="tiles" style="grid-template-columns:repeat(3,minmax(0,1fr))">
      ${tile("Origins forecast", `${r.origins_forecast}<small>/ ${r.origins_requested}</small>`, `${r.series} series read`)}
      ${tile("Official validator", r.validator_passed ? `<span style="color:var(--ok)">✓ Passed</span>` : `<span class="error">✗ Failed</span>`, "validate_submission.py")}
      ${tile("Data", `<span style="font-size:15px">${r.data_from?.slice(0, 10)} → ${r.data_to?.slice(0, 10)}</span>`, "UTC")}
    </div>
    ${sc ? `<div class="tiles">
      ${tile("MAE", `${eur(sc.mae_p50, 2)}`, "official score.py")}${tile("Pinball", eur(sc.calibration_pinball_mean, 2))}${tile("Coverage", pct(sc.coverage_p10_p90))}
      ${tile("Spike Brier", sc.brier_spike_mean.toFixed(4))}${tile("Direction Brier", sc.brier_direction.toFixed(4))}</div>` : ""}
    <div class="toolbar"><button class="btn" id="open">◉ Open in dashboard</button>
      <a class="btn ghost" href="api/jobs/${job}/forecast.csv" download="forecast_backtest.csv">⤓ forecast_backtest.csv</a>
      ${sc ? "" : `<span class="hint">Not scored: no outcomes for these quarter-hours in the upload</span>`}</div>
    ${skipped ? `<details class="more"><summary>${r.skipped.length} origin(s) skipped</summary><ul class="small muted">${skipped}</ul></details>` : ""}
    <details class="more"><summary>Validator report</summary><pre>${esc(r.validator_report || "")}</pre></details>`;
}

// Create the job, upload the files, start it and follow its progress
async function run() {
  running = true; refresh();
  const out = document.getElementById("run-out");
  const bar = (p, text) => (out.innerHTML = `<div style="margin-top:14px"><b>${esc(text)}</b><div class="progress"><div style="width:${p * 100}%"></div></div></div>`);
  try {
    const body = { inputs: files.inputs.name, spot: files.spot?.name || null, origins: files.origins?.name || null };
    if (!files.origins) Object.assign(body, { first_origin: document.getElementById("first").value + ":00Z", last_origin: document.getElementById("last").value + ":00Z",
      every_hours: Number(document.getElementById("every").value) || 1 });
    const res = await fetch("api/jobs", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
    if (!res.ok) throw new Error((await res.json()).detail || res.statusText);
    const { job, uploads } = await res.json();
    const list = Object.entries(files).filter(([, f]) => f);
    const total = list.reduce((a, [, f]) => a + f.size, 0);
    let done = 0;
    for (const [kind, f] of list) {
      const url = uploads ? uploads[kind] : `api/jobs/${job}/files/${kind}`;
      await put(url, f, (p) => bar((done + p * f.size) / total, `Uploading ${f.name}`));
      done += f.size;
    }
    await fetch(`api/jobs/${job}/start`, { method: "POST" });
    const started = Date.now();
    for (;;) {
      await sleep(1500);
      const info = await (await fetch(`api/jobs/${job}`)).json();
      const secs = Math.round((Date.now() - started) / 1000);
      if (info.state === "done") {
        out.innerHTML = resultHtml(info, job);
        document.getElementById("open").onclick = async () => {
          const payload = await (await fetch(`api/jobs/${job}/payload.json`)).json();
          window.addDataset(payload, `Uploaded run · ${new Date().toLocaleTimeString()}`);
        };
        break;
      }
      if (info.state === "failed") {
        out.innerHTML = `<div class="card mt" style="border-color:var(--high)"><h2 class="error">✗ ${esc(info.step)}</h2><p class="small" style="margin-top:6px">${esc(info.error)}</p></div>`;
        break;
      }
      bar(0.5 + Math.min(0.45, secs / 120), `${info.step || info.state}… (${secs} s)`);
    }
  } catch (e) {
    out.innerHTML = `<div class="card mt" style="border-color:var(--high)"><h2 class="error">✗ Couldn't run the forecast</h2><p class="small" style="margin-top:6px">${esc(e.message)}</p></div>`;
  }
  running = false; refresh();
}

// The guide and form for forecasting from your own files
export async function renderRun(root) {
  config = config || (await (await fetch("api/config")).json());
  const series = Object.keys(config.required_series).map((s) => `<code>${s}</code>`).join(" ");
  root.innerHTML = `<div class="card">
      <div class="card-head"><div><h2>Forecast from your own files</h2><span class="hint">Starter package files as delivered · same model, data rule and output format as the submission</span></div></div>
      <div class="drops">
        ${drop("inputs", "▦", "Inputs", "inputs.csv or inputs.parquet")}
        ${drop("spot", "€", "Spot price", "spot_nordpool.csv", true)}
        ${drop("origins", "◷", "Forecast origins", "forecast_origins.csv")}
      </div>
      <div class="range">or origins from <input type="datetime-local" id="first" step="3600"> to <input type="datetime-local" id="last" step="3600"> UTC, every
        <input type="number" id="every" value="1" min="1" max="24" style="width:56px"> h <button class="btn ghost" id="fill-test" type="button">Test period</button></div>
      <div class="toolbar" style="margin-top:16px"><button class="btn" id="go" disabled>▶ Run forecast</button>
        <span class="hint">673 test origins ≈ 20–60 s · you get the official CSV, validator result and score</span></div>
      <div id="run-out"></div>
      <details class="more"><summary>What files work?</summary>
        <div class="grid cols-2 mt">
          <div><b class="small">Inputs and spot: long format</b>
            <table><tbody>
              <tr><td><code>series_id</code></td><td class="muted">e.g. fi_imbalance_price</td></tr>
              <tr><td><code>timestamp_utc</code></td><td class="muted">2026-10-05T06:00:00Z</td></tr>
              <tr><td><code>value</code></td><td class="muted">number</td></tr>
              <tr><td><code>first_usable_origin_utc</code></td><td class="muted">first time the row may be used</td></tr>
            </tbody></table>
            <p class="small muted">Other columns are ignored. Spot file not needed if the inputs contain <code>fi_spot_price</code>.</p></div>
          <div><b class="small">Origins</b>
            <p class="small muted">A <code>forecast_origin_utc</code> column, UTC quarter-hours. Each origin needs 72 h of history and published spot and day-ahead forecasts for its next 10 h; others are skipped with the reason.</p>
            <b class="small">Series needed</b><p class="small" style="line-height:1.9">${series}</p></div>
        </div>
        <p class="small muted">Uploads are deleted after one day. Spot prices are used, never shown.</p>
      </details>
    </div>`;
  for (const kind of Object.keys(files)) {
    document.getElementById(`file-${kind}`).onchange = async (e) => {
      const f = e.target.files[0];
      files[kind] = f || null; checked[kind] = null;
      const box = document.getElementById(`drop-${kind}`), msg = document.getElementById(`msg-${kind}`);
      box.className = "drop";
      if (!f) { msg.textContent = "Drop or click"; refresh(); return; }
      msg.textContent = "Checking…";
      checked[kind] = await precheck(kind, f);
      box.className = `drop ${checked[kind].ok ? "ok" : "bad"}`;
      msg.textContent = (checked[kind].ok ? "✓ " : "✗ ") + checked[kind].msg;
      if (kind === "inputs" && checked.inputs.ok && !checked.inputs.spotInside && !files.spot) msg.textContent += " · add the spot file";
      refresh();
    };
  }
  for (const kind of Object.keys(files)) {
    const box = document.getElementById(`drop-${kind}`);
    box.ondragenter = () => box.classList.add("drag");
    box.ondragleave = box.ondrop = () => box.classList.remove("drag");
  }
  for (const id of ["first", "last"]) document.getElementById(id).oninput = refresh;
  document.getElementById("fill-test").onclick = () => {
    document.getElementById("first").value = "2026-10-04T21:00";
    document.getElementById("last").value = "2026-11-01T21:00";
    refresh();
  };
  document.getElementById("go").onclick = run;
}
