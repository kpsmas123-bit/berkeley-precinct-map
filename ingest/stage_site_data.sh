#!/usr/bin/env bash
# Copy processed data into site/data/ so the static site can fetch from ./data
# (keeps the published GitHub Pages tree self-contained).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
mkdir -p "$ROOT/site/data/results" "$ROOT/site/data/geo"
cp "$ROOT/data/processed/elections.json" "$ROOT/site/data/elections.json"
cp "$ROOT/data/processed/results/"*.json "$ROOT/site/data/results/"
cp "$ROOT/data/processed/geo/"*.geojson  "$ROOT/site/data/geo/"
for f in measures.json alignment.json featured.json; do
  [ -f "$ROOT/data/processed/$f" ] && cp "$ROOT/data/processed/$f" "$ROOT/site/data/$f"
done
echo "staged processed data -> site/data/"
