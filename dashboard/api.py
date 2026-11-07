import json
import os
from functools import lru_cache

import pandas as pd
from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.responses import JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from dashboard import jobs
from src.config import DATA
from dashboard.settings import LONG_COLUMNS, MAX_ORIGINS, ORIGIN_COLUMN, ORIGIN_SECRET, REQUIRED_SERIES, UPLOAD_LIMIT_MB, WEB, WEB_DATA

app = FastAPI(title="Imbalance price forecast API", version="1.0", docs_url="/api/docs", openapi_url="/api/openapi.json",
              description="Read the precomputed forecasts and alerts, or run the model on uploaded starter-package files.")


# On AWS, accept only requests from CloudFront; always revalidate page files so changes show at once
@app.middleware("http")
async def origin_check(request: Request, call_next):
    if ORIGIN_SECRET and request.headers.get("x-origin-verify") != ORIGIN_SECRET:
        return JSONResponse({"detail": "Forbidden"}, status_code=403)
    response = await call_next(request)
    if not request.url.path.startswith("/api/"):
        response.headers["Cache-Control"] = "no-cache"
    return response


# The precomputed dashboard data, loaded once
@lru_cache(maxsize=1)
def precomputed():
    return json.loads((WEB_DATA / "dashboard.json").read_text())


# Position of an origin in the precomputed data, or a clear HTTP error
def origin_index(origin):
    data = precomputed()
    try:
        stamp = int(pd.Timestamp(origin).tz_convert("UTC").value // 10**6) if pd.Timestamp(origin).tzinfo else int(pd.Timestamp(origin, tz="UTC").value // 10**6)
    except ValueError:
        raise HTTPException(400, "origin must be a UTC time such as 2026-10-05T06:00:00Z")
    if stamp not in data["origins"]:
        raise HTTPException(404, "No forecast for this origin. See /api/origins")
    return data["origins"].index(stamp)


# Milliseconds since 1970 as a UTC timestamp string
def iso(ms):
    return pd.Timestamp(ms, unit="ms", tz="UTC").strftime("%Y-%m-%dT%H:%M:%SZ")


# Endpoints
@app.get("/api/health", summary="Service check")
def health():
    return {"status": "ok"}


# Upload rules and limits
@app.get("/api/config", summary="Upload rules and limits")
def config():
    return {
        "upload_mode": "s3" if jobs.STORE.s3 else "direct",
        "upload_limit_mb": UPLOAD_LIMIT_MB, "max_origins": MAX_ORIGINS,
        "long_columns": LONG_COLUMNS, "origin_column": ORIGIN_COLUMN, "required_series": REQUIRED_SERIES,
    }


# Forecast origins with precomputed forecasts
@app.get("/api/origins", summary="Forecast origins with precomputed forecasts")
def origins():
    data = precomputed()
    return {"periods": data["meta"]["periods"], "origins": [iso(o) for o in data["origins"]]}


# The 40 quarter-hour forecast made at one origin
@app.get("/api/forecast", summary="The 40 quarter-hour forecast made at one origin")
def forecast(origin: str = Query(..., examples=["2026-10-05T06:00:00Z"])):
    data, i = precomputed(), origin_index(origin)
    steps, f = data["steps"], data["f"]
    rows = []
    for step in range(steps):
        r = i * steps + step
        rows.append({
            "delivery_start_utc": iso(data["origins"][i] + step * 900000), "step": step + 1,
            "p10": f["p10"][r], "p50": f["p50"][r], "p90": f["p90"][r],
            "p_up": f["up"][r], "p_down": f["down"][r], "p_none": f["none"][r],
            "p_spike_high": f["hi"][r], "p_spike_low": f["lo"][r],
            "top_drivers": f["names"][r], "driver_phrases": [data["phrases"][k] for k in f["drv"][r]],
        })
    return {"forecast_origin_utc": iso(data["origins"][i]), "data_cutoff_utc": iso(data["cutoffs"][i]), "rows": rows}


# Situations worth reviewing at one origin
@app.get("/api/alerts", summary="Situations worth reviewing at one origin")
def alerts(origin: str = Query(..., examples=["2026-10-05T06:00:00Z"])):
    data, i = precomputed(), origin_index(origin)
    return {"forecast_origin_utc": iso(data["origins"][i]),
            "alerts": [{**a, "start": iso(a["start"]), "end": iso(a["end"])} for a in data["alerts"][i]]}


# Day-ahead spot prices from the local data folder; licensed data, so the AWS image has none and this returns 404
@app.get("/api/spot", summary="Spot prices, only where the licensed data is present locally")
def spot():
    return spot_series()


# The spot series, read once
@lru_cache(maxsize=1)
def spot_series():
    path = DATA / "inputs_wide.csv"
    if not path.exists():
        raise HTTPException(404, "Spot prices are only available in the local version")
    values = pd.read_csv(path, usecols=["timestamp_utc", "fi_spot_price"])
    start = pd.Timestamp(values["timestamp_utc"].iloc[0])
    return {"t0": int(start.value // 10**6), "step": 900000, "values": [None if pd.isna(v) else round(float(v), 2) for v in values["fi_spot_price"]]}


# Files and origins for a forecast run
class JobRequest(BaseModel):
    inputs: str
    spot: str | None = None
    origins: str | None = None
    first_origin: str | None = None
    last_origin: str | None = None
    every_hours: int = 1


# Forecast runs on uploaded files
@app.post("/api/jobs", summary="Start a forecast run on uploaded files")
def create_job(request: JobRequest):
    if not request.origins and not (request.first_origin and request.last_origin):
        raise HTTPException(400, "Give an origins file or a first and last origin")
    job, uploads = jobs.new_job({"inputs": request.inputs, "spot": request.spot, "origins": request.origins})
    if not request.origins:
        jobs.set_status(job, "waiting for files", range={"start": request.first_origin, "end": request.last_origin, "every": request.every_hours})
    return {"job": job, "uploads": uploads}


# Upload one file directly (local mode)
@app.put("/api/jobs/{job}/files/{kind}", summary="Upload one file directly (local mode)")
async def upload_file(job: str, kind: str, request: Request):
    if jobs.STORE.s3:
        raise HTTPException(400, "On AWS, upload to the URL returned by POST /api/jobs")
    if kind not in jobs.FILES or not jobs.status(job):
        raise HTTPException(404, "Unknown job or file kind")
    jobs.STORE.put(f"{job}/in/{kind}", await request.body())
    return {"stored": kind}


# Run the model once the files are uploaded
@app.post("/api/jobs/{job}/start", summary="Run the model once the files are uploaded")
def start_job(job: str):
    if not jobs.status(job):
        raise HTTPException(404, "Unknown job")
    jobs.start(job)
    return jobs.status(job)


# Progress and result of a run
@app.get("/api/jobs/{job}", summary="Progress and result of a run")
def job_status(job: str):
    info = jobs.status(job)
    if not info:
        raise HTTPException(404, "Unknown job")
    return info


# The run's forecast in the official format
@app.get("/api/jobs/{job}/forecast.csv", summary="The run's forecast in the official format")
def job_forecast(job: str):
    data = jobs.STORE.get(f"{job}/forecast_backtest.csv")
    if data is None:
        raise HTTPException(404, "No forecast for this job")
    return Response(data, media_type="text/csv", headers={"Content-Disposition": "attachment; filename=forecast_backtest.csv"})


# The run's data for the dashboard
@app.get("/api/jobs/{job}/payload.json", summary="The run's data for the dashboard")
def job_payload(job: str):
    data = jobs.STORE.get(f"{job}/payload.json")
    if data is None:
        raise HTTPException(404, "No result for this job")
    return Response(data, media_type="application/json")


# Serve the web page as well when running locally
if not os.environ.get("AWS_LAMBDA_FUNCTION_NAME"):
    app.mount("/", StaticFiles(directory=WEB, html=True), name="web")
