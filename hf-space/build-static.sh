#!/bin/sh
# Assemble hf-space/static-dist for a Hugging Face Static Space: the page, the precomputed forecasts and the spot price as a plain file.
set -e
cd "$(dirname "$0")/.."
OUT=hf-space/static-dist
rm -rf "$OUT" && mkdir -p "$OUT/api"
cp -R dashboard/web/. "$OUT/"
cp hf-space/static-README.md "$OUT/README.md"
# api/spot is read by the page like the live endpoint, so the spot line is drawn
python3 - <<'PY'
import csv, json
from datetime import datetime, timezone
with open("data/inputs_wide.csv", newline="") as src:
    rows = csv.reader(src)
    header = next(rows)
    t, v = header.index("timestamp_utc"), header.index("fi_spot_price")
    data = list(rows)
t0 = int(datetime.strptime(data[0][t], "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc).timestamp() * 1000)
values = [round(float(r[v]), 2) if r[v] != "" else None for r in data]
json.dump({"t0": t0, "step": 900000, "values": values}, open("hf-space/static-dist/api/spot", "w"), separators=(",", ":"))
PY
find "$OUT" -name .DS_Store -delete
echo "Built $OUT"; du -sh "$OUT"; ls "$OUT" "$OUT/api"
