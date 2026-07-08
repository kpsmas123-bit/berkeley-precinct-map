# Berkeley Precinct Election Map

Static web map showing **precinct-level results** for Berkeley-relevant elections
(~2014–present), with a focus on **City Council District 1**. Python ingestion →
static JSON/GeoJSON → MapLibre GL JS frontend. No backend.

**Status:** November 2024 General built end-to-end and verified. All 39 Berkeley
contests reconcile **exactly** against the certified District Canvass (0 discrepancy).

## Quick start

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt

./build.sh 2024-11-general       # download → parse → geo → QA → stage site

python3 -m http.server 8777 --directory site
open http://localhost:8777
```

> The map uses MapLibre GL + external CARTO basemap tiles, so it must be viewed in a
> real browser (it won't render inside sandboxed/headless preview panels).

## Pipeline

| Step | Script | Output |
|------|--------|--------|
| 0 download | `ingest/download.sh <id>` | `data/raw/<id>/{sov,district_canvass}.xlsx`, `precincts.geojson` |
| 1 parse | `ingest/parse_canvass.py` | `data/processed/results/<id>.json` |
| 2 geometry | `ingest/build_geo.py`, `ingest/build_districts.py` | `data/processed/geo/<id>.geojson`, `d1_boundary.geojson` |
| 3 QA | `ingest/qa.py` | reconciliation report (exit 1 on >0.5% mismatch) |
| 4 stage | `ingest/stage_site_data.sh` | copies processed data into `site/data/` |

`data/processed/elections.json` is the manifest (id, date, name, source URLs, file paths).

## Data model

`results/<id>.json`:
```jsonc
{
  "election_id": "2024-11-general",
  "berkeley_precincts": ["200100", ...],
  "contests": { "Mayor - Berkeley": { "rcv": true, "kind": "candidate", "choices": ["ADENA ISHII", ...] } },
  "precincts": {
    "200100": {
      "registered": 3565, "ballots_cast": 3062,      // ballots_cast = top-of-ticket turnout proxy
      "contests": {
        "Mayor - Berkeley": { "choices": {"ADENA ISHII": 704, ...}, "cast": 3031, "over": 9, "under": 294 }
      }
    }
  }
}
```

- **precinct_id** = consolidated precinct id as reported for that election. **Never**
  join results from one election onto another election's geometry — IDs are not stable.
- **RCV** contests (`rcv: true`) are **first-choice votes only**. No precinct-level
  RCV redistribution exists; the map does not fabricate one.
- **Berkeley precinct set** is self-defining: the union of precincts appearing in any
  contest whose name contains "Berkeley". Every other contest (President, props, county)
  is then kept only for those precincts.

## Frontend (`site/`)

Single-page MapLibre app. Election → contest → map-mode (winner / % for a choice /
turnout) → click a precinct for the full results table. Current D1 boundary is drawn
on every election; permalink state lives in the URL hash
(`#2024-11-general/mayor-berkeley/winner`).

## Watch-outs (carried forward for backfill)

- Precinct IDs are **not** stable across elections — geometry is per-election.
- Consolidated "no data" precincts are usually merges, not zeros — handle explicitly.
- The current D1 boundary is a reference overlay; pre-2022 precincts don't nest into it,
  so don't claim historical D1 aggregates without a crosswalk.
- Canvass **format drift** is expected going back in time — `parse_canvass.py` targets the
  current SOV layout; older years may need per-election adapters (and 2014-era may be
  PDF-only or Statewide Database CSVs).

## Sources

- Alameda County ROV — Statement of Vote & District Canvass (certified).
- Alameda County Open Data Hub — Consolidated Precincts (per election).
- City of Berkeley — Council Districts (2022 redistricting).
