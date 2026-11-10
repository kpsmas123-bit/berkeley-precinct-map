#!/usr/bin/env python3
"""
Fetch Alameda County city boundaries once and write a simplified overlay used by
the countywide map (city outlines + the precinct -> city label).

Source: Alameda County Open Data Hub, "City_Boundaries" (14 incorporated cities
plus one feature covering the unincorporated remainder, which the county labels
"Alameda County" and this script renames to "Unincorporated").

Output: data/processed/county/cities.geojson

Usage: fetch_city_boundaries.py [--force]
"""
import json
import os
import sys
import urllib.request

from shapely.geometry import shape, mapping

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT_DIR = os.path.join(ROOT, "data", "processed", "county")
OUT = os.path.join(OUT_DIR, "cities.geojson")

DATASET = "5a45c0fa82a849eb9c936df0fe2a0d7e"
URL = (f"https://opendata.arcgis.com/api/v3/datasets/{DATASET}"
       "/downloads/data?format=geojson&spatialRefId=4326")
UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124.0 Safari/537.36")

SIMPLIFY = 0.0002     # city outlines are decoration; keep them cheap
PRECISION = 5
UNINC = "Unincorporated"


def round_geom(g, nd=PRECISION):
    t = g["type"]
    if t == "Polygon":
        g["coordinates"] = [[[round(x, nd), round(y, nd)] for x, y in r]
                            for r in g["coordinates"]]
    elif t == "MultiPolygon":
        g["coordinates"] = [[[[round(x, nd), round(y, nd)] for x, y in r] for r in p]
                            for p in g["coordinates"]]
    return g


def main():
    os.makedirs(OUT_DIR, exist_ok=True)
    if os.path.exists(OUT) and "--force" not in sys.argv:
        print(f"  cached city boundaries -> {OUT}")
        return

    req = urllib.request.Request(URL, headers={"User-Agent": UA,
                                               "Referer": "https://data.acgov.org/"})
    with urllib.request.urlopen(req, timeout=180) as r:
        raw = json.loads(r.read().decode("utf-8", "replace"))

    feats = []
    for f in raw["features"]:
        name = str(f["properties"].get("NAME", "")).strip()
        if not name:
            continue
        if name.lower() == "alameda county":
            name = UNINC
        g = shape(f["geometry"]).buffer(0)
        gs = g.simplify(SIMPLIFY, preserve_topology=True)
        feats.append({"type": "Feature",
                      "properties": {"city": name},
                      "geometry": round_geom(mapping(gs))})

    json.dump({"type": "FeatureCollection",
               "crs": {"type": "name",
                       "properties": {"name": "urn:ogc:def:crs:OGC:1.3:CRS84"}},
               "features": feats},
              open(OUT, "w"), separators=(",", ":"))
    kb = os.path.getsize(OUT) / 1024
    print(f"  city boundaries: {len(feats)} areas -> {OUT} ({kb:.0f} KB)")
    print("    " + ", ".join(sorted(f["properties"]["city"] for f in feats)))


if __name__ == "__main__":
    main()
