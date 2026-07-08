#!/usr/bin/env bash
# Phase 0 — download raw canvass + precinct geometry for one election.
# URLs come from data/processed/elections.json (sources.{sov_xlsx,
# district_canvass_xlsx, precincts_geojson}); adding an election = adding a
# manifest entry, no code change.
# Usage: download.sh <election_id>
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
EID="${1:?usage: download.sh <election_id>}"
RAW="$ROOT/data/raw/$EID"
mkdir -p "$RAW"
PY="$ROOT/.venv/bin/python"; [ -x "$PY" ] || PY="python3"

read -r SOV DC GEO < <("$PY" - "$EID" "$ROOT" <<'PY'
import json, os, sys
eid, root = sys.argv[1], sys.argv[2]
m = json.load(open(os.path.join(root, "data/processed/elections.json")))
e = next(x for x in m["elections"] if x["id"] == eid)
s = e["sources"]
print(s["sov_xlsx"], s["district_canvass_xlsx"], s["precincts_geojson"])
PY
)

# Some acvote/ArcGIS endpoints reject the default curl UA (500) or a missing
# Referer (403), so send a browser UA + the data hub as Referer on every request.
UA="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
REFERER="https://data.acgov.org/"

fetch() {  # url dest min_bytes label
  local url="$1" dest="$2" min="$3" label="$4"
  local code sz
  read -r code sz < <(curl -sSL -A "$UA" -e "$REFERER" -o "$dest" -w "%{http_code} %{size_download}\n" "$url")
  if [ "$code" != "200" ] || [ "$sz" -lt "$min" ]; then
    echo "  ERROR $label: http=$code size=$sz (< $min) url=$url" >&2
    return 1
  fi
  echo "  ok $label: $sz bytes"
}

echo "downloading $EID -> $RAW"
fetch "$SOV" "$RAW/sov.xlsx"              100000 "sov.xlsx"
fetch "$DC"  "$RAW/district_canvass.xlsx" 100000 "district_canvass.xlsx"
fetch "$GEO" "$RAW/precincts.geojson"     10000  "precincts.geojson"
