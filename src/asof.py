import numpy as np
import pandas as pd

from src.config import TABLES
from src.make_wide import build_tables, write_tables


# Read the wide tables, rebuilding them first when they are missing
def load_data():
    if not (TABLES / "inputs_wide.csv").exists() or not (TABLES / "inputs_usable.csv").exists():
        write_tables(*build_tables())
    values = pd.read_csv(TABLES / "inputs_wide.csv", index_col=0)
    usable = pd.read_csv(TABLES / "inputs_usable.csv", index_col=0)
    values.index = pd.to_datetime(values.index, utc=True)
    usable.index = pd.to_datetime(usable.index, utc=True)
    usable = usable.apply(lambda column: pd.to_datetime(column, utc=True))
    check_tables(values, usable)
    return values, usable


# Stop on any table shape or ordering problem the as-of method depends on
def check_tables(values, usable):
    assert values.index.equals(usable.index), "value and usable grids differ"
    assert list(values.columns) == list(usable.columns), "value and usable columns differ"
    assert (values.index.to_series().diff().dropna() == pd.Timedelta(minutes=15)).all(), "grid is not regular"
    for series in usable.columns:
        assert usable[series].dropna().is_monotonic_increasing, f"{series}: first usable time is not increasing"
    assert (values.notna() == usable.notna()).all(axis=None), "values and usable times are not aligned"


# Return the grid position of the last row of a series usable at each origin
def asof_index(usable, series, origins):
    known = usable[series].dropna()
    positions = np.searchsorted(known.to_numpy(), origins.to_numpy(), side="right") - 1
    assert (positions >= 0).all(), f"{series}: no usable row at the earliest origin"
    return usable.index.get_indexer(known.index[positions])


# Stop if any source of an as-of feature was not yet usable at its origin
def assert_usable_at(usable, sources, positions, origins):
    origin_times = origins.to_numpy()
    for series in sources:
        times = usable[series].to_numpy()[positions]
        assert not (times > origin_times).any(), f"{series}: row read before it was usable"


# Stop if any target-side value was not yet published at its origin
def assert_published(usable, sources, positions, origins):
    origin_times = origins.to_numpy()
    for series in sources:
        times = usable[series].to_numpy()[positions]
        assert (times <= origin_times).all(), f"{series}: delivery row read before publication"
