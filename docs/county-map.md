# The countywide map

*Part of the [Berkeley Precinct Election Map](../README.md) documentation.*

## Countywide map

`./build_county.sh [all|<election_id>]` builds `site/county.html`'s data into
`data/processed/county/`. It reuses the same downloaders and canvass parsers; the only
difference is that the parsers are handed the **county** precinct-id list instead of the
Berkeley one, and the output is then trimmed to the big-contest whitelist.

| Step | Script | Output |
|------|--------|--------|
| cities | `ingest/fetch_city_boundaries.py` | `county/cities.geojson` (14 cities + unincorporated) |
| geo | `ingest/build_county_geo.py` | `county/geo/<id>.geojson` — every precinct, tagged with its city |
| parse | `ingest/parse_canvass.py` / `parse_sovc_csv.py` | full county results (temp) |
| filter | `ingest/filter_county_results.py` | `county/results/<id>.json` — whitelist only, plus city/county rollups |
| manifest | `ingest/build_county_manifest.py` | `county/elections.json` |

An election with no certified canvass yet takes the **preliminary** path instead — see
[Elections awaiting certification](#elections-awaiting-certification).

Which contests qualify lives in **`ingest/county_contests.py`**. Categories `statewide`,
`federal`, `proposition`, `recall` and `regional` are on; `legislative` (State Senate/Assembly),
`judicial` (appellate retention) and `county` (sheriff, DA, supervisors, county measures)
are defined but off — add one to `ENABLED` and re-run, no other code change. Across the
nine certified elections this keeps 109 contests and drops 511 local ones.

`regional` is for a measure put to the **whole county** by a district that spans it — the
Nov 2026 transit measure (Measure RTM) is on essentially every county ballot, so it maps
as meaningfully as a state proposition. It is matched by exact jurisdiction rather than by
a loose "district" rule, because most district measures cover one school or park district
and would leave the county map 95% empty. A new region-wide measure needs its own line,
deliberately: adding one should be a decision, not a side effect.

**Jurisdiction labels** come from the city contests a precinct actually votes in, with
the county's city outlines as fallback. Geometry alone is wrong on city borders: in Nov
2024, precincts 203880 / 203890 / 208690 sit ~100% inside Oakland's published outline but
vote for Mayor of Berkeley and Berkeley city measures. Only true city offices and
"City of X" measures count as evidence — city-named *school* and *special* districts
(Hayward USD, Hayward Area Recreation & Park District) reach far past city limits and
would otherwise relabel hundreds of unincorporated precincts.

## Per-contest loading

The county map draws one contest at a time but was downloading all of them: 110 KB
gzipped for Nov 2026 to render a single choropleth. `ingest/split_results.py` writes

```
split/<id>/summary.json        contests, cities, county + city rollups, turnout,
                               status, and per-precinct metadata — no tallies
split/<id>/c/<contest>.json    one contest's per-precinct tallies
split/<id>/registration.json   per-precinct party registration
```

and the frontend fetches a contest when it is picked. Registration is split off too:
it was over half the summary's weight and only the two registration modes read it.

| Nov 2026 county, gzipped | before | after |
|---|---|---|
| first paint | 110 KB | **16 KB** |
| June 2026 primary | 173 KB | **27 KB** |

Nothing is discarded — the bytes arrive when they are needed. It works because every
read in `county.html` is `precinct.contests[state.contest]`; nothing iterates a
precinct's other contests. Contest slugs match the frontend's `slug()`, so a
contest's file is predictable from its permalink.

The one trap: a split summary carries no per-precinct `contests`, and a precinct
absent from a contest's file never gets an entry, so `loadElection` seeds every
precinct with an empty `contests` object. Without it the first precinct not on that
ballot throws.

Elections without a `split/` directory still load as a single file, so the two
formats can coexist.

## `site/county.html` — countywide

Same shell, different question. Election → contest (grouped Federal / Statewide /
Propositions / Region-wide) → map-mode: **winner**, **margin** (leader over runner-up), **turnout**,
**% for a choice**, and **stands out** (precincts differing from the *countywide* share
by >3 points and beyond sampling noise). The panel opens on Alameda County — contest
totals, countywide turnout, then all 15 jurisdictions ranked by whatever the active mode
measures — and drills into one city on click, showing its subtotal and every precinct.
Permalink hash is `#<election>/<contest>/<mode>[/c-<choice>][/t-<tab>][/<city>]`.

An election still being counted shows a second panel tab, **Latest county totals**, listing
every big race's countywide numbers with the precinct-mapped ones flagged and linked back
to the map. The tab is part of the permalink (`/t-latest`), so that view is shareable too.

A statewide primary can carry 60+ candidates, so the winner legend keys only the choices
that actually lead at least one precinct (the rest lump into "Other candidates"); the
same cap was added to the Berkeley map's legend.

Each election's data is fetched on demand (≤1.4 MB results + ≤0.8 MB geometry), not all
at once. Zero-vote precinct/choice entries are dropped at build time — in a crowded
primary they are most of the payload, and the frontend reads a missing choice as 0.
