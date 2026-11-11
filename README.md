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
  `./build_county.sh`, 2020 onward. See [Countywide map](#countywide-map).

**Status:** all 15 post-2014 elections with a published canvass are built
(2014–June 2026). Where the county published a certified District Canvass, contests
reconcile **exactly** against it; older elections have no canvass and are
spot-checked against known results. **November 2026 is citywide-only** until the
county publishes its precinct canvass at certification — see
[Elections awaiting certification](#elections-awaiting-certification).

| Election | Format | Precincts | Map | Reconciliation |
|---|---|---|---|---|
| 2026-11 General | — | 31 (geometry only) | 2021 | **pending certification** — citywide totals only |
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
`contests` map. See [Elections awaiting certification](#elections-awaiting-certification).

### Countywide map

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

### Elections awaiting certification

Alameda County publishes the precinct-level Statement of Vote only at or near
certification, roughly 30 days after election day. Until then the county publishes **two**
machine-readable feeds, and they carry different things:

`ingest/live_map_feed.py` holds the parse for the second feed; both builds import it, so
there is one parser rather than two that can drift apart. Run it directly to see what the
county is currently mapping.

| Source | What it has | What it is missing |
|--------|-------------|--------------------|
| the **Cast Vote Record**, on request from the Registrar | one anonymised record per ballot: the precinct, and every contest on that ballot | nothing that matters here, except registration — and the choices on ballots redacted under state law |
| `alamedacountyca.gov/rovresults/<id>/` — the results portal | every contest on the ballot, countywide totals, the "Preliminary/Unofficial — Update #N / Last Updated" stamp, registration and turnout | any geography at all |
| `electionmaps.alamedacountyca.gov/json/electionResults.json` — the feed behind the county's own results map | **per-precinct votes**, and each precinct's reporting status | all but the one or two contests the county chooses to map (Nov 2026: CD-14 and Measure RTM) |

**The Berkeley map** (`index.html`) uses whichever source exists.
`ingest/build_pending_results.py` keeps the precinct rows for any contest on Berkeley's
ballot and writes `precinct_results: "partial"`; those contests then behave exactly like
certified ones, council-district rollups included.

The difference a CVR makes here is the whole point. The county's results map does not
carry CD-12, so without one Berkeley could not see its own member of Congress on its own
map: Nov 2026 had exactly **one** mapped contest, the countywide transit measure (Berkeley
**85.6% Yes** against 66.8% countywide). With the CVR it has **54** — the entire ballot,
CD-12 included, where Lateefah Simon ranges from 72.4% to 90.5% across the 31 precincts.
Drop the export at `data/raw/<eid>/cvr/export.zip` or set `CVR_EXPORT`, then
`./build.sh <eid>`.

Without a CVR, every contest the results map does not cover stays citywide-only in a
second panel tab, **Latest Berkeley totals**; only contests whose jurisdiction *is*
Berkeley are kept there, because the portal reports county and state contests countywide
and a countywide number on a Berkeley map would be false. With a CVR that tab becomes a
cross-check against the county's own published figures rather than the only source.

With nothing mapped the file keeps `precinct_results: false` and the old behaviour: the
choropleth is deliberately blank rather than guessing, and the controls are locked.

**The Cast Vote Record is the one that actually solves this.** The portal tells you
Lateefah Simon won CD-12 with 80.6% and nothing about where; the results map covers two
races chosen by the county. The CVR covers all of them, precinct by precinct, a month
before certification. The Registrar releases it on request through a short Airtable form
linked from the results portal — name, organisation, email — and sends back a Dominion
Democracy Suite export. `ingest/parse_cvr.py` turns it into the same shape the canvass
parsers emit, so `filter_county_results.py` and everything downstream consume it
unchanged. Drop the export at `data/raw/<eid>/cvr/export.zip` (gitignored; a symlink is
fine) or point `CVR_EXPORT` at it, and `./build_county.sh <eid>` picks it up
automatically, falling back to the live feeds when there is none.

Alameda's Nov 2026 export is 234 MB zipped, 6.3 GB of JSON across 2,888 files, and
parses to all 28 big contests across 473 precincts, reconciling to within **0.17%** of
the portal's published countywide totals — CD-12 to within 8 votes in 250,000. See
[Reading a Cast Vote Record](#reading-a-cast-vote-record) for the traps.

**The countywide map** (`county.html`) uses whichever source is available, via
`ingest/fetch_live_county.py`, which writes a results file in exactly the shape a
certified build produces so every existing map mode just works:

* the contests with precinct figures — all of them from a CVR, one or two from the
  results-map feed — get real geometry and the full mode set;
* every other big race is carried in `county_only` as countywide totals, shown in a
  **Latest county totals** tab alongside the mapped ones;
* `preliminary: true` and the county's status banner are explicit in the file, so the
  numbers cannot be shown unlabelled;
* per-precinct registration does not exist in either feed, so it is written as 0 and the
  turnout mode disables itself on both maps. Countywide registration and turnout *do* exist
  and are recorded as such;
* precinct sums are reconciled against the best countywide totals available — the
  feed's own (which must match exactly) or, for a CVR, the portal's (a snapshot taken
  minutes apart, so the gap is reported per contest in `status.reconciliation`).

Jurisdiction labels are the one thing a preliminary build cannot derive, since it has no
local contests to learn from. `ingest/build_city_overrides.py` persists the
precinct → city corrections learned from *certified* builds and the preliminary build
applies them by precinct id (485 of the 627 Nov-2026 ids also existed in Nov 2024). Only
disagreements are stored, never the whole table, so a reused id cannot drag a stale answer
onto a redrawn precinct. Without this Berkeley would show 28 precincts instead of 31.

Re-run either build any time to refresh — both are cheap and hit only the live feeds:

```bash
./build.sh 2026-11-general          # Berkeley: citywide totals
./build_county.sh 2026-11-general   # county: precinct-level where it exists + all totals
```

**To finish the election once the county certifies** (~30 days after election day):

```bash
.venv/bin/python ingest/discover_sources.py 2026-11-general   # finds the canvass URLs
./build.sh 2026-11-general && ./build_county.sh 2026-11-general
git add -A && git commit -m "Nov 2026 precinct results" && git push origin main
```

`discover_sources.py` reads the county's election page, finds the precinct and district
canvass links, writes them into the manifest and clears the `precinct_results: false`
flag. It is safe to run early — if the canvass is not up yet it says so and changes
nothing. It exists because the county does not keep one URL convention: Nov 2024
published to `SOV/<date>/Statement of Vote - General Election.xlsx` and June 2026 to
`PDFs/<date>/Results/PrecinctCanvassJun02.xlsx`.

The precinct geometry is already downloaded and mapped, so the map fills in with no
frontend change — and the election joins the countywide map at the same time.

### Reading a Cast Vote Record

`ingest/parse_cvr.py` reads a Dominion Democracy Suite export, directory or zip.
`tests/test_parse_cvr.py` builds a synthetic export and asserts the behaviour below;
run it after any change.

The vendor publishes a format document — San Francisco mirrors it, along with a real
export, which is how this was written before Alameda's arrived. **Two things in it are
wrong for 5.19, and both fail silently:**

- The spec says the ballot element lists its contests as `Contests`. In 5.19 they are
  nested one level deeper under `Cards`, because a ballot can be several physical cards.
  Read the documented shape and every precinct comes out empty.
- A Session is one **card**, not one ballot. Alameda's export has 1,824,509 sessions for
  562,851 ballots — count sessions as ballots and turnout is 3.2x too high. Per-contest
  tallies are unaffected, since a contest lives on exactly one card, so `ballots_cast` is
  taken as the busiest contest's card count, the same top-of-ticket proxy
  `parse_canvass.py` uses.

The rest of the traps:

- **Redaction is in-band.** State law (2 CCR 20126) requires a published CVR to have the
  choices removed from any ballot traceable to an individual voter. Alameda does it in
  place: `Marks`, `Undervotes` and `Overvotes` become the string `"*** REDACTED ***"`.
  Iterating that as a list crashes; treating it as empty invents undervotes. It is
  counted as a card the contest appeared on, with choices unknown. In Nov 2026 that is
  8,171 contest-cards across 42 precincts — and in all 42, *every* ballot, so those
  precincts carry no usable result and the map shows them blank rather than zero.
- **Youth Voting ballots are in the export.** Counting groups 3 and 4 are ballots cast by
  minors in the county's youth programme; the Registrar reports them in a separate
  turnout block and they are not part of any result. They are excluded by default
  (`--counting-groups` overrides).
- **Adjudicated ballots carry two states.** Use the element flagged `IsCurrent`, which is
  `Modified` where an adjudicator changed something — 17 of the first 732 ballots.
- **A mark is not a vote.** Only `IsVote` counts: ambiguous marks, marks on an overvoted
  contest and unresolved write-ins are all present and must not be tallied. For ranked
  contests only `Rank: 1` is counted by default (`--rcv-all-ranks` to change), which
  matches how this project reports RCV elsewhere. The full ranking is in the file, so a
  real round-by-round count is possible later without re-requesting anything.
- **Ranked contests are named differently.** The CVR calls it `Auditor - Berkeley
  (RCV)`; the portal, the results map and the certified Statement of Vote all call it
  `Auditor - Berkeley` and carry the ranking separately. Left alone the same race appears
  twice under two names, and every ranked contest is silently renamed the day the
  certified canvass replaces the file. The suffix is stripped and the flag kept.
- **The precinct join differs by county.** A CVR names a *precinct portion*. The vendor
  doc points at `ExternalId`, which in Alameda is a meaningless sequence number
  (`"0001"`) while the portion's `Description` is the six-digit precinct id. Candidates
  are tried in order and, with `--precinct-ids`, the first that matches a real precinct
  wins; a join matching nothing exits non-zero rather than writing a plausible-looking
  file. `--portion-map` forces it.
- **The `.sha` file beside the export is a 128-byte RSA signature, not a checksum**, so
  it cannot be verified without the county's public key.

### Moving between the two maps

A Berkeley reader looking at a countywide race — Congress, Governor, a proposition —
usually wants to know how Berkeley compares with everywhere else, and that answer is on
the other map. So when the selected contest is not Berkeley-specific, the Berkeley map's
corner link becomes **"This race countywide →"** and carries the election, contest, mode
and chosen candidate across, instead of dropping the reader on the county map's default
view to find the race again. Berkeley-only contests keep the plain "County map" link,
since the county map does not carry them.

### Party registration

Nothing the county publishes with results carries party. The Statement of Vote, the
live results feed and the Cast Vote Record all give one undifferentiated "registered
voters" count — the CVR does not even give that. So the question worth asking was out
of reach: not "where did this candidate do well" (mostly a map of where Democrats
live) but **"where did this candidate run ahead of or behind what the precinct's
registration predicts"**.

`ingest/fetch_registration.py` closes that, from two public sources:

| Source | What it gives |
|---|---|
| [California Statewide Database](https://statewidedatabase.org/) (UC Berkeley) | registration by party per precinct — `totreg_r, dem, rep, aip, paf, msc, lib, nlp, grn, ref, dcl`. The only source below county level: the SoS Report of Registration stops at county and district, and the county's own eData is countywide. |
| the county's results-map feed | `homePrecincts` — which registration precincts were consolidated into each voting precinct, published per election |

**The join is exact, not geometric.** SWDB's `rgprec` is the county's 6-digit
registration precinct id plus a 2-digit split suffix (`20010000` → `200100` + `00`),
so stripping the suffix gives a home precinct and `homePrecincts` gives the voting
precinct it rolls into. Nothing is apportioned by area.

Coverage runs **99–100% of registered voters** on every election from 2016 on, even
though only ~85% of precincts join — the ones that fail to join are the tiny ones, so
`attach_registration.py` reports coverage by voters as well as by precinct count.
Snapshots exist for every election back to 2014 (`P14`…`P26`, plus `S21`/`S25` for
the odd-year specials); where one does not exist yet — `G26` at the time of writing —
the nearest earlier snapshot is used and both the data and the UI say so.

Run order is `fetch_registration.py <id>` then `attach_registration.py <results>
<registration>`; both builds do this automatically after the tallies. It is kept out
of the parsers because registration is a different publisher on a different schedule,
and a results file is perfectly usable without it.

**On the county map** this adds two modes:

* **Party reg** — a chosen party's share of each precinct's registered voters. Each
  party gets its own top-of-scale, or Libertarians at 3% and Democrats at 90% would
  be the same colour.
* **vs registration** — the one worth having. It fits a least-squares line of the
  selected choice's precinct share on that precinct's Democratic-minus-Republican
  registration margin, then colours the **residual**. The legend reports the fit's
  R². A precinct is only coloured if the gap clears 3 points *and* its own sampling
  noise, the same two gates "stands out" uses.

  Worth a look: Harris 2024 ran *ahead* of registration most in Piedmont (+6.4),
  Pleasanton (+4.2) and Livermore (+3.6) — the most Republican-registered parts of
  the county — which the plain share map cannot show you.

**On the Berkeley map** registration is shown as numbers (citywide, per council
district, per precinct) and not as a map: Berkeley is ~74% Democratic and ~3%
Republican, so a registration choropleth there is one flat colour.

**Watch the inference.** These are precinct-level associations. A precinct registered
70% Democratic voting 70% for a Democrat says nothing about which individuals did
what — the ecological fallacy — and the about box says so on both maps.

### Per-contest loading

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

### The historical layer (zones + swing)

Precinct lines are redrawn every election, so nothing compares across years as
published. Two cross-election passes fix that, and they run inside `build.sh`'s
existing one — alongside `build_measures.py` and `build_featured.py` — rather than
needing a build command of their own:

| Step | Script | Output |
|------|--------|--------|
| crosswalk | `ingest/build_crosswalk.py` | `crosswalk.json` — every election apportioned onto the current lines by area overlap, with `nested` / `exactness` quality per precinct and per district |
| indicators | `ingest/build_history.py` | `history.json` — three indicators per election, per city / district / precinct |

The indicators are deliberately few, because only a few things are measured the same
way in every election: **turnout**, **Democratic share of the two-party vote** at the
top of the ticket (President in presidential years, Governor otherwise — the pair is
named per election in the build script), and **pooled YES on Berkeley measures**.

`site/index.html` renders both halves in one **Swing** mode: the map shades each
precinct by the change between two elections, and the panel carries the full series
per council district as a sparkline, drilling into a year-by-year table. The
permalink carries the indicator and the comparison election (`/swing/i-major_dem/
v-2016-11-general`), and `history.json` is fetched only when the mode is opened.

**Quality is on screen, not buried.** The 2020-11, 2021-09 and 2022-06 lines only
reach ~0.56–0.58 district exactness against today's, so those years are flagged in
the legend and per district. The rule of thumb the data supports: district figures
are reliable because errors cancel within a district, precinct shading is not, for
those years.

Watch out for the key scopes — districts are `"1"`–`"8"` and precincts are six
digits, so nothing can infer which is meant from the key itself; `histValue()` takes
an explicit scope for that reason.

### Shareable links

Both maps keep their full state in the URL hash, so any view can be linked:

```
site/index.html#<election>/<contest>/<mode>[/<choice>][/b-<baseline>][/d<district>]
site/county.html#<election>/<contest>/<mode>[/c-<choice>][/<city>]
```

Embedded on samkp.com the same views are reachable as
`samkp.com/precinct-map.html#<berkeley hash>` and
`samkp.com/precinct-map.html#county/<county hash>`; the embedded map posts its hash to
the parent page, which keeps the address bar in step and answers the map's "copy link"
button with the samkp.com URL. Only that origin is trusted, and only the hash is sent.

**Candidate slugs are written without the party prefix** (`c-lateefah-simon`, not
`c-dem-lateefah-simon`) and read tolerantly, because the county prefixes choices with
the party in some elections and not others — she is `DEM - LATEEFAH SIMON` in the Nov
2024 canvass and plain `Lateefah Simon` in the Nov 2026 results. Without this a link
shared in one cycle would break in the next.

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

### `site/county.html` — countywide

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
