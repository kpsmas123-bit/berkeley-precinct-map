#!/usr/bin/env python3
"""
Persist the ballot-derived precinct -> city corrections learned from CERTIFIED county
builds, so a PRELIMINARY build can reuse them.

Why this exists
---------------
filter_county_results.py works out a precinct's jurisdiction from the city contests
its voters actually voted in, which beats pure geometry on city borders: a handful of
precincts sit inside a neighbour's published outline while voting on the other city's
ballot (e.g. 203880/203890/208690 are ~100% inside Oakland's polygon but vote for
Mayor of Berkeley).

A preliminary build has no local contests to learn from — the county's live feed
carries only the one or two big races it maps — so geometry would relabel those
precincts and Berkeley would lose three precincts on the map. Precinct ids are stable
enough between adjacent cycles (485 of the 627 Nov-2026 ids also existed in Nov 2024)
that carrying the corrections forward by id is sound.

Only DISAGREEMENTS are stored, never the whole table: where geometry and the ballot
already agree there is nothing to correct, and a full table would let a reused id
drag a stale answer onto a redrawn precinct. Newest election wins.

Usage: build_city_overrides.py   (reads data/processed/county/{results,geo})
"""
import json
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PROC = os.path.join(ROOT, "data", "processed")
CDIR = os.path.join(PROC, "county")
# Not under county/: that tree is a regenerable build intermediate and is ignored,
# but this file is knowledge learned from builds that may no longer exist on disk.
OUT = os.path.join(PROC, "city_overrides.json")


def main():
    rdir, gdir = os.path.join(CDIR, "results"), os.path.join(CDIR, "geo")
    if not os.path.isdir(rdir):
        print("  city overrides: no certified county builds yet, nothing to learn")
        return

    overrides, provenance = {}, {}
    # oldest first, so a newer election's answer wins on a reused id
    for fn in sorted(os.listdir(rdir)):
        if not fn.endswith(".json"):
            continue
        eid = fn[:-5]
        gpath = os.path.join(gdir, f"{eid}.geojson")
        if not os.path.exists(gpath):
            continue
        res = json.load(open(os.path.join(rdir, fn)))
        if res.get("preliminary"):
            continue          # never learn from a preliminary build
        geo = json.load(open(gpath))
        gcity = {str(f["properties"]["precinct"]): f["properties"].get("city")
                 for f in geo["features"]}
        for pid, p in res.get("precincts", {}).items():
            ballot, outline = p.get("city"), gcity.get(pid)
            if ballot and outline and ballot != outline:
                overrides[pid] = ballot
                provenance[pid] = {"city": ballot, "outline": outline, "learned_from": eid}

    # Merge, do not rewrite. A correction learned from an election is still true
    # after that election's build is dropped — pruning the county map to 2024+
    # silently cost two Hayward precincts their labels, because the 2022 build that
    # taught them was no longer on disk to teach them again.
    if os.path.exists(OUT):
        prev = json.load(open(OUT))
        for pid, city in prev.get("overrides", {}).items():
            overrides.setdefault(pid, city)
            provenance.setdefault(pid, prev.get("provenance", {}).get(pid, {
                "city": city, "outline": "?", "learned_from": "earlier build"}))

    json.dump({"note": ("precinct -> city corrections learned from certified builds, "
                        "where the city contests a precinct votes in disagree with the "
                        "city outline it sits inside; applied by preliminary builds only"),
               "overrides": overrides,
               "provenance": provenance},
              open(OUT, "w"), indent=2, sort_keys=True)

    print(f"  city overrides: {len(overrides)} ballot-derived corrections -> {OUT}")
    for pid in sorted(overrides)[:8]:
        v = provenance[pid]
        print(f"    {pid}: outline {v['outline']} -> ballot {v['city']}  ({v['learned_from']})")
    if len(overrides) > 8:
        print(f"    … and {len(overrides) - 8} more")


if __name__ == "__main__":
    main()
