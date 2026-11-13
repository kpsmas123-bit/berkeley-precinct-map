# Mapping an election before it is certified

*Part of the [Berkeley Precinct Election Map](../README.md) documentation.*

## Elections awaiting certification

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

## Reading a Cast Vote Record

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
