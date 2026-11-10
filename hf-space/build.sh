#!/bin/sh
# Assemble hf-space/dist: only what the hosted app needs. From data/ only the spot price column is copied (the API's /api/spot reads it).
set -e
cd "$(dirname "$0")/.."
OUT=hf-space/dist
rm -rf "$OUT" && mkdir -p "$OUT/organiser" "$OUT/artifacts/models" "$OUT/dashboard"

cp hf-space/Dockerfile hf-space/README.md hf-space/requirements.txt "$OUT/"
cp -R src "$OUT/src"
cp organiser/validate_submission.py organiser/score.py "$OUT/organiser/"
cp artifacts/models/final_models.joblib "$OUT/artifacts/models/"
cp artifacts/run_manifest.json "$OUT/artifacts/"
cp dashboard/*.py dashboard/feature_quantiles.json "$OUT/dashboard/"
cp -R dashboard/web "$OUT/dashboard/web"
mkdir -p "$OUT/data"
python3 - <<'PY'
import csv
with open("data/inputs_wide.csv", newline="") as src, open("hf-space/dist/data/inputs_wide.csv", "w", newline="") as dst:
    rows = csv.reader(src)
    header = next(rows)
    keep = [header.index("timestamp_utc"), header.index("fi_spot_price")]
    out = csv.writer(dst, lineterminator="\n")
    out.writerow([header[k] for k in keep])
    for r in rows:
        out.writerow([r[k] for k in keep])
PY
find "$OUT" -name __pycache__ -prune -exec rm -rf {} + -o -name .DS_Store -delete

echo "Built $OUT"; du -sh "$OUT"; find "$OUT" -type f -size +5M -exec ls -lh {} \;
head -2 "$OUT/data/inputs_wide.csv"
