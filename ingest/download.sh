#!/usr/bin/env bash
# Phase 0 — download raw canvass + geometry for one election.
# Usage: download.sh <election_id>   (currently supports 2024-11-general)
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
EID="${1:-2024-11-general}"
RAW="$ROOT/data/raw/$EID"
mkdir -p "$RAW"

case "$EID" in
  2024-11-general)
    SOV="https://acvote.alamedacountyca.gov/acvote-assets/02_election_information/SOV/20241105"
    curl -sSL -o "$RAW/sov.xlsx"              "$SOV/Statement%20of%20Vote%20-%20General%20Election.xlsx"
    curl -sSL -o "$RAW/district_canvass.xlsx" "$SOV/District%20Canvas%20-%20General%20Election.xlsx"
    # Consolidated precincts (ArcGIS Hub dataset 7c46f7548f8c41d8abb5219faa3b82c6_0)
    curl -sSL -o "$RAW/precincts.geojson" \
      "https://opendata.arcgis.com/api/v3/datasets/7c46f7548f8c41d8abb5219faa3b82c6_0/downloads/data?format=geojson&spatialRefId=4326"
    ;;
  *)
    echo "Unknown election id: $EID (add a case block in download.sh)"; exit 1 ;;
esac
echo "downloaded raw files -> $RAW"
ls -la "$RAW"
# Council-district boundary sets are fetched separately by ingest/fetch_district_maps.py.
