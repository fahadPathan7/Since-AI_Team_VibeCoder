import json

import numpy as np
import pandas as pd

from dashboard.alerts import build_alerts
from dashboard.settings import DRIVER_NAMES, NO_LEVEL, QUANTILES_FILE
from src.config import SPIKE_MARGIN


# Training-period quartiles of each driver feature, used to say "high" or "low"
def load_quantiles():
    return json.loads(QUANTILES_FILE.read_text())


# A plain phrase for one driver at its current value
def phrase(name, value, quantiles):
    label = DRIVER_NAMES.get(name, name)
    if name == "dir_last":
        return {1: "latest regulation was up", -1: "latest regulation was down"}.get(int(value) if np.isfinite(value) else 0, label)
    if name == "is_weekend":
        return "weekend" if value == 1 else "weekday"
    if name in NO_LEVEL or name not in quantiles["features"] or not np.isfinite(value):
        return label
    low, high = quantiles["features"][name]
    if name == "cons_err_1h":
        return "consumption above forecast" if value > high else "consumption below forecast" if value < low else label
    if name in ("sp_last", "sp_last_decay", "sp_mix", "sp_med_4h", "sp_med_24h"):
        when = {"sp_med_4h": " over the last 4 h", "sp_med_24h": " over the last 24 h"}.get(name, "")
        return f"imbalance price well above spot{when}" if value > high else f"imbalance price well below spot{when}" if value < low else label
    return f"high {label}" if value > high else f"low {label}" if value < low else label


# Driver phrases for every forecast row from its driver names and feature values
def driver_phrases(drivers, features, quantiles):
    names = drivers.str.split(";")
    return [list(dict.fromkeys(phrase(n, float(features[n].iloc[i]) if n in features else np.nan, quantiles) for n in row)) for i, row in enumerate(names)]


# Quarter-hour outcomes used for hindsight views, without spot values
def actual_block(values, usable, start, end):
    window = values.loc[start:end]
    spread = window["fi_imbalance_price"] - window["fi_spot_price"]
    times = usable.loc[start:end, "fi_imbalance_price"]
    known = window["fi_imbalance_price"].notna()
    return {
        "t0": int(window.index[0].value // 10**6),
        "price": [round(float(v), 2) if k else None for v, k in zip(window["fi_imbalance_price"], known)],
        "dir": [int(v) if np.isfinite(v) else None for v in window["fi_mfrr_direction"]],
        "hi": [int(s > SPIKE_MARGIN) if np.isfinite(s) else None for s in spread],
        "lo": [int(s < -SPIKE_MARGIN) if np.isfinite(s) else None for s in spread],
        "usable": [int(t.value // 10**6) if pd.notna(t) else None for t in times],
    }


# The dashboard data for a set of forecasts, shared by the precomputed views and uploaded runs
def build_payload(forecast, features, actuals=None, meta=None, period=None):
    quantiles = load_quantiles()
    forecast = forecast.sort_values(["origin", "step"]).reset_index(drop=True)
    features = features.set_index(["origin", "delivery"]).loc[list(zip(forecast["origin"], forecast["delivery"]))].reset_index(drop=True)
    forecast["phrases"] = driver_phrases(forecast["top_drivers"], features, quantiles)
    forecast["spot"] = features["spot"].to_numpy()
    alerts = build_alerts(forecast, quantiles["base_rates"])
    vocab = sorted({p for row in forecast["phrases"] for p in row})
    index = {p: i for i, p in enumerate(vocab)}
    origins = sorted(forecast["origin"].unique())
    cutoffs = forecast.groupby("origin")["data_cutoff"].first()
    round_to = lambda column, digits: [round(float(v), digits) for v in forecast[column]]
    return {
        "meta": meta or {},
        "steps": int(forecast["step"].max()),
        "origins": [int(pd.Timestamp(o).value // 10**6) for o in origins],
        "cutoffs": [int(cutoffs[o].value // 10**6) for o in origins],
        "period": period or [0] * len(origins),
        "phrases": vocab,
        "f": {
            "p10": round_to("p10", 1), "p50": round_to("p50", 1), "p90": round_to("p90", 1),
            "up": round_to("p_up", 4), "down": round_to("p_down", 4), "none": round_to("p_none", 5),
            "hi": round_to("p_spike_high", 4), "lo": round_to("p_spike_low", 4),
            "drv": [[index[p] for p in row] for row in forecast["phrases"]],
            "names": [row.split(";") for row in forecast["top_drivers"]],
        },
        "alerts": [alerts[o] for o in origins],
        "actual": actuals,
        "base_rates": quantiles["base_rates"],
    }
