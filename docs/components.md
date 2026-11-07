---
title: "Data sources, services, models and software"
subtitle: "With their usage rights · Turku Energia challenge, Since AI Hackathon 2026"
---

Licences are as declared in each package's metadata, or by its publisher, at the versions listed.

## Data sources

All data comes from the organisers' starter package. We added no external data.

| Source | Data used | Usage rights |
|---|---|---|
| Fingrid Open Data | Imbalance price, mFRR and aFRR data, direction, consumption, production, cross-border flows, day-ahead consumption, wind and solar forecasts | CC BY 4.0 |
| ENTSO-E Transparency Platform | Neighbouring area imbalance prices, load forecasts and FI–EE capacity. These are in the package, and were checked for the feature study. The final model doesn't use them | CC BY 4.0, modified by the organisers (converted to UTC and 15-minute series) |
| Nord Pool, via Turku Energia | Finnish day-ahead spot price | Licensed to Turku Energia. Hackathon use only, no redistribution, no public repositories, delete after the event. Shown only in the local dashboard, never on the hosted site |
| Calendar series in the package | Weekday, local hour, holidays, daylight saving | Provided by the organisers |

**Attribution:** contains data from Fingrid Open Data and the ENTSO-E Transparency Platform, both CC BY 4.0, processed by the organisers and by this project as described in `README.md`.

## External services

The forecast and its code use no external services or APIs at run time.

| Service | Use | Usage rights |
|---|---|---|
| Claude Code (Anthropic) | AI assistant for coding, analysis and writing during development. It isn't part of the forecast | Anthropic commercial terms |
| Amazon Web Services: CloudFront, S3, Lambda, ECR, IAM, CloudWatch Logs, EventBridge | Hosting of the ValoBalance dashboard and API at https://d33zptc1t0y8ga.cloudfront.net (`infra/`). Not needed to produce the forecast | AWS Customer Agreement |

## Ready-made models

None. We use no pre-trained models. Every model is trained from the starter package data by the submitted code.

## Organiser files

| Files | Use | Usage rights |
|---|---|---|
| `validate_submission.py`, `score.py`, `make_templates.py`, `baseline.ipynb`, templates | Validation, scoring and templates, unchanged in `organiser/` | Provided by the organisers for the challenge |

## Software components

| Component | Version | Use | Licence |
|---|---|---|---|
| Python | 3.14 | Language | PSF License |
| LightGBM | 4.7.0 | Quantile and binary models, SHAP values | MIT |
| scikit-learn | 1.9.1 | Logistic regression, preprocessing | BSD-3-Clause |
| pandas | 3.1.1 | Data handling | BSD-3-Clause |
| NumPy | 2.5.4 | Numerical computing | BSD-3-Clause, with bundled parts under 0BSD, MIT, Zlib and CC0-1.0 |
| PyArrow | 26.0.1 | Reading Parquet files | Apache-2.0 |
| tzdata | 2026.6 | Time zone data | Apache-2.0 |
| joblib | 1.6.0 | Saving models | BSD-3-Clause |
| pytest | 9.2.0 | Tests | MIT |
| Matplotlib | 3.11.2 | Charts | Matplotlib License, PSF-based |
| Jupyter Notebook | 7.6.5 | Analysis notebook | BSD-3-Clause |
| nbconvert | 7.17.2 | Running notebooks | BSD-3-Clause |
| nbformat | 5.11.1 | Notebook format | BSD-3-Clause |
| ipykernel | 7.4.0 | Notebook kernel | BSD-3-Clause |
| libomp (LLVM OpenMP) | 23.1.5 | Parallel computing for LightGBM on macOS | MIT, as listed by Homebrew |
| FastAPI | 0.162.2 | Dashboard API | MIT |
| Uvicorn | 0.54.0 | Local web server | BSD-3-Clause |
| Pydantic | 2.14.3 | API request checks | MIT |
| HTTPX | 0.28.1 | API tests | BSD-3-Clause |
| Mangum | 0.22.0 | Runs the API on AWS Lambda | MIT |
| AWS Lambda Python Runtime Interface Client | 4.2.3 | Lambda container entry point | Apache-2.0 |
| boto3 | 1.43.126 | S3 and Lambda calls on AWS | Apache-2.0 |
| Apache ECharts | 5.6.0 | Dashboard charts, bundled in `dashboard/web/vendor/` | Apache-2.0 |
| Docker image `python:3.14-slim` | 3.14 | Base of the Lambda image | PSF License for Python; Debian packages under their own licences |
| Terraform | 1.16.5 | AWS infrastructure (`infra/`) | BUSL-1.1 |
| Terraform AWS provider | 6.72.0 | AWS resources | MPL-2.0 |

Other packages are installed automatically as dependencies of these, under their own licences.

## Documentation tools

The PDF documents were made with Pandoc (GPL-2.0-or-later) and Google Chrome. Neither is needed to run the code.

## Evaluated and not used

These were compared during development and aren't part of the final solution. None of them beat the chosen design by a clear margin.

| Model | Library | Licence |
|---|---|---|
| XGBoost | XGBoost | Apache-2.0 |
| CatBoost | CatBoost | Apache-2.0 |
| HistGradientBoosting | scikit-learn | BSD-3-Clause |
| Random forest | scikit-learn | BSD-3-Clause |
| Extra trees | scikit-learn | BSD-3-Clause |

Stacking, two-stage models, three-class spike models, a mixture model and Platt calibration were also tested. They were built with the components above.
