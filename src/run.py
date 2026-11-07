import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import time

import joblib
import numpy as np
import pandas as pd

from src.asof import load_data
from src.config import (ARTIFACTS, CORE, DATA, FOLDS, GATE_G1, GATE_G3_COVERAGE, GATE_G3_MAX, GATE_G4, GATE_G4_TOLERANCE,
                        OUTPUTS, PACKAGE, QUANTILE, BINARY_L4, BINARY_XT, CLASS_LAYOUTS, INTERVAL_SCALE, LOGIT_C, MIN_LEAF_FLOOR,
                        PRICE_FEATURES_DECAY, PRICE_LAYOUTS, ROOT, SEEDS,
                        SPIKE_FEATURES, SPIKE_MARGIN, TRAIN_CUTOFF)
from src.features import all_origins, attach_labels, build_features, none_share
from src.models import fit_all, global_importance, p50_contributions, predict_all, top_drivers
from src.submission import postprocess, run_scorer, run_validator, write_forecast


# Build the full labelled table for every origin
def build_table():
    values, usable = load_data()
    rows = attach_labels(build_features(values, usable, all_origins()), values, usable)
    return rows, values, usable


# Rows whose labels were usable at a cut-off
def training_rows(rows, cutoff):
    train = rows[(rows["label_fu"] <= cutoff) & rows["y_price"].notna()]
    assert train["label_fu"].max() <= cutoff, "training label used past its cut-off"
    return train


# Mean pinball loss at one quantile
def pinball(actual, forecast, quantile):
    error = actual - forecast
    return float(np.mean(np.maximum(quantile * error, (quantile - 1) * error)))


# Metrics for rows with usable labels, from unscaled and final forecasts
def fold_metrics(rows, raw, forecast, p_none):
    actual = rows["y_price"].to_numpy()
    spot = rows["spot"].to_numpy()
    low_raw, mid_raw, high_raw = np.sort(np.vstack([spot + raw["q10"], spot + raw["q50"], spot + raw["q90"]]), axis=0)
    spread = rows["y_spread"].to_numpy()
    high, low = (spread > SPIKE_MARGIN).astype(float), (spread < -SPIKE_MARGIN).astype(float)
    up, none = (rows["y_dir"] == 1).astype(float).to_numpy(), (rows["y_dir"] == 0).astype(float).to_numpy()
    down = 1 - up - none
    return {
        "mae": float(np.abs(actual - forecast["p50"]).mean()),
        "pinball_raw": (pinball(actual, low_raw, 0.1) + pinball(actual, high_raw, 0.9)) / 2,
        "pinball": (pinball(actual, forecast["p10"], 0.1) + pinball(actual, forecast["p90"], 0.9)) / 2,
        "coverage": float(((actual >= forecast["p10"]) & (actual <= forecast["p90"])).mean()),
        "spike": (float(((forecast["p_spike_high"] - high) ** 2).mean()) + float(((forecast["p_spike_low"] - low) ** 2).mean())) / 2,
        "direction": float((((forecast["p_up"] - up) ** 2) + ((forecast["p_down"] - down) ** 2) + ((p_none - none) ** 2)).mean()),
    }


# Train and score the three rolling-origin folds
def command_folds():
    rows, values, usable = build_table()
    ARTIFACTS.mkdir(exist_ok=True)
    records, passed = [], True
    for fold, (cutoff, end) in FOLDS.items():
        train = training_rows(rows, cutoff)
        check = rows[(rows["origin"] >= cutoff) & (rows["origin"] < end) & (rows["delivery"] < end) & rows["y_price"].notna()]
        started = time.time()
        models = fit_all(train)
        raw = predict_all(models, check)
        p_none = none_share(values, usable, cutoff)
        forecast = postprocess(raw, check, p_none)
        metrics = fold_metrics(check, raw, forecast, p_none)
        records.append({"fold": fold, "train_rows": len(train), "rows": len(check), "seconds": round(time.time() - started, 1), **metrics})
        for name, expected in GATE_G4[fold].items():
            if abs(metrics[name] / expected - 1) > GATE_G4_TOLERANCE:
                passed = False
                print(f"G4 outside tolerance: {fold} {name} {metrics[name]:.4f}, expected about {expected}")
        pd.concat([check[["origin", "delivery", "step", "y_price"]], forecast], axis=1).to_parquet(ARTIFACTS / f"oof_{fold}.parquet")
    table = pd.DataFrame(records)
    table.to_csv(ARTIFACTS / "fold_metrics.csv", index=False)
    print(table.round(4).to_string(index=False))
    print("G4", "PASS" if passed else "FAIL")
    return 0 if passed else 1


# Score the 7 Sep - 4 Oct forecast with the official validator and scorer
def command_validation():
    rows, values, usable = build_table()
    folder = ARTIFACTS / "validation"
    folder.mkdir(parents=True, exist_ok=True)
    subprocess.run([sys.executable, str(PACKAGE / "make_templates.py"), "--test-start", "2026-09-07", "--test-end", "2026-10-04",
                    "--output-dir", str(folder)], check=True, capture_output=True)
    cutoff, end = FOLDS["F3"]
    train = training_rows(rows, cutoff)
    target = rows[(rows["origin"] >= cutoff) & (rows["origin"] < end)]
    models = fit_all(train)
    raw = predict_all(models, target)
    forecast = postprocess(raw, target, none_share(values, usable, cutoff))
    drivers = top_drivers(p50_contributions(models, target))
    output = folder / "forecast_validation.csv"
    write_forecast(forecast, target, drivers, folder / "sample_submission.csv", output)
    code, report = run_validator(output, folder / "forecast_origins.csv")
    print(report.splitlines()[0])
    if code:
        print(report)
        return 1
    score = run_scorer(output, DATA / "actuals_validation.csv", folder / "score")
    return report_gate_g3(score)


# Compare the official validation score with the G3 limits
def report_gate_g3(score):
    passed = True
    for metric, limit in GATE_G3_MAX.items():
        ok = float(score[metric]) <= limit
        passed &= ok
        print(f"{metric}: {float(score[metric]):.4f} (limit {limit}) {'ok' if ok else 'FAIL'}")
    coverage = float(score["coverage_p10_p90"])
    ok = GATE_G3_COVERAGE[0] <= coverage <= GATE_G3_COVERAGE[1]
    passed &= ok
    print(f"coverage: {coverage:.4f} (range {GATE_G3_COVERAGE}) {'ok' if ok else 'FAIL'}")
    print("G3", "PASS" if passed else "FAIL")
    return 0 if passed else 1


# SHA-256 of a file
def file_hash(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


# Record exactly what produced the final forecast
def write_manifest(train, target, p_none):
    source = {str(path.relative_to(ROOT)): file_hash(path) for path in sorted((ROOT / "src").glob("*.py"))}
    data = {name: file_hash(DATA / name) for name in ["inputs.parquet", "spot_nordpool.csv", "inputs_wide.csv", "inputs_usable.csv"]}
    manifest = {
        "created_utc": pd.Timestamp.now(tz="UTC").isoformat(),
        "train_cutoff": TRAIN_CUTOFF.isoformat(),
        "train_rows": int(len(train)),
        "last_training_label_usable": train["label_fu"].max().isoformat(),
        "last_training_delivery": train["delivery"].max().isoformat(),
        "forecast_rows": int(len(target)),
        "p_none": p_none,
        "seeds": SEEDS,
        "core_features": CORE,
        "spike_features": SPIKE_FEATURES,
        "price_features": PRICE_FEATURES_DECAY,
        "price_layouts": [[list(bucket) for bucket in buckets] + [features[-1]] for buckets, features in PRICE_LAYOUTS],
        "class_layouts": [[list(bucket) for bucket in buckets] for buckets in CLASS_LAYOUTS],
        "min_leaf_floor": MIN_LEAF_FLOOR,
        "quantile_settings": QUANTILE,
        "binary_l4_settings": BINARY_L4,
        "binary_xt_settings": BINARY_XT,
        "logit_c": LOGIT_C,
        "interval_scale": INTERVAL_SCALE,
        "source_sha256": source,
        "data_sha256": data,
    }
    (ARTIFACTS / "run_manifest.json").write_text(json.dumps(manifest, indent=2))


# Fit on all usable labels once, forecast the 673 test origins and validate the file
def command_final():
    rows, values, usable = build_table()
    train = training_rows(rows, TRAIN_CUTOFF)
    origins = pd.to_datetime(pd.read_csv(PACKAGE / "forecast_origins.csv")["forecast_origin_utc"], utc=True)
    target = rows[rows["origin"].isin(origins)]
    assert len(target) == 26920, "unexpected number of forecast rows"
    assert target["y_price"].notna().sum() == 0, "test-period labels reached the forecast rows"
    models = fit_all(train)
    raw = predict_all(models, target)
    p_none = none_share(values, usable)
    forecast = postprocess(raw, target, p_none)
    contributions = p50_contributions(models, target)
    output = OUTPUTS / "forecast_backtest.csv"
    write_forecast(forecast, target, top_drivers(contributions), PACKAGE / "sample_submission.csv", output)
    global_importance(contributions).to_csv(OUTPUTS / "global_drivers.csv", index=False)
    (ARTIFACTS / "models").mkdir(parents=True, exist_ok=True)
    joblib.dump(models, ARTIFACTS / "models" / "final_models.joblib")
    write_manifest(train, target, p_none)
    code, report = run_validator(output, PACKAGE / "forecast_origins.csv")
    print(report)
    print(f"Training rows {len(train)}, last delivery {train['delivery'].max()}, p_none {p_none:.6f}")
    print("G5", "PASS" if code == 0 else "FAIL")
    return code


# Run the organisers' baseline notebook on a copy, keeping the package unchanged
def command_baseline():
    folder = ARTIFACTS / "baseline_package"
    if folder.exists():
        shutil.rmtree(folder)
    folder.mkdir(parents=True)
    for name in ["baseline.ipynb", "make_templates.py", "validate_submission.py", "score.py", "forecast_origins.csv", "sample_submission.csv"]:
        shutil.copy(PACKAGE / name, folder / name)
    os.symlink(DATA.resolve(), folder / "data")
    subprocess.run([sys.executable, "-m", "nbconvert", "--to", "notebook", "--execute", "--inplace", "--ExecutePreprocessor.timeout=900",
                    "baseline.ipynb"], check=True, cwd=folder, capture_output=True)
    kept = ARTIFACTS / "baseline_score"
    if kept.exists():
        shutil.rmtree(kept)
    shutil.copytree(folder / "baseline_output" / "validation" / "score", kept)
    score = pd.read_csv(kept / "score_summary.csv").iloc[0]
    shutil.rmtree(folder)
    passed = True
    for metric, expected in GATE_G1.items():
        ok = round(float(score[metric]), 4 if expected < 1 else 2) == expected
        passed &= ok
        print(f"{metric}: {float(score[metric]):.4f} (expected {expected}) {'ok' if ok else 'FAIL'}")
    print("G1", "PASS" if passed else "FAIL")
    return 0 if passed else 1


# Command-line entry point
def main():
    commands = {"baseline": command_baseline, "folds": command_folds, "validation": command_validation, "final": command_final}
    parser = argparse.ArgumentParser(description="Turku Energia imbalance price forecast")
    parser.add_argument("command", choices=sorted(commands))
    return commands[parser.parse_args().command]()


if __name__ == "__main__":
    sys.exit(main())
