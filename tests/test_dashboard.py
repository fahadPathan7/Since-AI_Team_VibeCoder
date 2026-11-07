import io

import pandas as pd
import pytest

from dashboard import inputs as checks
from dashboard.predict import run_forecast
from src.config import DATA, OUTPUTS

ORIGINS = "forecast_origin_utc\n2026-10-04T21:00:00Z\n2026-10-25T00:00:00Z\n2026-06-01T05:00:00Z\n"


# The organiser files as an upload would deliver them
@pytest.fixture(scope="module")
def files():
    inputs = pd.read_parquet(DATA / "inputs.parquet")
    buffer = io.BytesIO()
    inputs.to_csv(buffer, index=False)
    return {"inputs": ("inputs.csv", buffer.getvalue()), "spot": ("spot_nordpool.csv", (DATA / "spot_nordpool.csv").read_bytes())}


# A run on the raw files must reproduce the submitted forecast rows exactly
def test_upload_run_matches_submitted_forecast(files):
    table, payload, report = run_forecast(files["inputs"], files["spot"], ("origins.csv", ORIGINS.encode()))
    assert report["validator_passed"] and report["origins_forecast"] == 2
    assert "72 h of history" in report["skipped"][0]["reason"]
    submitted = pd.read_csv(OUTPUTS / "forecast_backtest.csv")
    submitted = submitted[submitted["forecast_origin_utc"].isin(table["forecast_origin_utc"])].reset_index(drop=True)
    assert table.astype(str).equals(submitted.astype(str))
    assert len(payload["origins"]) == 2 and "fi_spot_price" not in str(payload)


# Clear messages for files that don't fit
def test_bad_inputs_are_explained(files):
    raw = pd.read_csv(io.BytesIO(files["inputs"][1]), nrows=50)
    with pytest.raises(checks.InputError, match="missing column"):
        checks.check_long("inputs.csv", raw.drop(columns=["first_usable_origin_utc"]))
    long = checks.check_long("inputs.csv", pd.read_csv(io.BytesIO(files["inputs"][1])))
    with pytest.raises(checks.InputError, match="fi_spot_price"):
        checks.combine(long)
    with pytest.raises(checks.InputError, match="forecast_origin_utc"):
        checks.read_origins("origins.csv", b"time\n2026-10-05T00:00:00Z\n")
    with pytest.raises(checks.InputError, match="UTC"):
        checks.read_origins("origins.csv", b"forecast_origin_utc\n05.10.2026 00:00\n")
