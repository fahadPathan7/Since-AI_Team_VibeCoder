from pathlib import Path

import pandas as pd

# Project folders, all inside this submission folder
ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / "organiser"
DATA = ROOT / "data"
TABLES = DATA
TEAM_WIDE = DATA / "inputs_wide_team.csv"
ARTIFACTS = ROOT / "artifacts"
OUTPUTS = ROOT / "outputs"

# Dates that define the training data and the forecast origins
TRAIN_CUTOFF = pd.Timestamp("2026-10-04T21:00:00Z")
FIRST_ORIGIN = pd.Timestamp("2026-06-03T21:00:00Z")
LAST_ORIGIN = pd.Timestamp("2026-11-01T21:00:00Z")
HORIZON_STEPS = 40
SPIKE_MARGIN = 50.0

# Rolling-origin folds as (training cut-off, end of validation window)
FOLDS = {
    "F1": (pd.Timestamp("2026-07-31T21:00:00Z"), pd.Timestamp("2026-08-16T21:00:00Z")),
    "F2": (pd.Timestamp("2026-08-16T21:00:00Z"), pd.Timestamp("2026-09-06T21:00:00Z")),
    "F3": (pd.Timestamp("2026-09-06T21:00:00Z"), pd.Timestamp("2026-10-04T21:00:00Z")),
}

# Model inputs for the quantile and direction models
CORE = [
    "spot", "spot_dev_day", "spot_drange", "spot_chg_prev_h",
    "net_fc", "wind_fc", "cons_fc", "net_ramp_prev_h",
    "hour", "is_weekend", "step",
    "sp_last", "sp_med_4h", "sp_med_24h", "dir_last", "up_6h", "up_24h",
    "mfrr_up_prem_4h", "mfrr_dn_prem_4h", "cons_err_1h", "net_export",
]

# Extra model inputs for the spike models only
VOL = ["abs_med_24h", "abs_med_72h", "hi_72h", "lo_72h"]
SPIKE_FEATURES = CORE + VOL

# Price model inputs, with or without the faded last spread
PRICE_FEATURES = CORE + ["afrr_up_prem_4h", "afrr_dn_prem_4h"]
PRICE_FEATURES_DECAY = PRICE_FEATURES + ["gap_h", "sp_last_decay", "sp_mix"]
DRIVER_FEATURES = PRICE_FEATURES_DECAY

# Step buckets: each layout trains one model per bucket, and the layouts are averaged
PRICE_LAYOUTS = [
    ([(1, 12), (13, 40)], PRICE_FEATURES),
    ([(1, 4), (5, 12), (13, 40)], PRICE_FEATURES),
    ([(1, 8), (9, 40)], PRICE_FEATURES_DECAY),
    ([(1, 8), (9, 20), (21, 40)], PRICE_FEATURES),
    ([(1, 4), (5, 40)], PRICE_FEATURES),
]
CLASS_LAYOUTS = [[(1, 8), (9, 40)], [(1, 4), (5, 12), (13, 40)], [(1, 8), (9, 20), (21, 40)]]

# Logistic regression uses CORE without the cyclical hour
LOGIT_FEATURES = [c for c in CORE if c != "hour"]

# Reference columns that must never reach a model
REFERENCE = ["origin", "delivery", "data_cutoff", "y_price", "y_spread", "y_dir", "label_fu"]

# Settings shared by every LightGBM model
LGB_SHARED = dict(subsample=0.7, subsample_freq=1, verbose=-1, n_jobs=8)

# Quantile model settings
QUANTILE = dict(objective="quantile", num_leaves=7, min_child_samples=2000, learning_rate=0.03,
                n_estimators=400, extra_trees=True, colsample_bytree=0.5, **LGB_SHARED)

# Spike model and first direction model settings
BINARY_L4 = dict(objective="binary", num_leaves=4, min_child_samples=4000, learning_rate=0.03,
                 n_estimators=150, colsample_bytree=0.6, **LGB_SHARED)

# Second direction model settings
BINARY_XT = dict(objective="binary", num_leaves=7, min_child_samples=2000, learning_rate=0.03,
                 n_estimators=200, extra_trees=True, colsample_bytree=0.5, **LGB_SHARED)

# Remaining fixed design values
LOGIT_C = 0.1
SEEDS = [1, 2, 3, 4, 5]
INTERVAL_SCALE = 1.25

# Smallest leaf size when a bucket scales it down, for quantile, spike and second direction models
MIN_LEAF_FLOOR = {"quantile": 300, "binary_l4": 500, "binary_xt": 300}
PROBABILITY_FLOOR = 1e-4

# Pass limits for the official validation score
GATE_G1 = {"mae_p50": 66.20, "calibration_pinball_mean": 24.18, "brier_spike_mean": 0.1132, "brier_direction": 0.4509}
GATE_G3_MAX = {"mae_p50": 43.0, "calibration_pinball_mean": 12.2, "brier_spike_mean": 0.094, "brier_direction": 0.405}
GATE_G3_COVERAGE = (0.76, 0.84)

# Expected metrics per fold
GATE_G4 = {
    "F1": {"mae": 17.80, "pinball_raw": 4.67, "spike": 0.0220, "direction": 0.4279},
    "F2": {"mae": 35.79, "pinball_raw": 8.13, "spike": 0.1080, "direction": 0.4249},
    "F3": {"mae": 42.33, "pinball_raw": 12.41, "spike": 0.0923, "direction": 0.3987},
}
GATE_G4_TOLERANCE = 0.015
