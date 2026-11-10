#!/usr/bin/env bash
# Countywide map build: every Alameda County precinct, big shared-ballot contests
# only (statewide offices, Congress, state propositions — see ingest/county_contests.py).
#
# Reuses the Berkeley pipeline's downloaders and canvass parsers unchanged; the only
# difference is that the parsers are handed the COUNTY precinct-id list instead of the
# Berkeley one, and the result is then trimmed to the big-contest whitelist.
#
# Usage:
#   ./build_county.sh                # build every eligible election
#   ./build_county.sh all            # same
#   ./build_county.sh <election_id>  # build just one
#
# Eligible = in data/processed/elections.json, dated on/after COUNTY_FROM, and with a
# published precinct canvass (a pending election has no precinct tallies to map).
set -uo pipefail
ROOT="$(cd "$(dirname "$0")" && pwd)"
PY="$ROOT/.venv/bin/python"; [ -x "$PY" ] || PY="python3"
ARG="${1:-all}"
COUNTY_FROM="${COUNTY_FROM:-2020-01-01}"

CDIR="$ROOT/data/processed/county"
mkdir -p "$CDIR/geo" "$CDIR/ids" "$CDIR/results" "$CDIR/tmp"

ids_eligible() { "$PY" - "$ROOT" "$COUNTY_FROM" <<'PY'
import json, os, sys
root, since = sys.argv[1], sys.argv[2]
m = json.load(open(os.path.join(root, "data/processed/elections.json")))
for e in m["elections"]:
    if e["date"] >= since and e.get("precinct_results", True):
        print(e["id"])
PY
}
meta_of() { "$PY" - "$1" "$ROOT" <<'PY'
import json, os, sys
eid, root = sys.argv[1], sys.argv[2]
m = json.load(open(os.path.join(root, "data/processed/elections.json")))
e = next(x for x in m["elections"] if x["id"] == eid)
print(e.get("format", "xlsx"), e["date"], e["name"].replace(" ", "_"))
PY
}

echo "== city boundaries (once) =="
"$PY" "$ROOT/ingest/fetch_city_boundaries.py" || exit 1

build_one() {
  local EID="$1"
  local RAW="$ROOT/data/raw/$EID"
  local GEO="$CDIR/geo/$EID.geojson" IDS="$CDIR/ids/$EID.json"
  local TMP="$CDIR/tmp/$EID.full.json" OUT="$CDIR/results/$EID.json"
  local FMT DATE NAME
  read -r FMT DATE NAME < <(meta_of "$EID") || { echo "  [$EID] not in manifest"; return 1; }
  local PARSER="parse_canvass.py"; [ "$FMT" = "csv" ] && PARSER="parse_sovc_csv.py"

  echo "──────── $EID  (county, format: $FMT) ────────"
  bash "$ROOT/ingest/download.sh" "$EID" || { echo "  FAIL download"; return 1; }
  "$PY" "$ROOT/ingest/build_county_geo.py" \
        "$RAW/precincts.geojson" "$CDIR/cities.geojson" "$GEO" "$IDS" \
        || { echo "  FAIL county geo"; return 1; }
  "$PY" "$ROOT/ingest/$PARSER" "$RAW/sov.$FMT" "$EID" "$TMP" "$IDS" \
        || { echo "  FAIL parse"; return 1; }
  "$PY" "$ROOT/ingest/filter_county_results.py" "$TMP" "$GEO" "$OUT" \
        || { echo "  FAIL filter"; return 1; }
  rm -f "$TMP"
  return 0
}

if [ "$ARG" = "all" ]; then IDS_LIST="$(ids_eligible)"; else IDS_LIST="$ARG"; fi

declare -a OK=() BAD=()
while read -r EID; do
  [ -z "$EID" ] && continue
  if build_one "$EID"; then OK+=("$EID"); else BAD+=("$EID"); fi
done <<< "$IDS_LIST"

echo "== county manifest =="
"$PY" "$ROOT/ingest/build_county_manifest.py" || exit 1

echo "== stage county data =="
bash "$ROOT/ingest/stage_site_data.sh"

echo ""
echo "════════ COUNTY BUILD SUMMARY ════════"
echo "  built:  ${OK[*]:-none}"
echo "  failed: ${BAD[*]:-none}"
echo "open:  http://localhost:8777/county.html"
[ ${#BAD[@]} -eq 0 ]
