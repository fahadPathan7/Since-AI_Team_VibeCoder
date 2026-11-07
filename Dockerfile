# Runs the whole pipeline or the dashboard with no local Python setup
FROM python:3.14-slim

# LightGBM needs the OpenMP runtime
RUN apt-get update && apt-get install -y --no-install-recommends libgomp1 && rm -rf /var/lib/apt/lists/*

# Pinned Python packages
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# The submission folder
COPY . .

# Default: every README step in order, from the organiser files to the validated test forecast
ENV PYTHONUNBUFFERED=1 MPLCONFIGDIR=/tmp
EXPOSE 8000
CMD ["sh", "-c", "python -m src.make_wide && python -m src.run baseline && python -m pytest tests/ -q && python -m src.run folds && python -m src.run validation && python -m src.run final"]
