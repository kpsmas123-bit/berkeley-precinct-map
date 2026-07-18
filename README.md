# Berkeley Precinct Election Map

Static web map showing **precinct-level results** for Berkeley-relevant elections
(~2014–present), with a focus on **City Council District 1**. Python ingestion →
static JSON/GeoJSON → MapLibre GL JS frontend. No backend.

**Status:** all 13 post-2014 elections built (2014–2024). Where the county
published a certified District Canvass, contests reconcile **exactly** against it;
older elections have no canvass and are spot-checked against known results.

| Election | Format | Precincts | Map | Reconciliation |
|---|---|---|---|---|
| 2024-11 General | xlsx | 32 | 2021 | 39/39 exact |
| 2024-03 Pres. Primary | xlsx | 31 | 2021 | 14 exact, 7 minor-party sub-contests flagged ⚠ |
| 2022-11 General | xlsx | 31 | 2021 | 46/46 exact (incl. D1 council) |
| 2022-06 Primary | xlsx | 28 | 2021 | 22/22 exact |
| 2021-09 Gubernatorial Recall | csv | 32 | 2013 | no canvass published |
| 2020-11 General | csv | 32 | 2013 | no canvass (spot-checked: Arreguín) |
| 2020-03 Pres. Primary | csv | 75 | 2013 | no canvass (spot-checked: Sanders>Warren) |
| 2018-11 General | csv | 106 | 2013 | no canvass; source has no turnout column |
| 2018-06 Primary | xls | 106 | 2013 | no canvass published |
| 2016-11 General | xls | 107 | 2013 | no canvass (spot-checked: Arreguín>Capitelli) |
| 2016-06 Pres. Primary | xls | 104 | 2013 | no canvass (spot-checked: Sanders>Clinton) |
| 2014-11 General | xls | 103 | 2013 | no canvass (spot-checked: Brown); borrowed 2016 geometry |
| 2014-06 Primary | xls | 93 | 2013 | no canvass; borrowed 2016 geometry |

Three canvass formats are auto-dispatched from the manifest `format` field: modern
`xlsx` SOV, legacy OLE2 `.xls` SOV (read via `xlrd`), and long-format `csv` SOVC.
Pre-2020 elections use the county's un-consolidated precincts (100+, smaller); COVID
all-mail voting consolidated Berkeley to ~30 from Nov 2020 on. 2014 has no precinct
GeoJSON published, so it borrows the 2016 (same-era) geometry (~99.7% id match; a few
no-data precincts render empty). Adding an election is a manifest entry —
`./build.sh all` (re-run any election that hits a transient download error).

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

## Sources & attribution

- **Election tallies:** Alameda County Registrar of Voters — Statement of Vote & District Canvass (public records; not copyrightable).
- **Precinct geometry:** Alameda County Open Data Hub — Consolidated Precincts (per election).
- **Council districts:** City of Berkeley — Council Districts (2013 & 2021 redistricting).
- **Basemap:** © OpenStreetMap contributors (ODbL), © CARTO — attribution shown on the map.
- **Library:** MapLibre GL JS (3-Clause BSD), self-hosted under `site/vendor/` (no third-party CDN at runtime).

## License

- **Code:** MIT (see [LICENSE](LICENSE)).
- **Derived data** (`data/processed/`, `site/data/`): CC-BY-4.0. Underlying tallies are public records.

## Privacy

The published page sets **no cookies and runs no analytics/trackers**. It stores one
local flag (`bpm_about_v1`) in the browser to avoid re-showing the intro. Map tiles are
fetched from CARTO/OpenStreetMap, which see the visitor's IP as any web request would.

## Publishing to GitHub Pages

The site is the static `site/` directory (no build step). A ready-to-use workflow is at
[`.github/workflows/pages.yml`](.github/workflows/pages.yml):

1. Create a **public** GitHub repo and push (`gh repo create <name> --public --source=. --push`).
2. Repo **Settings → Pages → Source: GitHub Actions**.
3. Push to `main` — the workflow uploads `site/` and deploys. (Private repos need a paid plan for Pages.)

Alternatively, rename `site/` → `docs/` and use the classic "deploy from /docs" option.
