#!/usr/bin/env bash
# Copy processed data into site/data/ so the static site can fetch from ./data
# (keeps the published GitHub Pages tree self-contained).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
mkdir -p "$ROOT/site/data/results" "$ROOT/site/data/geo"
cp "$ROOT/data/processed/elections.json" "$ROOT/site/data/elections.json"
cp "$ROOT/data/processed/results/"*.json "$ROOT/site/data/results/"
cp "$ROOT/data/processed/geo/"*.geojson  "$ROOT/site/data/geo/"
for f in measures.json alignment.json featured.json history.json crosswalk.json; do
  [ -f "$ROOT/data/processed/$f" ] && cp "$ROOT/data/processed/$f" "$ROOT/site/data/$f"
done

# countywide map data (built separately by ./build_county.sh)
if [ -d "$ROOT/data/processed/county" ]; then
  mkdir -p "$ROOT/site/data/county/geo"
  for f in elections.json cities.geojson; do
    [ -f "$ROOT/data/processed/county/$f" ] && cp "$ROOT/data/processed/county/$f" "$ROOT/site/data/county/$f"
  done
  if [ -d "$ROOT/data/processed/county/split" ]; then
    rm -rf "$ROOT/site/data/county/split"
    cp -R "$ROOT/data/processed/county/split" "$ROOT/site/data/county/split"
  fi
  # Single-file results are the pre-split format. Stage one only where no split
  # exists, so the two formats never ship the same election twice.
  for f in "$ROOT/data/processed/county/results/"*.json; do
    [ -e "$f" ] || continue
    eid="$(basename "$f" .json)"
    if [ ! -d "$ROOT/data/processed/county/split/$eid" ]; then
      mkdir -p "$ROOT/site/data/county/results"
      cp "$f" "$ROOT/site/data/county/results/$eid.json"
    else
      rm -f "$ROOT/site/data/county/results/$eid.json"
    fi
  done
  rmdir "$ROOT/site/data/county/results" 2>/dev/null || true
  if compgen -G "$ROOT/data/processed/county/geo/*.geojson" > /dev/null; then
    cp "$ROOT/data/processed/county/geo/"*.geojson "$ROOT/site/data/county/geo/"
  fi
  echo "staged county data   -> site/data/county/"
fi
echo "staged processed data -> site/data/"
