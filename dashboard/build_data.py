import json

import numpy as np
import pandas as pd

from dashboard.payload import actual_block, build_payload
from dashboard.settings import ALERTS, QUANTILES_FILE, WEB_DATA
from src.asof import load_data
from src.config import ARTIFACTS, DRIVER_FEATURES, OUTPUTS, SPIKE_MARGIN, TRAIN_CUTOFF
from src.features import all_origins, attach_labels, build_features

PERIODS = [
    {"name": "Validation", "file": ARTIFACTS / "validation" / "forecast_validation.csv",
     "model": "Trained on data usable by 6 Sep, so this period is out of sample"},
    {"name": "Test", "file": OUTPUTS / "forecast_backtest.csv",
     "model": "Final model, trained on data usable by 4 Oct; this is the submitted forecast"},
]


# Training-period quartiles of the driver features and the training spike rates
def write_quantiles(values, usable):
    rows = attach_labels(build_features(values, usable, all_origins()), values, usable)
    train = rows[rows["y_price"].notna() & (rows["label_fu"] <= TRAIN_CUTOFF)]
    features = {name: [float(train[name].quantile(0.25)), float(train[name].quantile(0.75))] for name in DRIVER_FEATURES}
    base = {"high": float((train["y_spread"] > SPIKE_MARGIN).mean()), "low": float((train["y_spread"] < -SPIKE_MARGIN).mean())}
    QUANTILES_FILE.write_text(json.dumps({"features": features, "base_rates": base}, indent=1))


# A submission-format forecast file as typed rows
def read_forecast(path):
    table = pd.read_csv(path)
    return pd.DataFrame({
        "origin": pd.to_datetime(table["forecast_origin_utc"], utc=True),
        "delivery": pd.to_datetime(table["delivery_start_utc"], utc=True),
        "step": table["step"], "data_cutoff": pd.to_datetime(table["data_cutoff_utc"], utc=True),
        **{c: table[c] for c in ["p10", "p50", "p90", "p_up", "p_down", "p_none", "p_spike_high", "p_spike_low", "top_drivers"]},
    })


# How often each alert is shown per update and how often its event followed, against the overall rate
def alert_stats(payload, values):
    spread = values["fi_imbalance_price"] - values["fi_spot_price"]
    events = {"spike_high": spread > SPIKE_MARGIN, "spike_low": spread < -SPIKE_MARGIN, "direction_up": values["fi_mfrr_direction"] == 1}
    stats = []
    for period, name in enumerate(p["name"] for p in PERIODS):
        picks = [i for i, p in enumerate(payload["period"]) if p == period]
        start = pd.Timestamp(payload["origins"][picks[0]], unit="ms", tz="UTC")
        end = pd.Timestamp(payload["origins"][picks[-1]], unit="ms", tz="UTC") + pd.Timedelta(hours=10)
        for kind in ["spike_high", "spike_low", "direction_up", "conflict", "moved", "uncertainty"]:
            shown = [a for i in picks for a in payload["alerts"][i] if a["kind"] == kind]
            row = {"period": name, "kind": kind, "per_update": round(len(shown) / len(picks), 2), "inside": None, "overall": None, "window_hit": None}
            if kind in events and shown:
                inside = [bool(events[kind].loc[pd.Timestamp(t, unit="ms", tz="UTC")]) for a in shown for t in range(a["start"], a["end"], 900000)]
                hits = [bool(events[kind].loc[pd.Timestamp(a["start"], unit="ms", tz="UTC"):pd.Timestamp(a["end"] - 1, unit="ms", tz="UTC")].any()) for a in shown]
                row.update(inside=round(float(np.mean(inside)), 3), overall=round(float(events[kind].loc[start:end].mean()), 3), window_hit=round(float(np.mean(hits)), 3))
            stats.append(row)
    return stats


# Precompute the dashboard data for the validation and test periods
def main():
    values, usable = load_data()
    write_quantiles(values, usable)
    frames = [read_forecast(p["file"]) for p in PERIODS]
    forecast = pd.concat(frames, ignore_index=True)
    features = build_features(values, usable, pd.DatetimeIndex(sorted(forecast["origin"].unique())))
    period_of = {o: i for i, frame in enumerate(frames) for o in frame["origin"].unique()}
    origins = sorted(forecast["origin"].unique())
    actuals = actual_block(values, usable, origins[0] - pd.Timedelta(days=31), forecast["delivery"].max())
    importance = pd.read_csv(OUTPUTS / "global_drivers.csv")
    meta = {
        "title": "Validation and test periods",
        "source": "precomputed",
        "periods": [{"name": p["name"], "model": p["model"], "from": int(f["origin"].min().value // 10**6),
                     "to": int(f["origin"].max().value // 10**6)} for p, f in zip(PERIODS, frames)],
        "importance": importance.round(4).to_dict(orient="records"),
        "thresholds": ALERTS,
    }
    payload = build_payload(forecast, features, actuals, meta, [period_of[o] for o in origins])
    payload["meta"]["alert_stats"] = alert_stats(payload, values)
    WEB_DATA.mkdir(parents=True, exist_ok=True)
    path = WEB_DATA / "dashboard.json"
    path.write_text(json.dumps(payload, separators=(",", ":"), allow_nan=False))
    print(f"Wrote {path} ({path.stat().st_size / 1e6:.1f} MB), {len(origins)} origins")
    print(pd.DataFrame(payload["meta"]["alert_stats"]).to_string(index=False))


if __name__ == "__main__":
    main()
