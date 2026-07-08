# Berkeley Precinct Election Map — Build Plan

**Goal:** Static web map (GitHub Pages) showing precinct-level results for all
Berkeley-relevant elections ~2014–present. Focus: Council District 1. Contests: all
local (council, mayor, school board, rent board, city measures) plus county/state
contests on Berkeley ballots.

**Stack:** Python ingestion → static JSON/GeoJSON → MapLibre GL JS frontend. No backend.

## Build order

1. **Nov 2024 end-to-end** (download → parse → geo → map renders one contest) ✅ **done**
2. Frontend polish + QA harness ✅ **done** (QA reconciles exactly vs certified District Canvass)
3. Backfill remaining elections newest→oldest (formats get worse going back)
4. 2014/older via Statewide Database only if ROV archive fails

## Target election inventory (Phase 0)

- **Generals:** Nov 2014, 2016, 2018, 2020, 2022, **2024 ✅**
- **Primaries:** Jun 2014, Jun 2016, Jun 2018, Mar 2020, Jun 2022, Mar 2024, Jun 2026
- **Statewide specials touching Berkeley:** Sep 2021 gubernatorial recall
- **Berkeley specials:** D7 (Apr 2024), D4 (May 2024) — not D1, include for completeness
- Skip specials with no Berkeley precincts (2021 AD-18, Oakland-only, Sunol)

For each: Precinct Canvass (SOV) XLSX (fall back to PDF / Statewide Database for older
years) + matching Consolidated Precincts GeoJSON from the county Open Data Hub. Record
every source URL in `data/processed/elections.json`.

## Watch-outs

- **Precinct IDs are not stable across elections.** Never join results from one election
  to another election's geometry.
- **RCV:** no precinct-level redistribution exists; don't fake it (first-choice only).
- **Consolidations:** "no vote data" precincts are usually merges, not zeros — handle
  explicitly or the map lies.
- **D1 boundary changed with 2021 redistricting;** pre-2022 precincts won't nest cleanly
  in current D1. Show current D1 overlay on all years but don't claim historical D1
  aggregates without a crosswalk.
- **Format drift** means: build one election end-to-end first (Nov 2024), then generalize.

## Repo layout

```
berkeley-precinct-map/
├── build.sh                 # download → parse → geo → QA → stage, for one election
├── data/
│   ├── raw/<id>/            # downloaded canvass xlsx + precinct geojson
│   └── processed/
│       ├── elections.json   # manifest: id, date, name, sources, file paths
│       ├── results/<id>.json
│       └── geo/<id>.geojson + d1_boundary.geojson + council_districts.geojson
├── ingest/
│   ├── download.sh          # Phase 0 fetch
│   ├── parse_canvass.py     # SOV xlsx → normalized results (Berkeley-filtered)
│   ├── build_geo.py         # county geojson → simplified Berkeley precincts + join validation
│   ├── build_districts.py   # 2022 council layer → D1 + all-district overlays
│   ├── qa.py                # reconcile precinct sums vs certified District Canvass
│   └── stage_site_data.sh   # processed → site/data
├── site/                    # static MapLibre frontend (index.html + data/)
└── PLAN.md
```
