#!/usr/bin/env bash
# End-to-end build. Per election: download -> parse -> geo -> assign districts ->
# QA. District maps are fetched once; site data is staged once at the end.
#
# Usage:
#   ./build.sh                 # build every election in the manifest
#   ./build.sh all             # same
#   ./build.sh <election_id>   # build just one
set -uo pipefail
ROOT="$(cd "$(dirname "$0")" && pwd)"
PY="$ROOT/.venv/bin/python"; [ -x "$PY" ] || PY="python3"
ARG="${1:-all}"

ids_all() { "$PY" - "$ROOT" <<'PY'
import json, os, sys
m = json.load(open(os.path.join(sys.argv[1], "data/processed/elections.json")))
print("\n".join(e["id"] for e in m["elections"]))
PY
}
meta_of() { "$PY" - "$1" "$ROOT" <<'PY'
import json, os, sys
eid, root = sys.argv[1], sys.argv[2]
m = json.load(open(os.path.join(root, "data/processed/elections.json")))
e = next(x for x in m["elections"] if x["id"] == eid)
print(e["district_map"], e["districts_geo"])
PY
}

build_one() {
  local EID="$1"
  local RAW="$ROOT/data/raw/$EID" RES="$ROOT/data/processed/results/$EID.json" GEO="$ROOT/data/processed/geo/$EID.geojson"
  local IDS="$RAW/berkeley_ids.json"
  local MAPKEY DGEO
  read -r MAPKEY DGEO < <(meta_of "$EID") || { echo "  [$EID] not in manifest"; return 1; }
  local DMAP="$ROOT/data/district_maps/$MAPKEY.geojson" DGEOP="$ROOT/data/processed/$DGEO"
  echo "──────── $EID  (map: $MAPKEY) ────────"
  bash "$ROOT/ingest/download.sh" "$EID"                                          || { echo "  FAIL download"; return 1; }
  "$PY" "$ROOT/ingest/build_geo.py" "$RAW/precincts.geojson" "$DMAP" "$GEO" "$IDS" || { echo "  FAIL geo"; return 1; }
  "$PY" "$ROOT/ingest/parse_canvass.py" "$RAW/sov.xlsx" "$EID" "$RES" "$IDS"      || { echo "  FAIL parse"; return 1; }
  "$PY" "$ROOT/ingest/assign_districts.py" "$RES" "$GEO" "$DMAP" "$MAPKEY"        || { echo "  FAIL assign"; return 1; }
  "$PY" "$ROOT/ingest/build_districts.py" "$DMAP" "$DGEOP"                        || { echo "  FAIL overlay"; return 1; }
  "$PY" "$ROOT/ingest/qa.py" "$RAW/district_canvass.xlsx" "$RES"                  || { echo "  ⚠ QA mismatch (see above)"; return 2; }
  return 0
}

echo "== fetch council-district maps (both eras) =="
"$PY" "$ROOT/ingest/fetch_district_maps.py"

if [ "$ARG" = "all" ]; then IDS="$(ids_all)"; else IDS="$ARG"; fi

declare -a OK=() WARN=() BAD=()
while read -r EID; do
  [ -z "$EID" ] && continue
  build_one "$EID"; rc=$?
  if   [ $rc -eq 0 ]; then OK+=("$EID")
  elif [ $rc -eq 2 ]; then WARN+=("$EID")
  else BAD+=("$EID"); fi
done <<< "$IDS"

echo "== stage site data =="
bash "$ROOT/ingest/stage_site_data.sh"

echo ""
echo "════════ BUILD SUMMARY ════════"
echo "  clean:    ${OK[*]:-none}"
echo "  QA warn:  ${WARN[*]:-none}"
echo "  failed:   ${BAD[*]:-none}"
echo "serve with:  python3 -m http.server 8777 --directory site"
[ ${#BAD[@]} -eq 0 ]
