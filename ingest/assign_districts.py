#!/usr/bin/env python3
"""
Assign each precinct in an election's results to a council district, using the
district-boundary set that was in effect for THAT election (majority-area overlap).
Writes `district` and `district_frac` onto every precinct in the results JSON, plus
a top-level `districts` summary {district -> [precinct ids]} and the map key used.

Precincts are drawn to nest within the districts of their era, so overlap is usually
~1.0. Any precinct whose largest-overlap district holds < STRADDLE of its area is
reported (it genuinely spans a district line) but still assigned by majority.

Usage:
  assign_districts.py <results.json> <precincts.geojson> <district_map.geojson> <map_key>
"""
import json
import sys

from shapely.geometry import shape

STRADDLE = 0.90


def main():
    results_path, geo_path, dmap_path, map_key = sys.argv[1:5]
    results = json.load(open(results_path))
    precs = json.load(open(geo_path))
    dmap = json.load(open(dmap_path))

    dgeom = {f["properties"]["district"]: shape(f["geometry"]).buffer(0)
             for f in dmap["features"]}

    by_district = {}
    straddlers = []
    assigned = 0
    for f in precs["features"]:
        pid = str(f["properties"]["precinct"])
        if pid not in results["precincts"]:
            continue
        g = shape(f["geometry"]).buffer(0)
        area = g.area or 1e-12
        fracs = {d: g.intersection(dg).area / area for d, dg in dgeom.items()}
        best = max(fracs, key=fracs.get)
        frac = round(fracs[best], 4)
        results["precincts"][pid]["district"] = best
        results["precincts"][pid]["district_frac"] = frac
        by_district.setdefault(best, []).append(pid)
        assigned += 1
        if fracs[best] < STRADDLE:
            top2 = sorted(fracs.items(), key=lambda x: -x[1])[:2]
            straddlers.append((pid, [(d, round(fr, 2)) for d, fr in top2]))

    results["district_map"] = map_key
    results["districts"] = {d: sorted(by_district[d], key=int_or_str)
                            for d in sorted(by_district, key=int_or_str)}
    json.dump(results, open(results_path, "w"), separators=(",", ":"))

    counts = ", ".join(f"D{d}:{len(by_district[d])}" for d in sorted(by_district, key=int_or_str))
    print(f"assigned {assigned} precincts using {map_key} -> {counts}")
    if straddlers:
        print(f"  straddlers (<{STRADDLE:.0%} in one district, assigned by majority):")
        for pid, t in straddlers:
            print(f"    {pid}: {t}")
    else:
        print("  no straddlers — precincts nest cleanly into the era map")


def int_or_str(x):
    try:
        return (0, int(x))
    except (ValueError, TypeError):
        return (1, str(x))


if __name__ == "__main__":
    main()
