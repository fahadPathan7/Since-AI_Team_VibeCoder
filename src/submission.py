import subprocess
import sys

import numpy as np
import pandas as pd

from src.config import INTERVAL_SCALE, PACKAGE, PROBABILITY_FLOOR

TIME_FORMAT = "%Y-%m-%dT%H:%M:%SZ"


# Turn raw model outputs into valid forecast columns
def postprocess(raw, rows, p_none):
    spot = rows["spot"].to_numpy()
    p10, p50, p90 = np.sort(np.vstack([spot + raw["q10"], spot + raw["q50"], spot + raw["q90"]]), axis=0)
    p10 = p50 - INTERVAL_SCALE * (p50 - p10)
    p90 = p50 + INTERVAL_SCALE * (p90 - p50)
    high = np.clip(raw["p_high"].to_numpy(), PROBABILITY_FLOOR, 1 - PROBABILITY_FLOOR)
    low = np.clip(raw["p_low"].to_numpy(), PROBABILITY_FLOOR, 1 - PROBABILITY_FLOOR)
    up = np.clip(raw["p_up_raw"].to_numpy(), PROBABILITY_FLOOR, 1 - PROBABILITY_FLOOR)
    total = high + low
    high, low = np.where(total > 1, high / total, high), np.where(total > 1, low / total, low)
    return pd.DataFrame({
        "p10": p10, "p50": p50, "p90": p90,
        "p_up": up * (1 - p_none), "p_down": (1 - up) * (1 - p_none), "p_none": p_none,
        "p_spike_high": high, "p_spike_low": low,
    }, index=rows.index)


# Fill the organiser template so its rows and column order are kept
def write_forecast(forecast, rows, drivers, template_path, output_path):
    template = pd.read_csv(template_path, dtype=str, keep_default_na=False)
    filled = pd.DataFrame({
        "forecast_origin_utc": rows["origin"].dt.strftime(TIME_FORMAT),
        "delivery_start_utc": rows["delivery"].dt.strftime(TIME_FORMAT),
        "step": rows["step"],
        "p10": forecast["p10"].round(3), "p50": forecast["p50"].round(3), "p90": forecast["p90"].round(3),
        "p_up": forecast["p_up"].round(6), "p_down": forecast["p_down"].round(6), "p_none": forecast["p_none"].round(6),
        "p_spike_high": forecast["p_spike_high"].round(6), "p_spike_low": forecast["p_spike_low"].round(6),
        "data_cutoff_utc": rows["data_cutoff"].dt.strftime(TIME_FORMAT),
        "top_drivers": drivers,
    })
    keys = template[["forecast_origin_utc", "delivery_start_utc", "step"]].astype({"step": int})
    merged = keys.merge(filled, on=["forecast_origin_utc", "delivery_start_utc", "step"], how="left", validate="one_to_one")
    assert merged.drop(columns=["top_drivers"]).notna().all(axis=None), "template rows without a forecast"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    merged[list(template.columns)].to_csv(output_path, index=False, lineterminator="\n")


# Run the organisers' validator on a forecast file
def run_validator(forecast_path, origins_path):
    result = subprocess.run(
        [sys.executable, str(PACKAGE / "validate_submission.py"), "--backtest", str(forecast_path), "--origins", str(origins_path)],
        capture_output=True, text=True,
    )
    return result.returncode, result.stdout + result.stderr


# Run the organisers' scorer and return its summary row
def run_scorer(forecast_path, actuals_path, output_dir, baseline_summary=None):
    command = [sys.executable, str(PACKAGE / "score.py"), "--submission", str(forecast_path), "--actuals", str(actuals_path),
               "--spike-margin", "50", "--output-dir", str(output_dir)]
    if baseline_summary:
        command += ["--baseline-summary", str(baseline_summary)]
    subprocess.run(command, check=True, capture_output=True, text=True)
    return pd.read_csv(output_dir / "score_summary.csv").iloc[0]
