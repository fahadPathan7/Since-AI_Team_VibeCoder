import json
import subprocess
import sys
import tempfile
from functools import lru_cache
from pathlib import Path

import joblib
import numpy as np
import pandas as pd

from dashboard import inputs as checks
from dashboard.payload import actual_block, build_payload
from dashboard.settings import MANIFEST_FILE, MODEL_FILE
from src.config import PACKAGE
from src.features import build_features
from src.models import p50_contributions, predict_all, top_drivers
from src.submission import postprocess

TIME_FORMAT = "%Y-%m-%dT%H:%M:%SZ"
COLUMNS = ["forecast_origin_utc", "delivery_start_utc", "step", "p10", "p50", "p90", "p_up", "p_down", "p_none",
           "p_spike_high", "p_spike_low", "data_cutoff_utc", "top_drivers"]


# The final models and the training "none" share, loaded once per process
@lru_cache(maxsize=1)
def model():
    return joblib.load(MODEL_FILE), json.loads(MANIFEST_FILE.read_text())["p_none"]


# Forecast rows in the official 13-column format
def forecast_table(rows, forecast, drivers):
    return pd.DataFrame({
        "forecast_origin_utc": rows["origin"].dt.strftime(TIME_FORMAT).to_numpy(),
        "delivery_start_utc": rows["delivery"].dt.strftime(TIME_FORMAT).to_numpy(),
        "step": rows["step"].to_numpy(),
        "p10": forecast["p10"].round(3).to_numpy(), "p50": forecast["p50"].round(3).to_numpy(), "p90": forecast["p90"].round(3).to_numpy(),
        "p_up": forecast["p_up"].round(6).to_numpy(), "p_down": forecast["p_down"].round(6).to_numpy(), "p_none": forecast["p_none"].round(6).to_numpy(),
        "p_spike_high": forecast["p_spike_high"].round(6).to_numpy(), "p_spike_low": forecast["p_spike_low"].round(6).to_numpy(),
        "data_cutoff_utc": rows["data_cutoff"].dt.strftime(TIME_FORMAT).to_numpy(),
        "top_drivers": drivers,
    })[COLUMNS]


# Run an organiser script on files in a temporary folder and return its exit code and text
def organiser(script, *args):
    result = subprocess.run([sys.executable, str(PACKAGE / script), *map(str, args)], capture_output=True, text=True)
    return result.returncode, (result.stdout + result.stderr).strip()


# Official validator and, when outcomes are in the data, the official scorer
def official_checks(table, origins, actuals, folder):
    folder = Path(folder)
    forecast_path, origins_path = folder / "forecast_backtest.csv", folder / "forecast_origins.csv"
    table.to_csv(forecast_path, index=False, lineterminator="\n")
    pd.DataFrame({"forecast_origin_utc": origins.strftime(TIME_FORMAT)}).to_csv(origins_path, index=False)
    code, report = organiser("validate_submission.py", "--backtest", forecast_path, "--origins", origins_path)
    result = {"validator_passed": code == 0, "validator_report": report, "score": None}
    scored = actuals[actuals["delivery_start_utc"].isin(table["delivery_start_utc"])]
    if code == 0 and len(scored):
        actuals_path = folder / "actuals.csv"
        scored.to_csv(actuals_path, index=False)
        code, text = organiser("score.py", "--submission", forecast_path, "--actuals", actuals_path, "--spike-margin", 50, "--output-dir", folder / "score")
        if code == 0:
            summary = pd.read_csv(folder / "score" / "score_summary.csv").iloc[0]
            keys = ["rows_scored_price", "mae_p50", "calibration_pinball_mean", "coverage_p10_p90", "brier_spike_mean", "brier_direction"]
            result["score"] = {k: float(summary[k]) for k in keys}
    return result


# Forecast every origin the uploaded data supports and build the dashboard data for it
def run_forecast(inputs_file, spot_file=None, origins_file=None, origin_range=None, progress=lambda text: None):
    progress("Checking the inputs file")
    long = checks.check_long(inputs_file[0], checks.read_table(*inputs_file))
    spot = None
    if spot_file:
        progress("Checking the spot file")
        spot = checks.check_long(spot_file[0], checks.read_table(*spot_file))
    long = checks.combine(long, spot)
    progress("Building the as-of tables")
    values, usable = checks.wide_tables(long)
    origins = checks.read_origins(*origins_file) if origins_file else checks.origin_range(*origin_range)
    keep, skipped = checks.usable_origins(values, usable, origins)
    if len(keep) == 0:
        raise checks.InputError("None of the origins can be forecast with this data. " + "; ".join(f"{o:%Y-%m-%dT%H:%M:%SZ}: {r}" for o, r in skipped[:3]))
    progress(f"Building features for {len(keep)} origins")
    rows = build_features(values, usable, keep).reset_index(drop=True)
    progress("Running the models")
    models, p_none = model()
    raw = predict_all(models, rows)
    forecast = postprocess(raw, rows, p_none)
    drivers = top_drivers(p50_contributions(models, rows))
    table = forecast_table(rows, forecast, drivers)
    progress("Running the official validator")
    actuals = checks.actuals_from(values, usable)
    with tempfile.TemporaryDirectory() as folder:
        official = official_checks(table, keep, actuals, folder)
    progress("Preparing the dashboard")
    frame = pd.concat([rows[["origin", "delivery", "step", "data_cutoff"]], forecast], axis=1)
    frame["top_drivers"] = drivers
    end = rows["delivery"].max()
    block = actual_block(values, usable, rows["origin"].min() - pd.Timedelta(days=31), end) if values["fi_imbalance_price"].notna().any() else None
    meta = {"title": "Uploaded data", "source": "upload", "origins": len(keep), "skipped": len(skipped)}
    payload = build_payload(frame, rows, block, meta)
    report = {
        "origins_requested": len(origins), "origins_forecast": len(keep),
        "skipped": [{"origin": o.strftime(TIME_FORMAT), "reason": r} for o, r in skipped[:200]],
        "series": int(long["series_id"].nunique()),
        "data_from": values.index[0].strftime(TIME_FORMAT), "data_to": values.index[-1].strftime(TIME_FORMAT),
        **official,
    }
    return table, payload, report
