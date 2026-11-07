import os
from pathlib import Path

# Folders, all inside the submission folder
ROOT = Path(__file__).resolve().parents[1]
DASHBOARD = ROOT / "dashboard"
WEB = DASHBOARD / "web"
WEB_DATA = WEB / "data"
MODEL_FILE = ROOT / "artifacts" / "models" / "final_models.joblib"
MANIFEST_FILE = ROOT / "artifacts" / "run_manifest.json"
QUANTILES_FILE = DASHBOARD / "feature_quantiles.json"
RUNS = Path(os.environ.get("RUNS_DIR", DASHBOARD / "runs"))

# Settings that switch the API between local use and AWS
RUNS_BUCKET = os.environ.get("RUNS_BUCKET", "")
ORIGIN_SECRET = os.environ.get("ORIGIN_SECRET", "")
UPLOAD_LIMIT_MB = 200
MAX_ORIGINS = 2000

# Columns every uploaded long-format file must have
LONG_COLUMNS = ["series_id", "timestamp_utc", "value", "first_usable_origin_utc"]
ORIGIN_COLUMN = "forecast_origin_utc"

# Series the model reads, with a plain description for error messages
REQUIRED_SERIES = {
    "fi_imbalance_price": "Finnish imbalance price (Fingrid 319)",
    "fi_spot_price": "Finnish day-ahead spot price (Nord Pool, usually in spot_nordpool.csv)",
    "fi_mfrr_direction": "dominant mFRR direction (Fingrid 369)",
    "fi_mfrr_up_price": "mFRR up-regulation price",
    "fi_mfrr_down_price": "mFRR down-regulation price",
    "fi_afrr_up_price": "aFRR up-regulation price",
    "fi_afrr_down_price": "aFRR down-regulation price",
    "fi_consumption": "measured consumption",
    "fi_consumption_fc_da": "day-ahead consumption forecast",
    "fi_wind_fc_da": "day-ahead wind power forecast",
    "fi_solar_fc_da": "day-ahead solar power forecast",
    "fi_se1_flow": "cross-border flow FI-SE1",
    "fi_se3_flow": "cross-border flow FI-SE3",
    "fi_no4_flow": "cross-border flow FI-NO4",
    "fi_ee_flow": "cross-border flow FI-EE",
    "cal_hour_local": "local hour (calendar)",
    "cal_weekday_local": "local weekday (calendar)",
}

# Series that must be published for every delivery quarter-hour at the origin
DELIVERY_SERIES = ["fi_spot_price", "fi_consumption_fc_da", "fi_wind_fc_da", "fi_solar_fc_da"]
HISTORY_HOURS = 72

# Alert rules, tuned once on the validation period to about three windows a day and then frozen
ALERTS = {
    "spike_high": 0.25,
    "spike_low": 0.35,
    "spike_rise": 0.10,
    "direction_up": 0.60,
    "moved_eur": 25.0,
    "uncertainty_percentile": 0.95,
    "conflict_gap_eur": 20.0,
    "min_quarters": 2,
    "merge_gap": 4,
}

# Plain-language names of the model inputs, used for drivers
DRIVER_NAMES = {
    "spot": "spot price level",
    "spot_dev_day": "spot price against its daily average",
    "spot_drange": "daily spot price range",
    "spot_chg_prev_h": "spot price change from the previous hour",
    "net_fc": "net demand forecast",
    "wind_fc": "wind power forecast",
    "cons_fc": "consumption forecast",
    "net_ramp_prev_h": "net demand ramp",
    "hour": "time of day",
    "is_weekend": "weekend or weekday",
    "step": "forecast horizon",
    "sp_last": "latest imbalance price gap to spot",
    "sp_med_4h": "imbalance price gap to spot, last 4 h",
    "sp_med_24h": "imbalance price gap to spot, last 24 h",
    "dir_last": "latest regulation direction",
    "up_6h": "share of up-regulation, last 6 h",
    "up_24h": "share of up-regulation, last 24 h",
    "mfrr_up_prem_4h": "recent mFRR up-regulation premium",
    "mfrr_dn_prem_4h": "recent mFRR down-regulation premium",
    "afrr_up_prem_4h": "recent aFRR up-regulation premium",
    "afrr_dn_prem_4h": "recent aFRR down-regulation premium",
    "cons_err_1h": "consumption against its forecast",
    "net_export": "cross-border net flow",
    "gap_h": "age of the latest data",
    "sp_last_decay": "latest gap to spot, fading with horizon",
    "sp_mix": "latest gap to spot, fading with horizon",
}
NO_LEVEL = {"hour", "is_weekend", "step", "dir_last", "gap_h"}
