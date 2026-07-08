#!/usr/bin/env bash
# End-to-end build for one election:
#   download -> fetch district maps -> parse -> geo -> assign districts -> QA -> stage.
# Usage: ./build.sh [election_id]   (default 2024-11-general)
set -euo pipefail
ROOT="$(cd "$(dirname "$0")" && pwd)"
EID="${1:-2024-11-general}"
PY="$ROOT/.venv/bin/python"
[ -x "$PY" ] || PY="python3"

RAW="$ROOT/data/raw/$EID"
RES="$ROOT/data/processed/results/$EID.json"
GEO="$ROOT/data/processed/geo/$EID.geojson"

# Resolve this election's district-map key + overlay path from the manifest.
read -r MAPKEY DGEO < <("$PY" - "$EID" "$ROOT" <<'PY'
import json, os, sys
eid, root = sys.argv[1], sys.argv[2]
m = json.load(open(os.path.join(root, "data/processed/elections.json")))
e = next(x for x in m["elections"] if x["id"] == eid)
print(e["district_map"], e["districts_geo"])
PY
)
DMAP="$ROOT/data/district_maps/$MAPKEY.geojson"
DGEO="$ROOT/data/processed/$DGEO"

echo "== [0] download canvass + precinct geometry =="
bash "$ROOT/ingest/download.sh" "$EID"

echo "== [1] fetch council-district maps (both eras) =="
"$PY" "$ROOT/ingest/fetch_district_maps.py"

echo "== [2] parse canvass =="
"$PY" "$ROOT/ingest/parse_canvass.py" "$RAW/sov.xlsx" "$EID" "$RES"

echo "== [3] precinct geometry =="
"$PY" "$ROOT/ingest/build_geo.py" "$RAW/precincts.geojson" "$RES" "$GEO"

echo "== [4] assign precincts -> districts ($MAPKEY) =="
"$PY" "$ROOT/ingest/assign_districts.py" "$RES" "$GEO" "$DMAP" "$MAPKEY"

echo "== [5] per-election district overlay =="
"$PY" "$ROOT/ingest/build_districts.py" "$DMAP" "$DGEO"

echo "== [6] QA reconciliation (fails on >0.5% mismatch) =="
"$PY" "$ROOT/ingest/qa.py" "$RAW/district_canvass.xlsx" "$RES"

echo "== [7] stage site data =="
bash "$ROOT/ingest/stage_site_data.sh"

echo "== done. serve with:  python3 -m http.server 8777 --directory site  =="
