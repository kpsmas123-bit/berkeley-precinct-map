# Party registration

*Part of the [Berkeley Precinct Election Map](../README.md) documentation.*

## Party registration

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
