import json
import os
import threading
import traceback
import uuid

import pandas as pd

from dashboard.inputs import InputError
from dashboard.settings import RUNS, RUNS_BUCKET, UPLOAD_LIMIT_MB

FILES = ("inputs", "spot", "origins")


# Run storage on local disk, or in S3 when RUNS_BUCKET is set
class Store:
    def __init__(self):
        self.s3 = None
        if RUNS_BUCKET:
            import boto3
            from botocore.config import Config
            region = os.environ.get("AWS_REGION", "eu-north-1")
            self.s3 = boto3.client("s3", region_name=region, endpoint_url=f"https://s3.{region}.amazonaws.com",
                                   config=Config(signature_version="s3v4", s3={"addressing_style": "virtual"}))

    def put(self, key, data, content_type="application/octet-stream"):
        if self.s3:
            self.s3.put_object(Bucket=RUNS_BUCKET, Key=key, Body=data, ContentType=content_type)
            return
        path = RUNS / key
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)

    def get(self, key):
        if self.s3:
            try:
                return self.s3.get_object(Bucket=RUNS_BUCKET, Key=key)["Body"].read()
            except self.s3.exceptions.ClientError as error:
                if error.response["Error"]["Code"] in ("NoSuchKey", "404", "AccessDenied"):
                    return None
                raise
        path = RUNS / key
        return path.read_bytes() if path.exists() else None

    def upload_url(self, key):
        return self.s3.generate_presigned_url("put_object", Params={"Bucket": RUNS_BUCKET, "Key": key}, ExpiresIn=3600)


STORE = Store()


# Create a job and say where each file should be uploaded
def new_job(file_names):
    job = uuid.uuid4().hex
    names = {kind: name for kind, name in file_names.items() if name}
    set_status(job, "waiting for files", names=names)
    uploads = {kind: STORE.upload_url(f"{job}/in/{kind}") for kind in names} if STORE.s3 else None
    return job, uploads


# Record a job's state with any extra details
def set_status(job, state, **extra):
    current = status(job) or {}
    current.update({"job": job, "state": state, "updated": pd.Timestamp.now(tz="UTC").isoformat(), **extra})
    STORE.put(f"{job}/status.json", json.dumps(current).encode(), "application/json")


# A job's last recorded state, or None
def status(job):
    data = STORE.get(f"{job}/status.json")
    return json.loads(data) if data else None


# Run a job whose files are already stored, recording progress and the result
def run_job(job):
    info = status(job)
    names = info.get("names", {})
    files = {kind: (names[kind], STORE.get(f"{job}/in/{kind}")) for kind in names}
    try:
        for kind, (name, data) in files.items():
            if data is None:
                raise InputError(f"The {kind} file '{name}' was not received")
            if len(data) > UPLOAD_LIMIT_MB * 1e6:
                raise InputError(f"The {kind} file is larger than {UPLOAD_LIMIT_MB} MB")
        if "inputs" not in files:
            raise InputError("An inputs file is required")
        origin_range = info.get("range")
        if "origins" not in files and not origin_range:
            raise InputError("Give a forecast origins file or a first and last origin")
        from dashboard.predict import run_forecast
        table, payload, report = run_forecast(
            files["inputs"], files.get("spot"), files.get("origins"),
            (origin_range["start"], origin_range["end"], origin_range.get("every", 1)) if origin_range else None,
            progress=lambda text: set_status(job, "running", step=text),
        )
        STORE.put(f"{job}/forecast_backtest.csv", table.to_csv(index=False, lineterminator="\n").encode(), "text/csv")
        STORE.put(f"{job}/payload.json", json.dumps(payload, separators=(",", ":"), allow_nan=False).encode(), "application/json")
        set_status(job, "done", step="Finished", report=report)
    except InputError as error:
        set_status(job, "failed", step="Input check failed", error=str(error))
    except Exception as error:
        traceback.print_exc()
        set_status(job, "failed", step="Unexpected error", error=f"{type(error).__name__}: {error}")


# Start a job in the background: a thread locally, an asynchronous Lambda call on AWS
def start(job):
    set_status(job, "queued", step="Queued")
    function = os.environ.get("AWS_LAMBDA_FUNCTION_NAME")
    if function:
        import boto3
        boto3.client("lambda").invoke(FunctionName=function, InvocationType="Event", Payload=json.dumps({"run_job": job}).encode())
    else:
        threading.Thread(target=run_job, args=(job,), daemon=True).start()
