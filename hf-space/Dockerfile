# Hugging Face Space: the dashboard and API with the trained model and precomputed data, and no input data
FROM python:3.14-slim

# LightGBM needs the OpenMP runtime
RUN apt-get update && apt-get install -y --no-install-recommends libgomp1 && rm -rf /var/lib/apt/lists/*

# Spaces run as a normal user with id 1000
RUN useradd -m -u 1000 user
WORKDIR /app

# Python packages, pinned
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Code, model, organiser checks and the page
COPY --chown=user . .
USER user

ENV PYTHONPATH=/app RUNS_DIR=/tmp/runs MPLCONFIGDIR=/tmp PYTHONUNBUFFERED=1
EXPOSE 7860
CMD ["python", "-m", "uvicorn", "dashboard.api:app", "--host", "0.0.0.0", "--port", "7860"]
