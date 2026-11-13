# The historical layer: zones and swing

*Part of the [Berkeley Precinct Election Map](../README.md) documentation.*

## The historical layer (zones + swing)

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
