from mangum import Mangum

from dashboard.api import app
from dashboard.jobs import run_job

http = Mangum(app, lifespan="off")


# Background runs arrive as {"run_job": id}; everything else is an HTTP request from CloudFront
def handler(event, context):
    if isinstance(event, dict) and "run_job" in event:
        run_job(event["run_job"])
        return {"done": event["run_job"]}
    return http(event, context)
