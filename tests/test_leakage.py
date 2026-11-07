import numpy as np
import pandas as pd
import pytest

from src.asof import load_data
from src.config import CORE, LOGIT_FEATURES, PRICE_FEATURES_DECAY, REFERENCE, SPIKE_FEATURES, TRAIN_CUTOFF
from src.features import all_origins, attach_labels, build_features, none_share
from src.make_wide import build_tables, compare_with_team_file

ORIGINS = [
    "2026-07-01T12:00:00Z", "2026-09-15T10:00:00Z", "2026-09-15T11:00:00Z", "2026-10-04T20:00:00Z",
    "2026-10-04T21:00:00Z", "2026-10-10T06:00:00Z", "2026-10-24T21:00:00Z", "2026-10-25T00:00:00Z",
    "2026-10-25T01:00:00Z", "2026-10-25T12:00:00Z", "2026-11-01T21:00:00Z",
]
FEATURES = sorted(set(CORE + SPIKE_FEATURES + PRICE_FEATURES_DECAY))


# Load the wide tables once for all tests
@pytest.fixture(scope="module")
def tables():
    return load_data()


# Replace every value not yet usable at the origin with garbage
def corrupt_future(values, usable, origin):
    future = (usable > origin).to_numpy()
    corrupted = values.to_numpy(copy=True)
    garbage = np.random.default_rng(1).normal(5e4, 1e4, corrupted.shape)
    mask = future & ~np.isnan(corrupted)
    corrupted[mask] = garbage[mask]
    return pd.DataFrame(corrupted, index=values.index, columns=values.columns), int(mask.sum())


# Features must not change when unusable data changes
@pytest.mark.parametrize("text", ORIGINS)
def test_future_rows_do_not_change_features(tables, text):
    values, usable = tables
    origin = pd.Timestamp(text)
    clean = build_features(values, usable, [origin])
    corrupted, changed = corrupt_future(values, usable, origin)
    dirty = build_features(corrupted, usable, [origin])
    assert changed > 0
    assert np.array_equal(clean[FEATURES].to_numpy(float), dirty[FEATURES].to_numpy(float), equal_nan=True)


# The perturbation test must be able to detect a change in usable data
def test_usable_rows_do_change_features(tables):
    values, usable = tables
    origin = pd.Timestamp("2026-09-15T10:00:00Z")
    clean = build_features(values, usable, [origin])
    changed = values.copy()
    last_usable = usable["fi_imbalance_price"][usable["fi_imbalance_price"] <= origin].index[-1]
    changed.loc[last_usable, "fi_imbalance_price"] += 1000.0
    dirty = build_features(changed, usable, [origin])
    assert not np.array_equal(clean[FEATURES].to_numpy(float), dirty[FEATURES].to_numpy(float), equal_nan=True)


# Building one origin alone must match building it within the full table
def test_single_origin_matches_full_table(tables):
    values, usable = tables
    origin = pd.Timestamp("2026-10-10T06:00:00Z")
    single = build_features(values, usable, [origin])
    full = build_features(values, usable, all_origins())
    part = full[full["origin"] == origin]
    assert np.array_equal(single[FEATURES].to_numpy(float), part[FEATURES].to_numpy(float), equal_nan=True)


# Test-period rows must carry no labels and training labels must respect the cut-off
def test_labels_stop_at_the_training_cutoff(tables):
    values, usable = tables
    rows = attach_labels(build_features(values, usable, all_origins()), values, usable)
    assert rows.loc[rows["origin"] >= TRAIN_CUTOFF, ["y_price", "y_spread", "y_dir"]].notna().sum().sum() == 0
    labelled = rows[rows["y_price"].notna()]
    assert labelled["label_fu"].max() <= TRAIN_CUTOFF
    assert labelled["delivery"].max() == pd.Timestamp("2026-10-04T19:45:00Z")


# The constant none share must match the known training count
def test_none_share_matches_training_count(tables):
    values, usable = tables
    assert none_share(values, usable) == pytest.approx(20 / 12092)


# Reference columns and team-only columns must never be model inputs
def test_feature_lists_are_clean():
    used = set(CORE + SPIKE_FEATURES + LOGIT_FEATURES + PRICE_FEATURES_DECAY)
    assert not used & set(REFERENCE)
    assert not used & {"premium", "period", "timestamp_local", "fi_imbalance_price", "fi_mfrr_direction"}
    assert len(CORE) == 21 and len(SPIKE_FEATURES) == 25


# Every local day's spot rows must share one publication time
def test_spot_days_publish_together(tables):
    _, usable = tables
    local_day = usable.index.tz_convert("Europe/Helsinki").strftime("%Y-%m-%d")
    assert usable["fi_spot_price"].groupby(local_day).nunique().max() == 1


# The clock-change day must have 100 quarter-hours in local time
def test_clock_change_day(tables):
    values, _ = tables
    local_day = values.index.tz_convert("Europe/Helsinki").strftime("%Y-%m-%d")
    assert (local_day == "2026-10-25").sum() == 100


# Saved tables must match a fresh rebuild and the team's wide file
def test_tables_match_organiser_files(tables):
    values, usable = tables
    fresh_values, fresh_usable = build_tables()
    assert np.array_equal(values.to_numpy(float), fresh_values.to_numpy(float), equal_nan=True)
    assert (usable.fillna(pd.Timestamp("2000-01-01", tz="UTC")).to_numpy() == fresh_usable.fillna(pd.Timestamp("2000-01-01", tz="UTC")).to_numpy()).all()
    assert compare_with_team_file(values) in (None, 0)
