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
# Eligible = in data/processed/elections.json and dated on/after COUNTY_FROM. An
# election whose certified canvass is published builds the normal way; one still
# awaiting certification builds in PRELIMINARY mode from the county's live feeds
# instead (see ingest/fetch_live_county.py), which is cheap to re-run as the count
# updates.
set -uo pipefail
ROOT="$(cd "$(dirname "$0")" && pwd)"
PY="$ROOT/.venv/bin/python"; [ -x "$PY" ] || PY="python3"
ARG="${1:-all}"
# Recent elections only. Pre-2024 county results were dropped deliberately: the
# patterns have shifted enough to be of limited use, and each one is ~110-280 KB of
# precinct tallies. Raising this back (COUNTY_FROM=2020-01-01 ./build_county.sh)
# rebuilds them from the raw canvasses, which are still in data/raw.
COUNTY_FROM="${COUNTY_FROM:-2024-01-01}"

CDIR="$ROOT/data/processed/county"
mkdir -p "$CDIR/geo" "$CDIR/ids" "$CDIR/results" "$CDIR/tmp"

# prints "<election_id> <certified|preliminary>"
ids_eligible() { "$PY" - "$ROOT" "$COUNTY_FROM" <<'PY'
import json, os, sys
root, since = sys.argv[1], sys.argv[2]
m = json.load(open(os.path.join(root, "data/processed/elections.json")))
for e in m["elections"]:
    if e["date"] < since:
        continue
    if e.get("precinct_results", True):
        print(e["id"], "certified")
    elif e.get("rov_election_id"):
        print(e["id"], "preliminary")
PY
}
# prints "<certified|preliminary|missing> <rov_election_id or ->"
mode_of() { "$PY" - "$1" "$ROOT" <<'PY'
import json, os, sys
eid, root = sys.argv[1], sys.argv[2]
m = json.load(open(os.path.join(root, "data/processed/elections.json")))
e = next((x for x in m["elections"] if x["id"] == eid), None)
if e is None:
    print("missing -")
else:
    print("certified" if e.get("precinct_results", True) else "preliminary",
          e.get("rov_election_id", "-"))
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
  local REGF="$ROOT/data/processed/registration/$EID.json"
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

  # Party registration is a separate publisher on a separate schedule, so it is
  # fetched and merged after the tallies rather than inside a parser.
  "$PY" "$ROOT/ingest/fetch_registration.py" "$EID" "$REGF" \
    && "$PY" "$ROOT/ingest/attach_registration.py" "$OUT" "$REGF" \
    || echo "  (registration unavailable for $EID — results unchanged)"
  return 0
}

# Preliminary build: no certified canvass exists, so precinct-level figures come from
# the county's live results-map feed (only the contests it maps) and every other big
# race is carried as countywide totals. Re-running after certification takes the
# certified path above and overwrites the same file.
build_preliminary() {
  local EID="$1" ROVID="$2"
  local RAW="$ROOT/data/raw/$EID"
  local GEO="$CDIR/geo/$EID.geojson" IDS="$CDIR/ids/$EID.json" OUT="$CDIR/results/$EID.json"
  local REGF="$ROOT/data/processed/registration/$EID.json"

  # A Cast Vote Record export, if one has been obtained, beats the live map feed by
  # a mile: one record per ballot, every contest, with the precinct on it. Drop it at
  # data/raw/<eid>/cvr/export.zip (gitignored; a symlink is fine) or point CVR_EXPORT
  # at it. Without one, the live results-map feed is used and only the one or two
  # contests the county chooses to map get precinct figures.
  local CVR="${CVR_EXPORT:-$RAW/cvr/export.zip}"
  local PARSED="$CDIR/tmp/$EID.cvr.json"

  echo "──────── $EID  (county, PRELIMINARY) ────────"
  bash "$ROOT/ingest/download.sh" "$EID" || { echo "  FAIL download"; return 1; }
  "$PY" "$ROOT/ingest/build_county_geo.py" \
        "$RAW/precincts.geojson" "$CDIR/cities.geojson" "$GEO" "$IDS" \
        || { echo "  FAIL county geo"; return 1; }

  if [ -e "$CVR" ]; then
    echo "  source: cast vote record ($CVR)"
    "$PY" "$ROOT/ingest/parse_cvr.py" "$CVR" "$EID" "$PARSED" \
          --precinct-ids="$IDS" --quiet \
          || { echo "  FAIL CVR parse"; return 1; }
    "$PY" "$ROOT/ingest/fetch_live_county.py" "$EID" "$GEO" "$OUT" \
          --rov-id="$ROVID" --from-cvr="$PARSED" \
          || { echo "  FAIL county results from CVR"; return 1; }
    rm -f "$PARSED"
  else
    echo "  source: live results-map feed (no CVR at $CVR)"
    "$PY" "$ROOT/ingest/fetch_live_county.py" "$EID" "$GEO" "$OUT" --rov-id="$ROVID" \
          || { echo "  FAIL live county results"; return 1; }
  fi

  # Party registration is a separate publisher on a separate schedule, so it is
  # fetched and merged after the tallies rather than inside a parser.
  "$PY" "$ROOT/ingest/fetch_registration.py" "$EID" "$REGF" \
    && "$PY" "$ROOT/ingest/attach_registration.py" "$OUT" "$REGF" \
    || echo "  (registration unavailable for $EID — results unchanged)"

  return 0
}

if [ "$ARG" = "all" ]; then
  IDS_LIST="$(ids_eligible)"
else
  IDS_LIST="$ARG $(mode_of "$ARG" | cut -d' ' -f1)"
fi

# The corrections a preliminary build leans on are learned from certified builds, so
# refresh them before building anything.
echo "== ballot-derived city corrections (from certified builds) =="
"$PY" "$ROOT/ingest/build_city_overrides.py" || true

declare -a OK=() PRELIM=() BAD=()
while read -r EID MODE; do
  [ -z "$EID" ] && continue
  case "$MODE" in
    preliminary)
      read -r _ ROVID < <(mode_of "$EID")
      if [ "$ROVID" = "-" ]; then
        echo "  [$EID] preliminary build needs rov_election_id in the manifest"
        BAD+=("$EID")
      elif build_preliminary "$EID" "$ROVID"; then PRELIM+=("$EID"); else BAD+=("$EID"); fi
      ;;
    missing)
      echo "  [$EID] not in manifest"; BAD+=("$EID") ;;
    *)
      if build_one "$EID"; then OK+=("$EID"); else BAD+=("$EID"); fi ;;
  esac
done <<< "$IDS_LIST"

# a fresh certified build may have taught us new corrections
"$PY" "$ROOT/ingest/build_city_overrides.py" >/dev/null 2>&1 || true

echo "== county manifest =="
"$PY" "$ROOT/ingest/build_county_manifest.py" || exit 1

echo "== stage county data =="
bash "$ROOT/ingest/stage_site_data.sh"

echo ""
echo "════════ COUNTY BUILD SUMMARY ════════"
echo "  built:       ${OK[*]:-none}"
echo "  preliminary: ${PRELIM[*]:-none}"
echo "  failed:      ${BAD[*]:-none}"
echo "open:  http://localhost:8777/county.html"
[ ${#BAD[@]} -eq 0 ]
