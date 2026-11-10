#!/usr/bin/env python3
"""
Build the COUNTYWIDE precinct layer for one election: every Alameda County precinct
(no city filter), simplified for county-scale zoom, each tagged with the city it
sits in so the map can group and label by jurisdiction.

Differences from build_geo.py (the Berkeley one):
  * keeps all precincts instead of clipping to one city,
  * simplifies harder, since the whole county is on screen rather than 31 precincts,
  * writes a `city` property per precinct (majority-area overlap with the county's
    city boundaries; the unincorporated remainder is labelled "Unincorporated").

Usage:
  build_county_geo.py <county.geojson> <cities.geojson> <out.geojson> <out_ids.json>
                      [simplify_deg]
"""
import json
import os
import re
import sys

from shapely.geometry import shape, mapping
from shapely.strtree import STRtree

SIMPLIFY_DEG = 0.00012     # ~13 m; county-scale map, not a parcel viewer
PRECISION = 5
PID_RE = re.compile(r"^\d{5,7}$")


def round_geom(g, nd=PRECISION):
    t = g["type"]
    if t == "Polygon":
        g["coordinates"] = [[[round(x, nd), round(y, nd)] for x, y in r]
                            for r in g["coordinates"]]
    elif t == "MultiPolygon":
        g["coordinates"] = [[[[round(x, nd), round(y, nd)] for x, y in r] for r in p]
                            for p in g["coordinates"]]
    return g


def detect_pid_field(feats):
    """Precinct-id field = the property holding the most distinct 5-7 digit values
    (beats OBJECTID sequences and name/label fields). Same heuristic as build_geo.py."""
    best, best_n = None, -1
    for key in feats[0]["properties"].keys():
        vals = {str(f["properties"].get(key, "")).strip() for f in feats}
        n = sum(1 for v in vals if PID_RE.match(v))
        if n > best_n:
            best, best_n = key, n
    return best, best_n


def main():
    county_path, cities_path, out_path, ids_path = sys.argv[1:5]
    simplify = float(sys.argv[5]) if len(sys.argv) > 5 else SIMPLIFY_DEG

    county = json.load(open(county_path))
    feats = county["features"]
    if not feats:
        print("ERROR: empty county geojson", file=sys.stderr)
        sys.exit(1)

    pid_field, n_ids = detect_pid_field(feats)
    if n_ids <= 0:
        print("ERROR: no precinct-id-like field found", file=sys.stderr)
        sys.exit(1)

    cities = json.load(open(cities_path))
    cgeoms = [shape(f["geometry"]).buffer(0) for f in cities["features"]]
    cnames = [f["properties"]["city"] for f in cities["features"]]
    tree = STRtree(cgeoms)

    kept, ids, seen = [], [], set()
    by_city = {}
    for f in feats:
        pid = str(f["properties"].get(pid_field, "")).strip()
        if not pid or pid in seen:
            continue
        g = shape(f["geometry"]).buffer(0)
        area = g.area or 1e-12

        # city = largest area overlap; candidates prefiltered by bbox via STRtree
        city, best = "Unincorporated", 0.0
        for idx in tree.query(g):
            inter = g.intersection(cgeoms[int(idx)]).area
            if inter > best:
                best, city = inter, cnames[int(idx)]
        frac = round(best / area, 3) if area else 0.0

        seen.add(pid)
        ids.append(pid)
        by_city[city] = by_city.get(city, 0) + 1
        gs = g.simplify(simplify, preserve_topology=True) if simplify > 0 else g
        kept.append({"type": "Feature",
                     "properties": {"precinct": pid, "city": city, "city_frac": frac},
                     "geometry": round_geom(mapping(gs))})

    json.dump({"type": "FeatureCollection",
               "crs": {"type": "name",
                       "properties": {"name": "urn:ogc:def:crs:OGC:1.3:CRS84"}},
               "features": kept}, open(out_path, "w"), separators=(",", ":"))
    json.dump(sorted(ids), open(ids_path, "w"))

    kb = os.path.getsize(out_path) / 1024
    print(f"  join field '{pid_field}': {len(kept)} county precincts -> {out_path} ({kb:.0f} KB)")
    top = ", ".join(f"{c}:{n}" for c, n in sorted(by_city.items(), key=lambda x: -x[1]))
    print(f"    by city: {top}")


if __name__ == "__main__":
    main()
