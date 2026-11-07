import numpy as np
import pandas as pd

from src.asof import assert_published, assert_usable_at, asof_index
from src.config import FIRST_ORIGIN, HORIZON_STEPS, LAST_ORIGIN, SPIKE_MARGIN, TRAIN_CUTOFF

PRICE_SOURCES = ["fi_imbalance_price", "fi_spot_price", "fi_mfrr_direction", "fi_mfrr_up_price", "fi_mfrr_down_price",
                 "fi_afrr_up_price", "fi_afrr_down_price"]
SYSTEM_SOURCES = ["fi_consumption", "fi_consumption_fc_da", "fi_se3_flow", "fi_no4_flow", "fi_se1_flow", "fi_ee_flow"]
DELIVERY_SOURCES = ["fi_spot_price", "fi_consumption_fc_da", "fi_wind_fc_da", "fi_solar_fc_da"]


# Backward-looking rolling statistic on the delivery grid
def rolling(series, window, how="mean"):
    return getattr(series.rolling(window, min_periods=max(1, window // 4)), how)()


# Price and balancing state, computed per delivery row from that row and earlier rows
def price_state(values):
    spot = values["fi_spot_price"]
    spread = values["fi_imbalance_price"] - spot
    direction = values["fi_mfrr_direction"]
    absolute = spread.abs()
    high = (spread > SPIKE_MARGIN).astype(float).where(spread.notna())
    low = (spread < -SPIKE_MARGIN).astype(float).where(spread.notna())
    up = (direction == 1).astype(float).where(direction.notna())
    return {
        "sp_last": spread,
        "sp_med_4h": rolling(spread, 16, "median"),
        "sp_med_24h": rolling(spread, 96, "median"),
        "dir_last": direction,
        "up_6h": rolling(up, 24),
        "up_24h": rolling(up, 96),
        "mfrr_up_prem_4h": rolling(values["fi_mfrr_up_price"] - spot, 16, "median"),
        "mfrr_dn_prem_4h": rolling(values["fi_mfrr_down_price"] - spot, 16, "median"),
        "afrr_up_prem_4h": rolling(values["fi_afrr_up_price"] - spot, 16, "median"),
        "afrr_dn_prem_4h": rolling(values["fi_afrr_down_price"] - spot, 16, "median"),
        "abs_med_24h": rolling(absolute, 96, "median"),
        "abs_med_72h": rolling(absolute, 288, "median"),
        "hi_72h": rolling(high, 288),
        "lo_72h": rolling(low, 288),
    }


# Fresh system state, computed per delivery row from that row and earlier rows
def system_state(values):
    flows = values["fi_se3_flow"] + values["fi_no4_flow"] + values["fi_se1_flow"] + values["fi_ee_flow"]
    return {
        "cons_err_1h": rolling(values["fi_consumption"] - values["fi_consumption_fc_da"], 4),
        "net_export": flows,
    }


# Published day-ahead and calendar values for each delivery row
def delivery_columns(values):
    spot = values["fi_spot_price"]
    local_day = values.index.tz_convert("Europe/Helsinki").strftime("%Y-%m-%d")
    net = values["fi_consumption_fc_da"] - values["fi_wind_fc_da"] - values["fi_solar_fc_da"]
    return {
        "spot": spot,
        "spot_dev_day": spot - spot.groupby(local_day).transform("mean"),
        "spot_drange": spot.groupby(local_day).transform("max") - spot.groupby(local_day).transform("min"),
        "spot_chg_prev_h": spot.diff(4),
        "net_fc": net,
        "wind_fc": values["fi_wind_fc_da"],
        "cons_fc": values["fi_consumption_fc_da"],
        "net_ramp_prev_h": net.diff(4),
        "hour": values["cal_hour_local"],
        "is_weekend": (values["cal_weekday_local"] >= 5).astype(int),
    }


# Hourly origins from the end of warm-up to the last test origin
def all_origins():
    return pd.date_range(FIRST_ORIGIN, LAST_ORIGIN, freq="h")


# Build one row per (origin, delivery), reading state only at its as-of position
def build_features(values, usable, origins):
    grid = values.index
    origins = pd.DatetimeIndex(origins)
    price_positions = asof_index(usable, "fi_imbalance_price", origins)
    system_positions = asof_index(usable, "fi_consumption", origins)
    assert_usable_at(usable, PRICE_SOURCES, price_positions, origins)
    assert_usable_at(usable, SYSTEM_SOURCES, system_positions, origins)

    # Repeat each origin once per step and locate each delivery on the grid
    repeated = np.repeat(np.arange(len(origins)), HORIZON_STEPS)
    steps = np.tile(np.arange(1, HORIZON_STEPS + 1), len(origins))
    row_origins = origins[repeated]
    deliveries = row_origins + pd.to_timedelta((steps - 1) * 15, unit="min")
    delivery_positions = grid.get_indexer(deliveries)
    assert (delivery_positions >= 0).all(), "delivery outside the data grid"
    assert_published(usable, DELIVERY_SOURCES, delivery_positions, row_origins)

    # Combine reference, delivery-side and origin-side columns
    columns = {"origin": row_origins, "delivery": deliveries, "step": steps}
    columns["data_cutoff"] = grid[system_positions][repeated]
    for name, series in delivery_columns(values).items():
        columns[name] = series.to_numpy()[delivery_positions]
    for name, series in price_state(values).items():
        columns[name] = series.to_numpy()[price_positions][repeated]
    for name, series in system_state(values).items():
        columns[name] = series.to_numpy()[system_positions][repeated]
    return add_decay(pd.DataFrame(columns))


# Last known spread faded towards the 4-hour median as the delivery moves away from the data cut-off
def add_decay(rows):
    gap = (rows["delivery"] - rows["data_cutoff"]).dt.total_seconds() / 3600
    fade = np.exp(-gap / 2)
    rows["gap_h"] = gap.to_numpy()
    rows["sp_last_decay"] = (rows["sp_last"] * fade).to_numpy()
    rows["sp_mix"] = (rows["sp_last_decay"] + rows["sp_med_4h"] * (1 - fade)).to_numpy()
    return rows


# Add labels only where they are usable by the training cut-off, leaving test rows empty
def attach_labels(rows, values, usable, cutoff=TRAIN_CUTOFF):
    positions = values.index.get_indexer(rows["delivery"])
    label_times = pd.Series(usable["fi_imbalance_price"].to_numpy()[positions], index=rows.index)
    allowed = (label_times <= cutoff).to_numpy()
    price = values["fi_imbalance_price"].to_numpy()[positions]
    spread = price - values["fi_spot_price"].to_numpy()[positions]
    direction = values["fi_mfrr_direction"].to_numpy()[positions]
    labelled = rows.copy()
    labelled["label_fu"] = label_times
    labelled["y_price"] = np.where(allowed, price, np.nan)
    labelled["y_spread"] = np.where(allowed, spread, np.nan)
    labelled["y_dir"] = np.where(allowed, direction, np.nan)
    return labelled


# Share of "none" direction among quarter-hours usable at the cut-off
def none_share(values, usable, cutoff=TRAIN_CUTOFF):
    known = values["fi_mfrr_direction"][usable["fi_mfrr_direction"] <= cutoff]
    return float((known == 0).mean())
