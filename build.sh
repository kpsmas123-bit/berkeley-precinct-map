#!/usr/bin/env bash
# End-to-end build for one election: download -> parse -> geo -> QA -> stage site.
# Usage: ./build.sh [election_id]   (default 2024-11-general)
set -euo pipefail
ROOT="$(cd "$(dirname "$0")" && pwd)"
EID="${1:-2024-11-general}"
PY="$ROOT/.venv/bin/python"
[ -x "$PY" ] || PY="python3"

RAW="$ROOT/data/raw/$EID"
RES="$ROOT/data/processed/results/$EID.json"
GEO="$ROOT/data/processed/geo/$EID.geojson"

echo "== [0] download =="
bash "$ROOT/ingest/download.sh" "$EID"

echo "== [1] parse canvass =="
"$PY" "$ROOT/ingest/parse_canvass.py" "$RAW/sov.xlsx" "$EID" "$RES"

echo "== [2] geometry =="
"$PY" "$ROOT/ingest/build_geo.py" "$RAW/precincts.geojson" "$RES" "$GEO"
"$PY" "$ROOT/ingest/build_districts.py" "$ROOT/data/raw/council_districts_2022.geojson" "$ROOT/data/processed/geo"

echo "== [3] QA reconciliation (fails on >0.5% mismatch) =="
"$PY" "$ROOT/ingest/qa.py" "$RAW/district_canvass.xlsx" "$RES"

echo "== [4] stage site data =="
bash "$ROOT/ingest/stage_site_data.sh"

echo "== done. serve with:  python3 -m http.server 8777 --directory site  =="
