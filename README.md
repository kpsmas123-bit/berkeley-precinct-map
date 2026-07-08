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
| 1 district maps | `ingest/fetch_district_maps.py` | `data/district_maps/berkeley-council-{2021,2013}.geojson` |
| 2 parse | `ingest/parse_canvass.py` | `data/processed/results/<id>.json` |
| 3 geometry | `ingest/build_geo.py` | `data/processed/geo/<id>.geojson` |
| 4 assign districts | `ingest/assign_districts.py` | adds `district`/`districts` to results (per-election era map) |
| 5 district overlay | `ingest/build_districts.py` | `data/processed/geo/<id>.districts.geojson` |
| 6 QA | `ingest/qa.py` | reconciliation report (exit 1 on >0.5% mismatch) |
| 7 stage | `ingest/stage_site_data.sh` | copies processed data into `site/data/` |

`data/processed/elections.json` is the manifest (id, date, name, source URLs, file paths).

## Data model

`results/<id>.json`:
```jsonc
{
  "election_id": "2024-11-general",
  "berkeley_precincts": ["200100", ...],
  "contests": { "Mayor - Berkeley": { "rcv": true, "kind": "candidate", "choices": ["ADENA ISHII", ...] } },
  "district_map": "berkeley-council-2021",             // which era's council lines this election uses
  "districts": { "1": ["207200","209310","209700"], ... },  // precincts grouped by council district
  "precincts": {
    "200100": {
      "registered": 3565, "ballots_cast": 3062,      // ballots_cast = top-of-ticket turnout proxy
      "district": "6", "district_frac": 0.999,        // assigned by majority-area overlap vs the era map
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
turnout). The right panel shows **one council district at a time, grouped**: a header
(district + member + boundary vintage), a district **subtotal** for the selected
contest, then each precinct's results. It **defaults to District 1** (the focus).
Clicking any precinct **switches** the panel to that precinct's district and highlights
it. Era-correct district lines are drawn per election (a pre-2021 election shows the
2013 map). Permalink state lives in the URL hash
(`#2024-11-general/mayor-berkeley/winner/d1`).

Per-election **district maps** live in `data/district_maps/`; each election in
`elections.json` names the one in effect (`district_map`). `assign_districts.py` then
buckets that election's precincts into districts by majority-area overlap. Because
Berkeley redistricts each decade, "District 1" is drawn honestly per era and is **not
comparable across redistricting cycles** — the panel labels the vintage to make that clear.

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
