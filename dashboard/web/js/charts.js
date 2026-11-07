import { fmtTime, fmtFull, fmt, pct } from "./data.js";

const live = new Map();

// Colours from the current theme
export function colors() {
  const css = getComputedStyle(document.documentElement);
  const v = (n) => css.getPropertyValue(n).trim();
  return { text: v("--text"), muted: v("--muted"), line: v("--line"), accent: v("--accent"), band: v("--band"), high: v("--high"),
    low: v("--low"), up: v("--up"), down: v("--down"), warn: v("--warn"), panel: v("--panel"), ok: v("--ok"), spot: v("--accent-2") };
}

// Draw or redraw a chart into an element
export function draw(el, option) {
  if (!el) return;
  let chart = live.get(el);
  if (!chart || chart.isDisposed()) {
    chart = echarts.init(el, null, { renderer: "canvas" });
    live.set(el, chart);
  }
  chart.setOption(option, true);
  return chart;
}

// Free every chart before a view is redrawn
export function disposeAll() {
  for (const c of live.values()) c.dispose();
  live.clear();
}

window.addEventListener("resize", () => live.forEach((c) => c.resize()));

// Settings shared by every chart
function base(c) {
  return {
    animation: false,
    textStyle: { color: c.text, fontFamily: "inherit" },
    grid: { left: 52, right: 18, top: 30, bottom: 34 },
    tooltip: { trigger: "axis", backgroundColor: c.panel, borderColor: c.line, textStyle: { color: c.text } },
    legend: { top: 0, right: 0, textStyle: { color: c.muted }, itemWidth: 14, itemHeight: 8 },
  };
}

// Time axis labelled in the chosen time zone
function timeAxis(c, tz) {
  return {
    type: "time", axisLine: { lineStyle: { color: c.line } }, splitLine: { show: false },
    axisLabel: { color: c.muted, formatter: (v) => fmtTime(v, tz), hideOverlap: true },
  };
}

// Value axis with theme colours
function valueAxis(c, name, extra = {}) {
  return { type: "value", name, nameTextStyle: { color: c.muted, align: "left" }, axisLabel: { color: c.muted },
    splitLine: { lineStyle: { color: c.line, type: [3, 4] } }, ...extra };
}

// Price band, median, spot, the forecast an hour earlier and, in hindsight, the actual price
export function priceChart(el, rows, { tz, previous, actual }) {
  const spot = window.spotAt;
  const c = colors();
  const series = [
    { name: "P10", type: "line", data: rows.map((r) => [r.t, r.p10]), lineStyle: { opacity: 0 }, symbol: "none", stack: "band", stackStrategy: "all", tooltip: { show: false } },
    { name: "P10–P90 range", type: "line", data: rows.map((r) => [r.t, r.p90 - r.p10]), lineStyle: { opacity: 0 }, symbol: "none", stack: "band", stackStrategy: "all",
      areaStyle: { color: c.band }, color: c.band, tooltip: { show: false } },
    { name: "Forecast now (P50)", type: "line", data: rows.map((r) => [r.t, r.p50]), symbol: "none", lineStyle: { width: 2.5, color: c.accent }, color: c.accent, step: "end" },
  ];
  if (spot) series.push({ name: "Spot price", type: "line", data: rows.map((r) => [r.t, spot(r.t)]), symbol: "none", step: "end",
    lineStyle: { width: 1.5, color: c.spot }, color: c.spot });
  if (previous) series.push({ name: "Forecast 1 h earlier", type: "line", data: previous.map((r) => [r.t, r.p50]), symbol: "none", step: "end",
    lineStyle: { width: 1.5, type: "dashed", color: c.muted }, color: c.muted });
  if (actual) series.push({ name: "Actual price", type: "line", data: actual, symbol: "circle", symbolSize: 4, step: "end",
    lineStyle: { width: 1.8, color: c.high }, color: c.high, connectNulls: false });
  const band = new Map(rows.map((r) => [r.t, r]));
  return draw(el, {
    ...base(c),
    legend: { ...base(c).legend, data: ["Forecast now (P50)", "P10–P90 range", ...(spot ? ["Spot price"] : []), ...(previous ? ["Forecast 1 h earlier"] : []), ...(actual ? ["Actual price"] : [])] },
    tooltip: { ...base(c).tooltip, formatter: (ps) => {
      const t = ps[0].value[0], r = band.get(t);
      const value = (name) => ps.find((p) => p.seriesName === name)?.value[1];
      const line = (color, label, v, bold) => (v == null ? "" : `<br><span style="color:${color}">●</span> ${label}: ${bold ? "<b>" : ""}${v.toFixed(1)}${bold ? "</b>" : ""} €/MWh`);
      return `<b>${fmtFull(t, tz)}</b>` + line(c.accent, "Forecast now (P50)", r.p50, true) + `<br><span style="color:${c.accent};opacity:.5">●</span> Range P10–P90: ${r.p10.toFixed(0)} to ${r.p90.toFixed(0)}`
        + line(c.spot, "Spot price", value("Spot price")) + line(c.muted, "Forecast 1 h earlier (P50)", value("Forecast 1 h earlier"))
        + line(c.high, "Actual price", value("Actual price"));
    } },
    xAxis: timeAxis(c, tz), yAxis: valueAxis(c, "€/MWh", { scale: true }), series,
  });
}

// Exceptional price risk per quarter-hour, high above and low below the axis
export function riskChart(el, rows, { tz, base: rates, actual }) {
  const c = colors();
  const top = Math.min(1, Math.max(0.3, Math.ceil(Math.max(...rows.map((r) => Math.max(r.hi, r.lo))) * 12) / 10));
  const series = [
    { name: "▲ Spike above spot", type: "bar", data: rows.map((r) => [r.t, r.hi]), itemStyle: { color: c.high }, barWidth: "70%" },
    { name: "▼ Spike below spot", type: "bar", data: rows.map((r) => [r.t, -r.lo]), itemStyle: { color: c.low }, barWidth: "70%", barGap: "-100%" },
  ];
  if (rates) series.push(
    { name: "Typical", type: "line", data: rows.map((r) => [r.t, rates.high]), symbol: "none", lineStyle: { type: "dotted", color: c.high }, color: c.muted, tooltip: { show: false } },
    { name: "Typical low", type: "line", data: rows.map((r) => [r.t, -rates.low]), symbol: "none", lineStyle: { type: "dotted", color: c.low }, tooltip: { show: false } },
  );
  if (actual) series.push({ name: "Actual spike", type: "scatter", data: actual.map(([t, v]) => [t, v > 0 ? top * 0.95 : -top * 0.95]), symbol: "diamond", symbolSize: 9, itemStyle: { color: c.text } });
  return draw(el, {
    ...base(c),
    legend: { ...base(c).legend, data: ["▲ Spike above spot", "▼ Spike below spot", ...(rates ? ["Typical"] : []), ...(actual ? ["Actual spike"] : [])] },
    tooltip: { ...base(c).tooltip, formatter: (ps) => {
      const t = ps[0].value[0];
      return `<b>${fmtFull(t, tz)}</b>` + ps.filter((p) => p.seriesName.includes("Spike")).map((p) => `<br>${p.seriesName}: ${pct(Math.abs(p.value[1]), 1)}`).join("");
    } },
    xAxis: timeAxis(c, tz),
    yAxis: valueAxis(c, "probability", { min: -top, max: top, axisLabel: { color: c.muted, formatter: (v) => pct(Math.abs(v)) } }),
    series,
  });
}

// Up, down and none probabilities stacked, as in the forecast file
export function directionChart(el, rows, { tz }) {
  const c = colors();
  const series = [
    { name: "Up (p_up)", type: "bar", stack: "d", data: rows.map((r) => [r.t, r.up]), itemStyle: { color: c.up }, barWidth: "100%" },
    { name: "Down (p_down)", type: "bar", stack: "d", data: rows.map((r) => [r.t, r.down]), itemStyle: { color: c.down }, barWidth: "100%" },
    { name: "None (p_none)", type: "bar", stack: "d", data: rows.map((r) => [r.t, r.none]), itemStyle: { color: c.muted }, barWidth: "100%" },
  ];
  return draw(el, {
    ...base(c), grid: { left: 62, right: 18, top: 30, bottom: 30 },
    tooltip: { ...base(c).tooltip, valueFormatter: (v) => pct(v, 1) },
    xAxis: timeAxis(c, tz), yAxis: valueAxis(c, "", { min: 0, max: 1, axisLabel: { color: c.muted, formatter: (v) => pct(v) } }), series,
  });
}

// The last hours of published prices leading into the forecast for the coming hour
export function contextChart(el, past, rows, { tz, origin }) {
  const c = colors();
  const spot = window.spotAt;
  const span = [...past.map((p) => p[0]), ...rows.map((r) => r.t)];
  const series = [
    { name: "P10", type: "line", data: rows.map((r) => [r.t, r.p10]), lineStyle: { opacity: 0 }, symbol: "none", stack: "band", stackStrategy: "all", step: "end", tooltip: { show: false } },
    { name: "P10–P90 range", type: "line", data: rows.map((r) => [r.t, r.p90 - r.p10]), lineStyle: { opacity: 0 }, symbol: "none", stack: "band", stackStrategy: "all", step: "end", areaStyle: { color: c.band }, color: c.band, tooltip: { show: false } },
    { name: "Forecast (P50)", type: "line", data: rows.map((r) => [r.t, r.p50]), symbol: "circle", symbolSize: 7, step: "end", lineStyle: { width: 3, color: c.accent }, color: c.accent },
    { name: "Published price", type: "line", data: past, symbol: "none", step: "end", lineStyle: { width: 1.8, color: c.text }, color: c.text,
      markLine: { symbol: "none", silent: true, lineStyle: { color: c.muted, type: "dashed" }, label: { formatter: "now", color: c.muted }, data: [{ xAxis: origin }] } },
  ];
  if (spot) series.push({ name: "Spot price", type: "line", data: span.map((t) => [t, spot(t)]), symbol: "none", step: "end", lineStyle: { width: 1.4, color: c.spot }, color: c.spot });
  return draw(el, {
    ...base(c), grid: { left: 52, right: 18, top: 46, bottom: 34 },
    legend: { ...base(c).legend, data: ["Published price", "Forecast (P50)", "P10–P90 range", ...(spot ? ["Spot price"] : [])] },
    tooltip: { ...base(c).tooltip, valueFormatter: (v) => (v == null ? "–" : `${v.toFixed(1)} €/MWh`) },
    xAxis: timeAxis(c, tz), yAxis: valueAxis(c, "€/MWh", { scale: true }), series,
  });
}

// Hindsight: actual price against forecasts made 1 and 6 hours before
export function trackChart(el, points, { tz }) {
  const c = colors();
  return draw(el, {
    ...base(c),
    xAxis: { ...timeAxis(c, tz), axisLabel: { color: c.muted, formatter: (v) => fmt(v, tz, { day: "numeric", month: "short", hour: "2-digit", hour12: false }), hideOverlap: true } },
    yAxis: valueAxis(c, "€/MWh", { scale: true }),
    dataZoom: [{ type: "inside" }, { type: "slider", height: 16, bottom: 4, borderColor: c.line }],
    grid: { ...base(c).grid, bottom: 50 },
    series: [
      { name: "1 h ahead P10–P90", type: "line", data: points.map((p) => [p.t, p.p10_1]), lineStyle: { opacity: 0 }, symbol: "none", stack: "b", stackStrategy: "all", tooltip: { show: false } },
      { name: "1 h ahead range", type: "line", data: points.map((p) => [p.t, p.p90_1 - p.p10_1]), lineStyle: { opacity: 0 }, symbol: "none", stack: "b", stackStrategy: "all", areaStyle: { color: c.band }, tooltip: { show: false } },
      { name: "Forecast 1 h ahead", type: "line", data: points.map((p) => [p.t, p.p50_1]), symbol: "none", lineStyle: { color: c.accent, width: 1.6 }, color: c.accent },
      { name: "Forecast 6 h ahead", type: "line", data: points.map((p) => [p.t, p.p50_6]), symbol: "none", lineStyle: { color: c.up, width: 1.2, type: "dashed" }, color: c.up },
      { name: "Actual", type: "line", data: points.map((p) => [p.t, p.y]), symbol: "none", lineStyle: { color: c.high, width: 1.4 }, color: c.high },
    ],
    legend: { ...base(c).legend, data: ["Actual", "Forecast 1 h ahead", "Forecast 6 h ahead"] },
    tooltip: { ...base(c).tooltip, valueFormatter: (v) => (v == null ? "–" : v.toFixed(1)) },
  });
}

// Simple bar chart with category labels
export function barChart(el, labels, values, { name, color, format = (v) => v.toFixed(1), horizontal = false }) {
  const c = colors();
  const cat = { type: "category", data: labels, axisLabel: { color: c.muted }, axisLine: { lineStyle: { color: c.line } } };
  const val = valueAxis(c, name);
  return draw(el, {
    ...base(c), legend: { show: false }, grid: horizontal ? { left: 210, right: 30, top: 10, bottom: 24 } : { left: 48, right: 12, top: 28, bottom: 30 },
    tooltip: { ...base(c).tooltip, valueFormatter: format },
    xAxis: horizontal ? val : cat, yAxis: horizontal ? { ...cat, inverse: true } : val,
    series: [{ type: "bar", data: values, itemStyle: { color: color || c.accent, borderRadius: 3 }, barMaxWidth: 26 }],
  });
}

// Calendar heatmap: day by local hour
export function heatmap(el, days, hours, cells, { max, color, name, marks, tz }) {
  const c = colors();
  return draw(el, {
    ...base(c), legend: { show: false },
    grid: { left: 70, right: 70, top: 10, bottom: 40 },
    tooltip: { formatter: (p) => `${days[p.value[1]]} ${String(hours[p.value[0]]).padStart(2, "0")}:00<br>${name}: ${pct(p.value[2], 1)}`,
      backgroundColor: c.panel, borderColor: c.line, textStyle: { color: c.text } },
    xAxis: { type: "category", data: hours.map((h) => String(h).padStart(2, "0")), axisLabel: { color: c.muted }, splitArea: { show: false } },
    yAxis: { type: "category", data: days, axisLabel: { color: c.muted }, inverse: true },
    visualMap: { min: 0, max, calculable: false, orient: "vertical", right: 0, top: "middle", itemHeight: 120,
      inRange: { color: [c.panel, color] }, textStyle: { color: c.muted }, formatter: (v) => pct(v) },
    series: [
      { type: "heatmap", data: cells, itemStyle: { borderColor: c.panel, borderWidth: 1 } },
      ...(marks ? [{ type: "scatter", data: marks, symbol: "circle", symbolSize: 5, itemStyle: { color: c.text }, tooltip: { formatter: "Actual spike" } }] : []),
    ],
  });
}

// Predicted probability against observed frequency
export function reliabilityChart(el, bins, { color }) {
  const c = colors();
  return draw(el, {
    ...base(c), legend: { show: false }, grid: { left: 52, right: 16, top: 16, bottom: 40 },
    tooltip: { trigger: "item", backgroundColor: c.panel, borderColor: c.line, textStyle: { color: c.text },
      formatter: (p) => p.seriesIndex ? `Predicted ${pct(p.value[0])}<br>Observed ${pct(p.value[1])}<br>${p.value[2]} quarter-hours` : "" },
    xAxis: valueAxis(c, "predicted", { min: 0, max: 1, nameLocation: "middle", nameGap: 26, axisLabel: { color: c.muted, formatter: (v) => pct(v) } }),
    yAxis: valueAxis(c, "observed", { min: 0, max: 1, axisLabel: { color: c.muted, formatter: (v) => pct(v) } }),
    series: [
      { type: "line", data: [[0, 0], [1, 1]], symbol: "none", lineStyle: { type: "dashed", color: c.muted } },
      { type: "line", data: bins, symbol: "circle", symbolSize: (v) => 6 + Math.min(14, Math.sqrt(v[2]) / 3), lineStyle: { color }, itemStyle: { color } },
    ],
  });
}

// Half-ring gauge for one probability, with a tick at the typical level
export function gaugeChart(el, value, { color, typical }) {
  const c = colors();
  return draw(el, {
    animation: true, animationDuration: 500,
    series: [{
      type: "gauge", startAngle: 200, endAngle: -20, min: 0, max: 1, radius: "100%", center: ["50%", "72%"],
      progress: { show: true, width: 10, roundCap: true, itemStyle: { color } },
      axisLine: { roundCap: true, lineStyle: { width: 10, color: [[typical, c.line], [typical + 0.004, c.muted], [1, c.line]] } },
      axisTick: { show: false }, splitLine: { show: false }, axisLabel: { show: false }, pointer: { show: false }, anchor: { show: false },
      title: { show: false }, detail: { show: false }, data: [{ value }],
    }],
  });
}

// Small line of the P50 forecast without axes
export function sparkChart(el, rows, { color }) {
  return draw(el, {
    animation: false, grid: { left: 6, right: 6, top: 4, bottom: 4 },
    xAxis: { type: "time", show: false }, yAxis: { type: "value", show: false, scale: true },
    series: [{ type: "line", data: rows.map((r) => [r.t, r.p50]), symbol: "none", smooth: 0.3, lineStyle: { width: 2, color },
      areaStyle: { color: new echarts.graphic.LinearGradient(0, 0, 0, 1, [{ offset: 0, color: color + "55" }, { offset: 1, color: color + "00" }]) } }],
  });
}
