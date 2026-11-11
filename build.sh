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
print(e["district_map"], e["districts_geo"], e.get("format", "xlsx"),
      "pending" if not e.get("precinct_results", True) else "full",
      e.get("rov_election_id", "-"), e.get("citywide", "-"))
PY
}

build_one() {
  local EID="$1"
  local RAW="$ROOT/data/raw/$EID" RES="$ROOT/data/processed/results/$EID.json" GEO="$ROOT/data/processed/geo/$EID.geojson"
  local IDS="$RAW/berkeley_ids.json"
  local REGF="$ROOT/data/processed/registration/$EID.json"
  local MAPKEY DGEO FMT STATE ROVID CITYREL
  read -r MAPKEY DGEO FMT STATE ROVID CITYREL < <(meta_of "$EID") || { echo "  [$EID] not in manifest"; return 1; }
  local DMAP="$ROOT/data/district_maps/$MAPKEY.geojson" DGEOP="$ROOT/data/processed/$DGEO"
  local EXT="$FMT"   # xlsx | xls | csv
  local PARSER="parse_canvass.py"; [ "$FMT" = "csv" ] && PARSER="parse_sovc_csv.py"
  echo "──────── $EID  (map: $MAPKEY, format: $FMT, $STATE) ────────"
  bash "$ROOT/ingest/download.sh" "$EID"                                          || { echo "  FAIL download"; return 1; }
  "$PY" "$ROOT/ingest/build_geo.py" "$RAW/precincts.geojson" "$DMAP" "$GEO" "$IDS" || { echo "  FAIL geo"; return 1; }
  if [ "$STATE" = "pending" ]; then
    # Precinct canvass not published yet: citywide totals + precinct roster only.
    local CITY="$ROOT/data/processed/$CITYREL"
    mkdir -p "$(dirname "$CITY")"
    "$PY" "$ROOT/ingest/fetch_live_results.py" "$ROVID" "$CITY"                   || { echo "  FAIL live results"; return 1; }
    # A Cast Vote Record export, if obtained, carries EVERY contest on the ballot
    # precinct by precinct — including CD-12, which the county's results map omits.
    # Drop it at data/raw/<eid>/cvr/export.zip (gitignored; a symlink is fine) or
    # point CVR_EXPORT at it; without one the live results map is used instead.
    local CVR="${CVR_EXPORT:-$RAW/cvr/export.zip}"
    local CVRJSON="$ROOT/data/processed/results/$EID.cvr.json"
    if [ -e "$CVR" ]; then
      echo "  precinct source: cast vote record ($CVR)"
      "$PY" "$ROOT/ingest/parse_cvr.py" "$CVR" "$EID" "$CVRJSON" \
            --precinct-ids="$IDS" --quiet                                        || { echo "  FAIL CVR parse"; return 1; }
      "$PY" "$ROOT/ingest/build_pending_results.py" "$EID" "$GEO" "$IDS" "$CITY" "$RES" \
            --from-cvr="$CVRJSON"                                                || { echo "  FAIL pending results"; return 1; }
      rm -f "$CVRJSON"
    else
      echo "  precinct source: live results-map feed (no CVR at $CVR)"
      "$PY" "$ROOT/ingest/build_pending_results.py" "$EID" "$GEO" "$IDS" "$CITY" "$RES" || { echo "  FAIL pending results"; return 1; }
    fi
    "$PY" "$ROOT/ingest/assign_districts.py" "$RES" "$GEO" "$DMAP" "$MAPKEY"      || { echo "  FAIL assign"; return 1; }
  "$PY" "$ROOT/ingest/fetch_registration.py" "$EID" "$REGF" \
    && "$PY" "$ROOT/ingest/attach_registration.py" "$RES" "$REGF" \
    || echo "  (registration unavailable for $EID — results unchanged)"

    "$PY" "$ROOT/ingest/build_districts.py" "$DMAP" "$DGEOP"                      || { echo "  FAIL overlay"; return 1; }
    echo "  QA skipped (awaiting certified canvass)"
    return 0
  fi
  "$PY" "$ROOT/ingest/$PARSER" "$RAW/sov.$EXT" "$EID" "$RES" "$IDS"               || { echo "  FAIL parse"; return 1; }
  "$PY" "$ROOT/ingest/assign_districts.py" "$RES" "$GEO" "$DMAP" "$MAPKEY"        || { echo "  FAIL assign"; return 1; }
  "$PY" "$ROOT/ingest/build_districts.py" "$DMAP" "$DGEOP"                        || { echo "  FAIL overlay"; return 1; }
  local rc=0
  if [ -f "$RAW/district_canvass.xlsx" ]; then
    "$PY" "$ROOT/ingest/qa.py" "$RAW/district_canvass.xlsx" "$RES" || { echo "  ⚠ QA mismatch (see above)"; rc=2; }
  else
    "$PY" - "$RES" <<'PY'
import json,sys; r=json.load(open(sys.argv[1])); r["qa"]="none"; json.dump(r,open(sys.argv[1],"w"),separators=(",",":")); print("  QA skipped (no certified canvass published)")
PY
  fi
  "$PY" "$ROOT/ingest/fetch_registration.py" "$EID" "$REGF" \
    && "$PY" "$ROOT/ingest/attach_registration.py" "$RES" "$REGF" \
    || echo "  (registration unavailable for $EID — results unchanged)"
  "$PY" "$ROOT/ingest/annotate_contests.py" "$RES" || echo "  (annotate failed)"
  return $rc
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

echo "== competitive ballot-measure slots (Feature 3 plumbing) =="
"$PY" "$ROOT/ingest/build_measures.py"

echo "== featured contests (auto-rank) =="
"$PY" "$ROOT/ingest/build_featured.py"

echo "== stage site data =="
bash "$ROOT/ingest/stage_site_data.sh"

echo ""
echo "════════ BUILD SUMMARY ════════"
echo "  clean:    ${OK[*]:-none}"
echo "  QA warn:  ${WARN[*]:-none}"
echo "  failed:   ${BAD[*]:-none}"
echo "serve with:  python3 -m http.server 8777 --directory site"
[ ${#BAD[@]} -eq 0 ]
