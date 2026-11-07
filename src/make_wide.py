import numpy as np
import pandas as pd

from src.config import DATA, TABLES, TEAM_WIDE

KEYS = ["series_id", "timestamp_utc", "value", "first_usable_origin_utc"]


# Stack the organiser files into one long table with UTC timestamps
def read_long():
    inputs = pd.read_parquet(DATA / "inputs.parquet", columns=KEYS)
    spot = pd.read_csv(DATA / "spot_nordpool.csv", usecols=KEYS)
    long = pd.concat([inputs, spot], ignore_index=True)
    for column in ["timestamp_utc", "first_usable_origin_utc"]:
        long[column] = pd.to_datetime(long[column], utc=True)
    return long


# Pivot values and first-usable times onto one regular 15-minute grid
def build_tables():
    long = read_long()
    grid = pd.date_range(long["timestamp_utc"].min(), long["timestamp_utc"].max(), freq="15min", name="timestamp_utc")
    values = long.pivot(index="timestamp_utc", columns="series_id", values="value").reindex(grid)
    usable = long.pivot(index="timestamp_utc", columns="series_id", values="first_usable_origin_utc").reindex(grid)
    return values.sort_index(axis=1), usable.sort_index(axis=1)


# Write both wide tables into the submission data folder
def write_tables(values, usable):
    TABLES.mkdir(parents=True, exist_ok=True)
    values.to_csv(TABLES / "inputs_wide.csv", date_format="%Y-%m-%dT%H:%M:%SZ")
    usable.to_csv(TABLES / "inputs_usable.csv", date_format="%Y-%m-%dT%H:%M:%SZ")


# Count cells that differ from the team's own wide file, when it exists
def compare_with_team_file(values):
    if not TEAM_WIDE.exists():
        return None
    team = pd.read_csv(TEAM_WIDE, low_memory=False)
    team.index = pd.to_datetime(team["timestamp_utc"], utc=True)
    differences = 0
    for column in values.columns:
        ours, theirs = values[column].to_numpy(), team[column].reindex(values.index).astype(float).to_numpy()
        differences += int((~(np.isclose(ours, theirs, atol=1e-6) | (np.isnan(ours) & np.isnan(theirs)))).sum())
    return differences


# Rebuild the tables and report the comparison
def main():
    values, usable = build_tables()
    write_tables(values, usable)
    print(f"Wrote {TABLES}: {values.shape[0]} quarter-hours, {values.shape[1]} series")
    differences = compare_with_team_file(values)
    if differences is not None:
        print(f"Cells differing from {TEAM_WIDE}: {differences}")
        if differences:
            raise SystemExit(1)


if __name__ == "__main__":
    main()
