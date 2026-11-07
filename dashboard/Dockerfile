# Lambda image with the code, the trained model and the precomputed dashboard data, and no input data
FROM python:3.14-slim

# LightGBM needs the OpenMP runtime
RUN apt-get update && apt-get install -y --no-install-recommends libgomp1 && rm -rf /var/lib/apt/lists/*

# Python packages, pinned
WORKDIR /app
COPY dashboard/requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir -r /tmp/requirements.txt

# Forecast code, organiser checks, model and dashboard data
COPY src ./src
COPY organiser/validate_submission.py organiser/score.py ./organiser/
COPY artifacts/models/final_models.joblib ./artifacts/models/
COPY artifacts/run_manifest.json ./artifacts/
COPY dashboard/*.py dashboard/feature_quantiles.json ./dashboard/
COPY dashboard/web/data ./dashboard/web/data

# Lambda runtime entry point
ENV PYTHONPATH=/app RUNS_DIR=/tmp/runs MPLCONFIGDIR=/tmp
ENTRYPOINT ["python", "-m", "awslambdaric"]
CMD ["dashboard.lambda_handler.handler"]
