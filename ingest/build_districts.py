#!/usr/bin/env python3
"""
Build the per-election council-district overlay (all districts, simplified for
display) from the district-boundary set in effect for that election. The frontend
draws every district faintly and emphasizes the focus district (D1) by filtering on
the `district` property, so one file per election is enough.

Note: these are the era-correct lines for the election. Because Berkeley redistricts
each decade, "District 1" in a pre-2021 election is a different geographic area than
current D1 — the overlay is drawn honestly per era, not back-projected.

Usage:
  build_districts.py <district_map.geojson> <out.districts.geojson>
"""
import json
import sys

from shapely.geometry import shape, mapping

TOL = 0.00003
ND = 6


def simp(geom):
    m = mapping(shape(geom).simplify(TOL, preserve_topology=True))
    rc = lambda c: [round(x, ND) for x in c]
    if m["type"] == "Polygon":
        m["coordinates"] = [[rc(p) for p in r] for r in m["coordinates"]]
    else:
        m["coordinates"] = [[[rc(p) for p in r] for r in poly] for poly in m["coordinates"]]
    return m


def main():
    src, out = sys.argv[1], sys.argv[2]
    gj = json.load(open(src))
    feats = [{"type": "Feature",
              "properties": {"district": str(f["properties"]["district"]),
                             "member": f["properties"].get("member")},
              "geometry": simp(f["geometry"])}
             for f in gj["features"]]
    feats.sort(key=lambda f: int(f["properties"]["district"]))
    json.dump({"type": "FeatureCollection", "features": feats},
              open(out, "w"), separators=(",", ":"))
    print(f"districts overlay: {len(feats)} districts -> {out}")


if __name__ == "__main__":
    main()
