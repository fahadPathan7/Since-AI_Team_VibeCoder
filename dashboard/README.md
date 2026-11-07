# ValoBalance: dashboard and API

A situational view for a production shift supervisor or an electricity trading specialist: what is worth checking now, what is coming in the next 10 hours, and how the forecast has performed. The same page runs locally or on AWS.

## Run it locally

From the `submission` folder, after the main setup in `../README.md`:

```bash
python -m dashboard
```

Open http://127.0.0.1:8000. API documentation is at http://127.0.0.1:8000/api/docs.

The page reads `web/data/dashboard.json`, which is already built. To rebuild it from the forecast files (about 10 seconds):

```bash
python -m dashboard.build_data
```

## Views

| View | What it answers |
|---|---|
| **Now** | The coming hour only: each quarter-hour's P50, range, risks and direction, the last 2 hours of published prices and the forecast from now, and the alerts that matter now. Later alerts are listed below them |
| **Next 10 hours** | Colour lanes for direction and spike risk, P50 with the P10–P90 range, spike risk above and below spot, up/down/none regulation, an hourly table with drivers, and a CSV download |
| **Hindsight** | Scores for the previous day, week, month or a custom date range, forecast against actual, error by horizon, alerts with what followed, and the inputs that move the price forecast most |
| **Run a forecast** | Upload the starter package files and get a forecast, the official validator result and, when outcomes are in the data, the official score |
| **About & API** | Model summary and API endpoints |

**Moving back in time.** The time control at the top (buttons, slider, keyboard arrows, or **Replay**, which steps forward one hour per second) sets the forecast time. Every view then uses only what was known at that moment: forecasts made by then and prices published by then. *Show what happened* in **Next 10 hours** adds the actual price, spikes and direction, clearly marked as hindsight. All times are Finnish time.

**Data sets.** *Validation* (7 Sep – 4 Oct) uses a model trained only on data usable by 6 Sep. *Test* (5 Oct – 1 Nov) is the submitted forecast. Uploaded runs are added to the data set list.

## Alerts

Each alert covers a window of quarter-hours (windows of the same kind less than an hour apart are joined), states in one line what the numbers are, names the main drivers and lists suggestions to review. They are never trading or operating instructions, because open data doesn't show available capacity, marginal costs or commitments.

| Alert | Trigger |
|---|---|
| Spike risk above spot | `p_spike_high` ≥ 0.25 (price more than 50 €/MWh above spot). Marked when the risk rose by 0.10 or more since the forecast an hour earlier |
| Spike risk below spot | `p_spike_low` ≥ 0.35 (price more than 50 €/MWh below spot) |
| Up-regulation expected | `p_up` ≥ 0.60 for at least 30 minutes |
| Conflicting signals | The direction model expects up-regulation while the price forecast is below spot, or down-regulation while it is more than 20 €/MWh above spot |
| Forecast moved | P50 moved by 25 €/MWh or more since the forecast an hour earlier, for at least 30 minutes |
| High uncertainty | P10–P90 width above the 95th percentile of the past week's forecasts |

The thresholds were set once on the validation period, for about 1–2 alerts per update on average, and then frozen. Measured on the validation and test periods: inside spike-above alerts, spikes happened 3.5 times as often as average on validation and 2.3 times as often on test.

## Forecast from your own files

**Run a forecast** accepts the starter package files as delivered. The page checks the columns and series in the browser before uploading, and the server checks everything again.

| File | Required | Format |
|---|---|---|
| Inputs | Yes | `inputs.csv` or `inputs.parquet`, long format |
| Spot | If the inputs don't contain `fi_spot_price` | `spot_nordpool.csv`, same long format |
| Origins | Or give a first and last origin | Any CSV with a `forecast_origin_utc` column, such as `forecast_origins.csv` |

**Columns of the inputs and spot files:**

| Column | Content |
|---|---|
| `series_id` | Series name, such as `fi_imbalance_price` |
| `timestamp_utc` | Quarter-hour start in UTC, such as `2026-10-05T06:00:00Z` |
| `value` | Number |
| `first_usable_origin_utc` | First forecast time allowed to use the row, in UTC |

Other columns, such as `source`, `dataset_id` and `unit`, are ignored.

**Series the model needs:** `fi_imbalance_price`, `fi_spot_price`, `fi_mfrr_direction`, `fi_mfrr_up_price`, `fi_mfrr_down_price`, `fi_afrr_up_price`, `fi_afrr_down_price`, `fi_consumption`, `fi_consumption_fc_da`, `fi_wind_fc_da`, `fi_solar_fc_da`, `fi_se1_flow`, `fi_se3_flow`, `fi_no4_flow`, `fi_ee_flow`, `cal_hour_local`, `cal_weekday_local`. Other series are allowed and ignored.

**Origins that can't be forecast are skipped with the reason.** Each origin needs 72 hours of data before it, and the spot price and day-ahead forecasts for its next 10 hours must be published at the origin. The data rule is the same as for the submission: at each origin, only rows with `first_usable_origin_utc` at or before it are read.

**What you get:** `forecast_backtest.csv` in the official 13-column format, the official validator report, the official `score.py` result when the uploaded data contains the outcomes, and the run in the dashboard. Running the starter package files for the 673 test origins reproduces `outputs/forecast_backtest.csv` exactly, which `tests/test_dashboard.py` checks.

The same run works without the browser:

```bash
curl -X POST localhost:8000/api/jobs -H 'Content-Type: application/json' \
  -d '{"inputs":"inputs.parquet","spot":"spot_nordpool.csv","origins":"forecast_origins.csv"}'
# returns {"job": "<id>", ...}
curl -X PUT --data-binary @data/inputs.parquet localhost:8000/api/jobs/<id>/files/inputs
curl -X PUT --data-binary @data/spot_nordpool.csv localhost:8000/api/jobs/<id>/files/spot
curl -X PUT --data-binary @organiser/forecast_origins.csv localhost:8000/api/jobs/<id>/files/origins
curl -X POST localhost:8000/api/jobs/<id>/start
curl localhost:8000/api/jobs/<id>                  # progress, validator and score
curl -o forecast.csv localhost:8000/api/jobs/<id>/forecast.csv
```

## API

| Endpoint | Returns |
|---|---|
| `GET /api/origins` | Forecast times with precomputed forecasts |
| `GET /api/forecast?origin=2026-10-05T06:00:00Z` | The 40 quarter-hour forecast with drivers |
| `GET /api/alerts?origin=…` | Situations worth reviewing |
| `POST /api/jobs`, `PUT /api/jobs/{id}/files/{kind}`, `POST /api/jobs/{id}/start` | A forecast run on uploaded files |
| `GET /api/jobs/{id}`, `/forecast.csv`, `/payload.json` | Progress and results of a run |

## Spot prices

The spot price is licensed for the hackathon only and may not be published. The local version draws it in the price chart as a reference line, read from `data/inputs_wide.csv` through `GET /api/spot`. The AWS image contains no `data/` folder, so the hosted site and its API never show spot prices. The precomputed data in `web/data/` contains forecasts, actual imbalance prices (Fingrid, CC BY 4.0), directions and whether a quarter-hour was a spike, but no spot prices.

The day-ahead spot price is published the day before, so it is always known for the next 10 hours at a forecast time. Showing it is not hindsight.

## Files

```text
dashboard/
  api.py, jobs.py, lambda_handler.py   API, run handling, AWS Lambda entry point
  inputs.py                            checks of uploaded files and origins
  predict.py                           forecast run on uploaded files, official validator and scorer
  alerts.py, payload.py                alert rules, driver wording, dashboard data
  build_data.py                        precomputes web/data/dashboard.json
  feature_quantiles.json               training-period quartiles used to word drivers
  web/                                 the page: index.html, styles.css, js/, vendor/echarts.min.js
  Dockerfile, requirements.txt         API image for AWS Lambda
```
