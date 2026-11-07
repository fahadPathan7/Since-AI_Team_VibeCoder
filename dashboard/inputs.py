import io

import numpy as np
import pandas as pd

from dashboard.settings import (DELIVERY_SERIES, HISTORY_HOURS, LONG_COLUMNS, MAX_ORIGINS, ORIGIN_COLUMN,
                                REQUIRED_SERIES)
from src.config import HORIZON_STEPS


# A problem with uploaded files, shown to the user as is
class InputError(ValueError):
    pass


# Read an uploaded CSV or Parquet file from bytes
def read_table(name, content):
    try:
        if name.lower().endswith(".parquet"):
            return pd.read_parquet(io.BytesIO(content))
        return pd.read_csv(io.BytesIO(content), low_memory=False)
    except Exception as error:
        raise InputError(f"{name}: could not be read as {'Parquet' if name.lower().endswith('.parquet') else 'CSV'} ({error})")


# Parse UTC timestamps, refusing values that are missing or not in UTC
def parse_utc(series, label):
    text = series.astype(str).str.strip()
    parsed = pd.to_datetime(text, utc=True, errors="coerce", format="ISO8601")
    bad = parsed.isna() | ~text.str.match(r"^\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}(:\d{2})?(Z|\+00:00)$")
    if bad.any():
        raise InputError(f"{label}: {int(bad.sum())} timestamps are not UTC in the form 2026-10-05T06:00:00Z, first: '{text[bad].iloc[0]}'")
    return parsed


# Check one long-format file and return its required columns with parsed types
def check_long(name, table):
    missing = [c for c in LONG_COLUMNS if c not in table.columns]
    if missing:
        raise InputError(f"{name}: missing column(s) {', '.join(missing)}. Required: {', '.join(LONG_COLUMNS)}. Found: {', '.join(map(str, table.columns))}")
    table = table[LONG_COLUMNS].copy()
    table["series_id"] = table["series_id"].astype(str).str.strip()
    table["timestamp_utc"] = parse_utc(table["timestamp_utc"], f"{name}, timestamp_utc")
    table["first_usable_origin_utc"] = parse_utc(table["first_usable_origin_utc"], f"{name}, first_usable_origin_utc")
    values = pd.to_numeric(table["value"], errors="coerce")
    bad = values.isna() & table["value"].notna() & (table["value"].astype(str).str.strip() != "")
    if bad.any():
        raise InputError(f"{name}: {int(bad.sum())} values are not numbers, first: '{table.loc[bad, 'value'].iloc[0]}'")
    table["value"] = values
    return table.dropna(subset=["value"])


# Combine the inputs file and the optional spot file into one long table
def combine(inputs, spot=None):
    if spot is not None:
        inputs = inputs[inputs["series_id"] != "fi_spot_price"]
        spot = spot[spot["series_id"] == "fi_spot_price"]
        if spot.empty:
            raise InputError("spot file: no rows with series_id 'fi_spot_price'")
        inputs = pd.concat([inputs, spot], ignore_index=True)
    present = set(inputs["series_id"].unique())
    missing = {s: d for s, d in REQUIRED_SERIES.items() if s not in present}
    if missing:
        listed = "; ".join(f"{s} ({d})" for s, d in missing.items())
        hint = " Upload spot_nordpool.csv as the spot file." if "fi_spot_price" in missing else ""
        raise InputError(f"Missing series: {listed}.{hint}")
    duplicated = inputs.duplicated(["series_id", "timestamp_utc"])
    if duplicated.any():
        first = inputs[duplicated].iloc[0]
        raise InputError(f"{int(duplicated.sum())} duplicate rows for the same series and quarter-hour, first: {first['series_id']} {first['timestamp_utc']:%Y-%m-%dT%H:%M:%SZ}")
    off_grid = (inputs["timestamp_utc"].dt.minute % 15 != 0) | (inputs["timestamp_utc"].dt.second != 0)
    if off_grid.any():
        raise InputError(f"{int(off_grid.sum())} timestamps are not quarter-hour starts, first: {inputs.loc[off_grid, 'timestamp_utc'].iloc[0]}")
    return inputs[inputs["series_id"].isin(REQUIRED_SERIES)]


# Pivot the long table into value and first-usable tables on a regular grid, as src/make_wide.py does
def wide_tables(long):
    grid = pd.date_range(long["timestamp_utc"].min(), long["timestamp_utc"].max(), freq="15min", name="timestamp_utc")
    values = long.pivot(index="timestamp_utc", columns="series_id", values="value").reindex(grid).sort_index(axis=1)
    usable = long.pivot(index="timestamp_utc", columns="series_id", values="first_usable_origin_utc").reindex(grid).sort_index(axis=1)
    for series in usable.columns:
        known = usable[series].dropna()
        if not known.is_monotonic_increasing:
            raise InputError(f"{series}: first_usable_origin_utc goes backwards in time, so the rows can't be read as-of")
    return values, usable


# Read the forecast origins from an uploaded file
def read_origins(name, content):
    table = read_table(name, content)
    if ORIGIN_COLUMN not in table.columns:
        raise InputError(f"{name}: missing column '{ORIGIN_COLUMN}'. Found: {', '.join(map(str, table.columns))}")
    origins = pd.DatetimeIndex(parse_utc(table[ORIGIN_COLUMN].dropna(), f"{name}, {ORIGIN_COLUMN}").unique()).sort_values()
    return check_origin_count(origins)


# Make an origin list from a start, an end and a step in hours
def origin_range(start, end, every_hours=1):
    start, end = pd.Timestamp(start), pd.Timestamp(end)
    start = start.tz_localize("UTC") if start.tzinfo is None else start.tz_convert("UTC")
    end = end.tz_localize("UTC") if end.tzinfo is None else end.tz_convert("UTC")
    if end < start:
        raise InputError("The last origin is before the first origin")
    return check_origin_count(pd.date_range(start, end, freq=f"{int(every_hours)}h"))


# Refuse empty, too long or off-grid origin lists
def check_origin_count(origins):
    if len(origins) == 0:
        raise InputError("No forecast origins given")
    if len(origins) > MAX_ORIGINS:
        raise InputError(f"{len(origins)} origins given; the limit per run is {MAX_ORIGINS}")
    off_grid = (origins.minute % 15 != 0) | (origins.second != 0)
    if off_grid.any():
        raise InputError(f"Origins must be quarter-hour starts, first bad one: {origins[off_grid][0]:%Y-%m-%dT%H:%M:%SZ}")
    return origins


# Split origins into those the data supports and those it doesn't, with a reason for each
def usable_origins(values, usable, origins):
    grid = values.index
    keep, skipped = [], []
    for origin in origins:
        last = origin + pd.Timedelta(minutes=15 * (HORIZON_STEPS - 1))
        if origin - pd.Timedelta(hours=HISTORY_HOURS) < grid[0]:
            skipped.append((origin, f"needs {HISTORY_HOURS} h of history before the origin; data starts {grid[0]:%Y-%m-%d %H:%M} UTC"))
            continue
        if last > grid[-1]:
            skipped.append((origin, f"the 10-hour horizon ends {last:%Y-%m-%d %H:%M} UTC, after the data ends {grid[-1]:%Y-%m-%d %H:%M} UTC"))
            continue
        reason = None
        for series in ["fi_imbalance_price", "fi_consumption"]:
            if not (usable[series].dropna() <= origin).any():
                reason = f"no {series} row is usable at the origin"
        window = usable.loc[origin:last, DELIVERY_SERIES]
        late = window.isna() | (window > origin)
        if late.any(axis=None):
            series = late.any().idxmax()
            reason = f"{series} for the next 10 hours isn't published by the origin (the forecast may only use published data)"
        if reason:
            skipped.append((origin, reason))
        else:
            keep.append(origin)
    return pd.DatetimeIndex(keep), skipped


# Actual outcomes in the uploaded data, for scoring a run in hindsight
def actuals_from(values, usable):
    direction = values["fi_mfrr_direction"].map({1: "up", -1: "down", 0: "none"})
    table = pd.DataFrame({
        "delivery_start_utc": values.index.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "imbalance_price": values["fi_imbalance_price"].to_numpy(),
        "spot_price": values["fi_spot_price"].to_numpy(),
        "direction": direction.to_numpy(),
        "first_usable_origin_utc": usable["fi_imbalance_price"].dt.strftime("%Y-%m-%dT%H:%M:%SZ").to_numpy(),
    })
    return table[np.isfinite(table["imbalance_price"])]
