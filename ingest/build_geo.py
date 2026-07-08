#!/usr/bin/env python3
"""
Select the Berkeley precincts for an election SPATIALLY (independent of contest
names, so it works even for primaries with no Berkeley-specific contest), simplify,
and emit a compact GeoJSON plus the Berkeley precinct-id list.

Berkeley = the union of the era's council districts (that union is the city). A
county precinct is "Berkeley" if the majority of its area falls inside that union.

Input county GeoJSON is expected in lon/lat (CRS84 / EPSG:4326). The precinct-id
property is auto-detected (field names drift across elections).

Usage:
  build_geo.py <county.geojson> <district_map.geojson> <out.geojson> <out_ids.json> [simplify_deg]
"""
import json
import os
import sys

from shapely.geometry import shape, mapping
from shapely.ops import unary_union

SIMPLIFY_DEG = 0.00003
PRECISION = 6
INSIDE = 0.5  # majority of precinct area must be inside the city


def round_coords(geom, nd=PRECISION):
    gtype = geom["type"]
    if gtype == "Polygon":
        geom["coordinates"] = [[[round(x, nd), round(y, nd)] for x, y in ring]
                               for ring in geom["coordinates"]]
    elif gtype == "MultiPolygon":
        geom["coordinates"] = [[[[round(x, nd), round(y, nd)] for x, y in ring]
                                 for ring in poly] for poly in geom["coordinates"]]
    return geom


def main():
    county_path, dmap_path, out_path, ids_path = sys.argv[1:5]
    simplify = float(sys.argv[5]) if len(sys.argv) > 5 else SIMPLIFY_DEG

    county = json.load(open(county_path))
    dmap = json.load(open(dmap_path))
    city = unary_union([shape(f["geometry"]).buffer(0) for f in dmap["features"]])

    feats = county["features"]
    if not feats:
        print("ERROR: empty county geojson", file=sys.stderr); sys.exit(1)

    # auto-detect the precinct-id field: consolidated precinct ids are 5-7 digit
    # numbers (e.g. 200100). Score each property by how many distinct such values it
    # holds — this cleanly beats OBJECTID/sequence keys (1..N) and name/label fields.
    import re
    pid_re = re.compile(r"^\d{5,7}$")
    best_field, best_n = None, -1
    for key in feats[0]["properties"].keys():
        vals = {str(f["properties"].get(key, "")).strip() for f in feats}
        n = sum(1 for v in vals if pid_re.match(v))
        if n > best_n:
            best_field, best_n = key, n
    if best_n <= 0:
        print("ERROR: no precinct-id-like field found in geojson", file=sys.stderr); sys.exit(1)

    kept, ids, seen = [], [], set()
    for f in feats:
        pid = str(f["properties"].get(best_field, "")).strip()
        if not pid or pid in seen:
            continue
        g = shape(f["geometry"]).buffer(0)
        area = g.area or 1e-12
        if g.intersection(city).area / area < INSIDE:
            continue
        seen.add(pid); ids.append(pid)
        gs = g.simplify(simplify, preserve_topology=True) if simplify > 0 else g
        kept.append({"type": "Feature", "properties": {"precinct": pid},
                     "geometry": round_coords(mapping(gs))})

    json.dump({"type": "FeatureCollection",
               "crs": {"type": "name", "properties": {"name": "urn:ogc:def:crs:OGC:1.3:CRS84"}},
               "features": kept}, open(out_path, "w"), separators=(",", ":"))
    json.dump(sorted(ids), open(ids_path, "w"))
    kb = os.path.getsize(out_path) / 1024
    print(f"  join field '{best_field}': {len(kept)} Berkeley precincts -> {out_path} ({kb:.0f} KB)")


if __name__ == "__main__":
    main()
