#!/usr/bin/env python3
"""
Filter a county Consolidated-Precincts GeoJSON to the Berkeley precinct set for an
election, lightly simplify, round coordinates, and emit a compact GeoJSON.

Join validation: reports precincts that have results but no polygon (orphans) and
polygons kept. Input GeoJSON is expected in lon/lat (CRS84 / EPSG:4326).

Usage:
  build_geo.py <county.geojson> <results.json> <out.geojson> [simplify_deg]
"""
import json
import sys

from shapely.geometry import shape, mapping

SIMPLIFY_DEG = 0.00003   # ~3m; light, keeps precinct shape, shrinks file
PRECISION = 6            # decimal places (~0.1m) — plenty for web display


def round_coords(geom, nd=PRECISION):
    if isinstance(geom, dict):
        gtype = geom["type"]
        if gtype == "Polygon":
            geom["coordinates"] = [[[round(x, nd), round(y, nd)] for x, y in ring]
                                   for ring in geom["coordinates"]]
        elif gtype == "MultiPolygon":
            geom["coordinates"] = [[[[round(x, nd), round(y, nd)] for x, y in ring]
                                     for ring in poly] for poly in geom["coordinates"]]
    return geom


def main():
    county_path, results_path, out_path = sys.argv[1], sys.argv[2], sys.argv[3]
    simplify = float(sys.argv[4]) if len(sys.argv) > 4 else SIMPLIFY_DEG

    results = json.load(open(results_path))
    wanted = set(results["berkeley_precincts"])

    county = json.load(open(county_path))
    features, seen = [], set()
    for f in county["features"]:
        pid = str(f["properties"].get("Precinct_ID", "")).strip()
        if pid not in wanted or pid in seen:
            continue
        seen.add(pid)
        geom = shape(f["geometry"])
        if simplify > 0:
            geom = geom.simplify(simplify, preserve_topology=True)
        features.append({
            "type": "Feature",
            "properties": {"precinct": pid},
            "geometry": round_coords(mapping(geom)),
        })

    orphans = sorted(wanted - seen)
    out = {"type": "FeatureCollection",
           "crs": {"type": "name", "properties": {"name": "urn:ogc:def:crs:OGC:1.3:CRS84"}},
           "features": features}
    with open(out_path, "w") as fh:
        json.dump(out, fh, separators=(",", ":"))

    import os
    kb = os.path.getsize(out_path) / 1024
    print(f"geo: {len(features)}/{len(wanted)} precincts kept -> {out_path} ({kb:.0f} KB)")
    if orphans:
        print(f"  ORPHANS (results but no polygon): {orphans}")
    # polygons with no results (context precincts) — none expected since we filter to wanted
    extra = seen - wanted
    if extra:
        print(f"  polygons with no results: {sorted(extra)}")


if __name__ == "__main__":
    main()
