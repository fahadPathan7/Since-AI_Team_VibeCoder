from collections import Counter

import numpy as np
import pandas as pd

from dashboard.settings import ALERTS

LOCAL = "Europe/Helsinki"
ORDER = {"spike_high": 0, "spike_low": 1, "conflict": 2, "direction_up": 3, "moved": 4, "uncertainty": 5}

# Suggestions to review for each alert, never instructions
REVIEW = {
    "spike_high": ["Check the production plan and the market position for this window",
                   "Consider whether flexible capacity could be offered for up-regulation",
                   "A short position left open into this window could be settled at a high price"],
    "spike_low": ["Check whether flexible consumption, such as electric boilers, could be increased",
                  "Consider whether production could be reduced or offered for down-regulation",
                  "A long position left open into this window could be settled at a low price"],
    "direction_up": ["The system is likely to be short of power: worth checking the position and the production plan",
                     "Up-regulation usually prices above spot"],
    "moved": ["Plans made on the forecast an hour earlier may need a re-check"],
    "uncertainty": ["The model is less sure than usual: keep a margin and recheck at the next update"],
    "conflict": ["The direction and price models disagree: worth an expert review before acting"],
}


# Local clock time of a UTC timestamp
def clock(t):
    return t.tz_convert(LOCAL).strftime("%H:%M")


# Runs of flagged quarter-hours with a minimum length, joining runs separated by a short gap
def runs(flags, minimum):
    found, start = [], None
    for i, flag in enumerate(list(flags) + [False]):
        if flag and start is None:
            start = i
        if not flag and start is not None:
            if i - start >= minimum:
                found.append((start, i))
            start = None
    merged = []
    for s, e in found:
        if merged and s - merged[-1][1] <= ALERTS["merge_gap"]:
            merged[-1] = (merged[-1][0], e)
        else:
            merged.append((s, e))
    return merged


# The three driver phrases seen most often in a window
def window_drivers(phrases):
    counts = Counter(p for row in phrases for p in row)
    return [p for p, _ in counts.most_common(3)]


# One alert as shown to the user
def make_alert(kind, rows, start, end, title, message, peak):
    deliveries = rows["delivery"].iloc[start:end]
    return {
        "kind": kind,
        "start": int(deliveries.iloc[0].value // 10**6),
        "end": int((deliveries.iloc[-1] + pd.Timedelta(minutes=15)).value // 10**6),
        "steps": [int(rows["step"].iloc[start]), int(rows["step"].iloc[end - 1])],
        "peak": round(float(peak), 3),
        "title": title,
        "message": message,
        "drivers": window_drivers(rows["phrases"].iloc[start:end]),
        "review": REVIEW[kind],
    }


# Alerts for one origin from its forecast rows, the previous origin's rows and the recent interval widths
def origin_alerts(rows, previous, width_limit, typical):
    rows = rows.sort_values("step").reset_index(drop=True)
    span = lambda s, e: f"{clock(rows['delivery'].iloc[s])}–{clock(rows['delivery'].iloc[e - 1] + pd.Timedelta(minutes=15))}"
    alerts = []
    prev = previous.set_index("delivery") if previous is not None else None
    prev_high = rows["delivery"].map(prev["p_spike_high"]).to_numpy() if prev is not None else np.full(len(rows), np.nan)
    prev_low = rows["delivery"].map(prev["p_spike_low"]).to_numpy() if prev is not None else np.full(len(rows), np.nan)
    prev_mid = rows["delivery"].map(prev["p50"]).to_numpy() if prev is not None else np.full(len(rows), np.nan)
    width = (rows["p90"] - rows["p10"]).to_numpy()
    uncertain = width >= width_limit if np.isfinite(width_limit) else np.zeros(len(rows), bool)

    # Exceptional price risk, high and low
    for kind, column, prev_p, limit, word, base in [
        ("spike_high", "p_spike_high", prev_high, ALERTS["spike_high"], "high", typical["high"]),
        ("spike_low", "p_spike_low", prev_low, ALERTS["spike_low"], "low", typical["low"]),
    ]:
        p = rows[column].to_numpy()
        risen = (p - np.nan_to_num(prev_p, nan=p)) >= ALERTS["spike_rise"]
        for s, e in runs(p >= limit, 1):
            peak = p[s:e].max()
            change = " The risk has increased since the forecast an hour earlier." if risen[s:e].any() else ""
            unsure = " The forecast is also very uncertain." if uncertain[s:e].any() else ""
            drivers = ", ".join(window_drivers(rows["phrases"].iloc[s:e]))
            side = "above" if word == "high" else "below"
            message = (f"Risk of a price spike more than 50 €/MWh {side} spot for {span(s, e)}: up to {peak:.0%} per quarter-hour, "
                       f"against a typical {base:.0%}.{change}{unsure} Main drivers: {drivers}.")
            alerts.append(make_alert(kind, rows, s, e, f"Spike risk {side} spot {span(s, e)}", message, peak))

    # Expected up-regulation
    up = rows["p_up"].to_numpy()
    for s, e in runs(up >= ALERTS["direction_up"], ALERTS["min_quarters"]):
        drivers = ", ".join(window_drivers(rows["phrases"].iloc[s:e]))
        message = f"Up-regulation is likely for {span(s, e)}, up to {up[s:e].max():.0%}. Main drivers: {drivers}."
        alerts.append(make_alert("direction_up", rows, s, e, f"Up-regulation expected {span(s, e)}", message, up[s:e].max()))

    # Direction and price models pointing different ways
    gap = (rows["p50"] - rows["spot"]).to_numpy()
    down = rows["p_down"].to_numpy()
    conflict = ((up >= ALERTS["direction_up"]) & (gap < 0)) | ((down >= ALERTS["direction_up"]) & (gap > ALERTS["conflict_gap_eur"]))
    for s, e in runs(conflict, ALERTS["min_quarters"]):
        side = "up" if up[s:e].mean() >= 0.5 else "down"
        message = (f"Conflicting signals for {span(s, e)}: the direction model expects {side}-regulation, but the price model "
                   f"puts the price on the other side of spot.")
        alerts.append(make_alert("conflict", rows, s, e, f"Conflicting signals {span(s, e)}", message, max(up[s:e].max(), down[s:e].max())))

    # Material change since the forecast an hour earlier
    moved = np.abs(rows["p50"].to_numpy() - prev_mid)
    for s, e in runs(np.nan_to_num(moved) >= ALERTS["moved_eur"], ALERTS["min_quarters"]):
        sign = "up" if np.nanmean(rows["p50"].to_numpy()[s:e] - prev_mid[s:e]) > 0 else "down"
        message = f"The price forecast for {span(s, e)} moved {sign} by up to {np.nanmax(moved[s:e]):.0f} €/MWh since the forecast an hour earlier."
        alerts.append(make_alert("moved", rows, s, e, f"Forecast moved {sign} {span(s, e)}", message, np.nanmax(moved[s:e])))

    # Unusually wide interval
    for s, e in runs(uncertain, ALERTS["min_quarters"]):
        message = (f"Unusually high uncertainty for {span(s, e)}: the P10–P90 range is up to {width[s:e].max():.0f} €/MWh wide, "
                   f"wider than {ALERTS['uncertainty_percentile']:.0%} of forecasts in the past week.")
        alerts.append(make_alert("uncertainty", rows, s, e, f"High uncertainty {span(s, e)}", message, width[s:e].max()))
    return sorted(alerts, key=lambda a: (ORDER[a["kind"]], a["start"]))


# Alerts for every origin; each origin sees only forecasts made at or before it
def build_alerts(forecast, typical):
    forecast = forecast.sort_values(["origin", "step"])
    groups = {origin: rows for origin, rows in forecast.groupby("origin", sort=True)}
    origins = sorted(groups)
    widths = pd.Series({o: (groups[o]["p90"] - groups[o]["p10"]).to_numpy() for o in origins})
    result = {}
    for i, origin in enumerate(origins):
        history = [w for o, w in widths.items() if origin - pd.Timedelta(days=7) < o <= origin]
        limit = np.quantile(np.concatenate(history), ALERTS["uncertainty_percentile"]) if len(history) >= 24 else np.inf
        previous = groups.get(origin - pd.Timedelta(hours=1))
        result[origin] = origin_alerts(groups[origin], previous, limit, typical)
    return result
