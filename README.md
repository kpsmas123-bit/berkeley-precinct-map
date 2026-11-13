# Berkeley Precinct Election Map

Two static web maps over the same pipeline. Python ingestion → static JSON/GeoJSON
→ MapLibre GL JS frontend. No backend.

- **`site/index.html` — Berkeley.** Precinct-level results for Berkeley-relevant
  elections (2014–present), citywide across all council districts, every contest on
  a Berkeley ballot including the local ones.
- **`site/county.html` — Alameda County.** Every precinct in the county, but only
  the big shared-ballot contests: statewide constitutional offices, U.S.
  President / Senate / House, state propositions and the 2021 recall. Local races
  are deliberately excluded — countywide they are a mostly-empty map. Built by
  `./build_county.sh`, 2024 onward. See [docs/county-map.md](docs/county-map.md).

**Status:** every election from 2014 on is built. Where the county published a
certified District Canvass the contests reconcile **exactly** against it; older
elections have no canvass and are spot-checked. **November 2026 is mapped from the
county's Cast Vote Record** — real precinct figures a month before certification,
and superseded by the Statement of Vote when it lands. See
[docs/pre-certification.md](docs/pre-certification.md).

| Election | Format | Precincts | Map | Reconciliation |
|---|---|---|---|---|
| 2026-11 General | CVR | 31 | 2021 | **preliminary** — cast vote record, within 0.17% of the portal |
| 2026-06 Primary | xlsx | 31 | 2021 | 16/16 exact |
| 2025-11 Statewide Special (Prop 50) | xlsx | 32 | 2021 | 1/1 exact |
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
`xlsx` SOV, legacy OLE2 `.xls` SOV (read via `xlrd`), and long-format `csv` SOVC. The
county also moves the files: the June 2026 canvass sits under
`PDFs/<date>/Results/PrecinctCanvassJun02.xlsx`, not the older `SOV/<date>/` path —
which is why every source URL is recorded per election in the manifest rather than
derived from a pattern.
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
| 7 stage | `ingest/stage_site_data.sh` | copies processed data into `site/data/` (incl. `site/data/county/`) |

For an election whose canvass is not published yet (`"precinct_results": false` in the
manifest), `build.sh` takes a shorter path: geometry and district assignment as usual,
then `ingest/fetch_live_results.py` for the county's running citywide totals and
`ingest/build_pending_results.py` to emit a results file with an empty per-precinct
`contests` map. See [docs/pre-certification.md](docs/pre-certification.md).

### Further reading

| Topic | |
|---|---|
| Mapping an election before it is certified — the three sources, the CVR, redaction | [docs/pre-certification.md](docs/pre-certification.md) |
| The countywide map, its contest whitelist and per-contest loading | [docs/county-map.md](docs/county-map.md) |
| Party registration: where it comes from and how it joins | [docs/party-registration.md](docs/party-registration.md) |
| The historical layer: zones, swing and crosswalk quality | [docs/history.md](docs/history.md) |
| Permalinks and the samkp.com embed bridge | [docs/links.md](docs/links.md) |

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

## Working on this

The pipeline grew from 11 scripts to 21 in a few sittings, and most of the mess that
had to be cleaned up afterwards came from the same reflex: writing a new thing is
cheaper than finding the existing one. Two rules, both learned the hard way here:

**Reuse or delete.** A new build step either reuses a script or removes one. If a
format replaces another, the old one goes in the same commit — `site/data/county/`
shipped 4.1 MB of superseded single-file results for days because the split format
was added and nothing was taken away.

**One copy, or it will drift.** `shared.css` / `shared.js` for the two maps,
`portal.py` for the two scrapers, `live_map_feed.py` for the two live builds. Both
times code was duplicated instead, a fix landed in one copy only: the portal's
missing "End Race" marker had to be patched twice, and the phone layout was ported
between the maps without a CSS variable it depended on, which silently dropped the
whole sheet transform.

## Watch-outs (carried forward for backfill)

- Precinct IDs are **not** stable across elections — geometry is per-election.
- Consolidated "no data" precincts are usually merges, not zeros — handle explicitly.
- The current D1 boundary is a reference overlay; pre-2022 precincts don't nest into it,
  so don't claim historical D1 aggregates without a crosswalk.
- Canvass **format drift** is expected going back in time — `parse_canvass.py` targets the
  current SOV layout; older years may need per-election adapters (and 2014-era may be
  PDF-only or Statewide Database CSVs).
- Format drift runs **forwards** too. The Nov 2025 SOV added a per-contest **"Total Votes"**
  column; parsed as a choice it double-counted the contest and made votes-per-ballot look
  like a vote-for-N race. `parse_canvass.AGGREGATE_COLS` now filters those columns, and
  `qa.py` applies the same filter — note that QA passed while the bug was live, because
  the District Canvass carries the same column and both sides double-counted equally.
  **A clean reconciliation only proves the two sides agree, not that the parse is right.**
- The results portal emits **no "End Race" marker**, so splitting on `<!-- Start Race: -->`
  gives the last race in a section everything that follows it. In Nov 2026 that made
  "State Superintendent" swallow the entire propositions table and report Prop 3's figure
  as a candidate with 4.2M votes. Both scrapers now cut each body at its "Back to Top"
  link.
- A CVR gives **no registration figures at all**, so turnout cannot be computed from
  one; the countywide figure shown comes from the portal.
- **State propositions are not emitted as races at all.** They live in one wide table
  (`id="panelDtlProps"`, Title | YES votes | YES % | NO votes | NO %) and need their own
  parse — miss it and the county map silently loses every proposition.
- Precincts are **reconsolidated every election**, so a precinct mapping from the wrong
  election is worse than none: it joins data onto precincts that did not exist. The
  county's feed archive starts in 2016, and an early version of
  `fetch_registration.py` fell back to the *current* election's feed when it found no
  match — which "joined" 25 of 2014's 103 precincts and looked like a coverage
  problem rather than a correctness one. It now skips instead.

## Sources & attribution

- **Election tallies:** Alameda County Registrar of Voters — Statement of Vote & District Canvass (public records; not copyrightable).
- **Precinct geometry:** Alameda County Open Data Hub — Consolidated Precincts (per election).
- **Council districts:** City of Berkeley — Council Districts (2013 & 2021 redistricting).
- **City boundaries:** Alameda County Open Data Hub — City_Boundaries (countywide map).
- **Live/uncertified totals:** Alameda County ROV results portal (`alamedacountyca.gov/rovresults/<id>/`),
  used only for an election whose precinct canvass is not published yet, and always labelled as preliminary.
- **Basemap:** Esri World Light Gray Canvas — Esri, HERE, Garmin, © OpenStreetMap contributors;
  attribution shown on the map. (Previously CARTO: `basemaps.cartocdn.com` now requires an API
  key and serves a watermarked placeholder tile without one.)
- **Library:** MapLibre GL JS (3-Clause BSD), self-hosted under `site/vendor/` (no third-party CDN at runtime).

## License

- **Code:** MIT (see [LICENSE](LICENSE)).
- **Derived data** (`data/processed/`, `site/data/`): CC-BY-4.0. Underlying tallies are public records.

## Privacy

The published pages set **no cookies and run no analytics/trackers**. They store one
local flag each (`bpm_about_v1` on the Berkeley map, `acpm_about_v1` on the county map)
to avoid re-showing the intro. Map tiles are fetched from Esri's ArcGIS tile service,
which sees the visitor's IP as any web request would.

## Publishing to GitHub Pages

The site is the static `site/` directory (no build step). A ready-to-use workflow is at
[`.github/workflows/pages.yml`](.github/workflows/pages.yml):

1. Create a **public** GitHub repo and push (`gh repo create <name> --public --source=. --push`).
2. Repo **Settings → Pages → Source: GitHub Actions**.
3. Push to `main` — the workflow uploads `site/` and deploys. (Private repos need a paid plan for Pages.)

Alternatively, rename `site/` → `docs/` and use the classic "deploy from /docs" option.
