#!/usr/bin/env python3
"""
Build the precinct CROSSWALK: for every election, the area-overlap weights that map
that election's precincts onto a single fixed base geography (the most recent
precinct set).

Why
---
Precinct ids are not stable across elections and Berkeley redistricted in 2021, so
the repo has never been able to answer "how did District 1 *as drawn today* vote in
2014?" — PLAN.md and the README both flag it as the missing piece. This supplies the
one thing that was missing: a defensible mapping from any election's precincts onto
today's lines.

Method
------
For each source precinct `s` and base precinct `b`, weight w(s,b) is the share of
`s`'s AREA that falls inside `b`. Counts are then apportioned num_b = Σ_s num_s·w(s,b).

The assumption is explicit and it is the usual one: **voters are distributed evenly
within a source precinct.** That is safe when a source precinct nests inside one base
precinct (w = 1, no assumption used at all) and weakest when a large old precinct
straddles several base precincts.

So every weight carries a quality signal:
  * `nested`   — share of the source's area in its single best base precinct.
                 1.0 means the apportionment is exact, not an estimate.
  * per-base `exactness` — the share of a base precinct's inbound weight that came
                 from sources that nested cleanly (nested >= NEST_OK).

Pre-2020 Berkeley had 100+ small precincts and today has ~31 larger ones, so most of
the history is many-small-into-one-large: aggregation, which is reliable. The lossy
direction (one large source split across several base units) is rare and is exactly
what `exactness` surfaces.

Usage:
  build_crosswalk.py [base_election_id]      # default: newest election in manifest
"""
import json
import os
import sys

from shapely.geometry import shape
from shapely.strtree import STRtree

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PROC = os.path.join(ROOT, "data", "processed")
OUT = os.path.join(PROC, "crosswalk.json")

NEST_OK = 0.95      # a source is "clean" if this much of it lands in one base unit
MIN_W = 0.005       # drop slivers below half a percent


def load(path):
    return json.load(open(path))


def main():
    manifest = load(os.path.join(PROC, "elections.json"))
    elections = sorted(manifest["elections"], key=lambda e: e["date"], reverse=True)
    base_id = sys.argv[1] if len(sys.argv) > 1 else elections[0]["id"]
    base_meta = next(e for e in elections if e["id"] == base_id)

    base_geo = load(os.path.join(PROC, base_meta["geo"]))
    base_ids, base_shapes = [], []
    for f in base_geo["features"]:
        base_ids.append(str(f["properties"]["precinct"]))
        base_shapes.append(shape(f["geometry"]).buffer(0))
    tree = STRtree(base_shapes)
    base_area = {pid: g.area for pid, g in zip(base_ids, base_shapes)}

    # each base precinct's council district, from the base election's results
    base_res = load(os.path.join(PROC, base_meta["results"]))
    base_district = {pid: p.get("district")
                     for pid, p in base_res.get("precincts", {}).items()}
    districts = {}
    for pid, d in base_district.items():
        if d is not None:
            districts.setdefault(str(d), []).append(pid)
    districts = {d: sorted(v) for d, v in sorted(districts.items(),
                                                 key=lambda kv: (len(kv[0]), kv[0]))}

    out = {
        "base_election": base_id,
        "base_district_map": base_meta.get("district_map"),
        "base_precincts": base_ids,
        "districts": districts,
        "method": ("Area-overlap apportionment onto the base election's precincts. "
                   "w(source,base) = share of the SOURCE precinct's area inside the "
                   "base precinct; counts are apportioned num_base = sum(num_source * w). "
                   "Assumes voters are spread evenly within a source precinct — exact "
                   "where a source nests in one base unit (nested = 1.0), an estimate "
                   "where it straddles. 'exactness' reports the share of a base unit's "
                   "inbound weight that came from cleanly nested sources."),
        "nest_threshold": NEST_OK,
        "elections": {},
    }

    for e in elections:
        geo_path = os.path.join(PROC, e["geo"])
        if not os.path.exists(geo_path):
            continue
        src = load(geo_path)
        weights, nested_of = {}, {}
        dweights, dnested_of = {}, {}
        clean_w = {pid: 0.0 for pid in base_ids}
        total_w = {pid: 0.0 for pid in base_ids}
        dclean_w, dtotal_w = {d: 0.0 for d in districts}, {d: 0.0 for d in districts}

        for f in src["features"]:
            spid = str(f["properties"]["precinct"])
            g = shape(f["geometry"]).buffer(0)
            a = g.area
            if not a:
                continue
            row = []
            for idx in tree.query(g):
                i = int(idx)
                inter = g.intersection(base_shapes[i]).area
                if inter <= 0:
                    continue
                w = inter / a
                if w >= MIN_W:
                    row.append([base_ids[i], round(w, 5)])
            if not row:
                continue
            row.sort(key=lambda r: -r[1])
            nested = row[0][1]
            nested_of[spid] = nested
            weights[spid] = row
            for bpid, w in row:
                total_w[bpid] += w
                if nested >= NEST_OK:
                    clean_w[bpid] += w

            # Same apportionment rolled up to council districts. A source that
            # straddles two precincts of the SAME district is exact at district
            # level even though it is an estimate at precinct level — which is why
            # the district trend lines are far more reliable than the precinct map.
            drow = {}
            for bpid, w in row:
                d = base_district.get(bpid)
                if d is None:
                    continue
                drow[str(d)] = drow.get(str(d), 0.0) + w
            if drow:
                drow = sorted(drow.items(), key=lambda kv: -kv[1])
                dnested = drow[0][1]
                dnested_of[spid] = dnested
                dweights[spid] = [[d, round(w, 5)] for d, w in drow]
                for d, w in drow:
                    dtotal_w[d] += w
                    if dnested >= NEST_OK:
                        dclean_w[d] += w

        exactness = {pid: round(clean_w[pid] / total_w[pid], 4)
                     for pid in base_ids if total_w[pid] > 0}
        dexactness = {d: round(dclean_w[d] / dtotal_w[d], 4)
                      for d in districts if dtotal_w[d] > 0}
        n_clean = sum(1 for v in nested_of.values() if v >= NEST_OK)
        n_dclean = sum(1 for v in dnested_of.values() if v >= NEST_OK)
        me = round(sum(exactness.values()) / len(exactness), 4) if exactness else None
        mde = round(sum(dexactness.values()) / len(dexactness), 4) if dexactness else None
        out["elections"][e["id"]] = {
            "weights": weights,
            "nested": {k: round(v, 4) for k, v in nested_of.items()},
            "exactness": exactness,
            "district_weights": dweights,
            "district_exactness": dexactness,
            "n_sources": len(weights),
            "n_clean": n_clean,
            "n_clean_district": n_dclean,
            "mean_exactness": me,
            "mean_district_exactness": mde,
        }
        pct = 100.0 * n_clean / len(weights) if weights else 0
        dpct = 100.0 * n_dclean / len(weights) if weights else 0
        print(f"  {e['id']:<18} {len(weights):>4} src -> {len(base_ids):>2} base "
              f"| precinct: {pct:3.0f}% nest, exactness {me} "
              f"| district: {dpct:3.0f}% nest, exactness {mde}")

    json.dump(out, open(OUT, "w"), separators=(",", ":"))
    kb = os.path.getsize(OUT) / 1024
    print(f"crosswalk: base={base_id} ({len(base_ids)} precincts, "
          f"{len(districts)} districts) -> {OUT} ({kb:.0f} KB)")


if __name__ == "__main__":
    main()
