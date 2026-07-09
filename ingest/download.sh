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

read -r FMT SOV DC GEO < <("$PY" - "$EID" "$ROOT" <<'PY'
import json, os, sys
eid, root = sys.argv[1], sys.argv[2]
m = json.load(open(os.path.join(root, "data/processed/elections.json")))
e = next(x for x in m["elections"] if x["id"] == eid)
s = e["sources"]
print(e.get("format", "xlsx"), s["sov"], s.get("district_canvass_xlsx", "-"), s["precincts_geojson"])
PY
)
EXT="$FMT"   # xlsx | xls | csv — the saved sov file extension

# Some acvote/ArcGIS endpoints reject the default curl UA (500) or a missing
# Referer (403), so send a browser UA + the data hub as Referer on every request.
UA="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
REFERER="https://data.acgov.org/"

fetch() {  # url dest min_bytes label
  local url="$1" dest="$2" min="$3" label="$4"
  local code sz
  if [ -z "${FORCE_DOWNLOAD:-}" ] && [ -s "$dest" ] && [ "$(wc -c < "$dest")" -ge "$min" ]; then
    echo "  cached $label ($(wc -c < "$dest") bytes)"; return 0
  fi
  read -r code sz < <(curl -sSL -A "$UA" -e "$REFERER" -o "$dest" -w "%{http_code} %{size_download}\n" "$url")
  if [ "$code" != "200" ] || [ "$sz" -lt "$min" ]; then
    echo "  ERROR $label: http=$code size=$sz (< $min) url=$url" >&2
    return 1
  fi
  echo "  ok $label: $sz bytes"
}

echo "downloading $EID -> $RAW"
rm -f "$RAW/sov.xlsx" "$RAW/sov.xls" "$RAW/sov.csv" "$RAW/district_canvass.xlsx"  # avoid stale from a prior format
fetch "$SOV" "$RAW/sov.$EXT"             20000 "sov.$EXT"
fetch "$GEO" "$RAW/precincts.geojson"    10000 "precincts.geojson"
if [ "$DC" != "-" ]; then
  fetch "$DC" "$RAW/district_canvass.xlsx" 20000 "district_canvass.xlsx"
else
  echo "  (no district canvass published for this election)"
fi
