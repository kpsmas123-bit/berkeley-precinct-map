#!/usr/bin/env python3
"""
Build the Berkeley council-district overlays from the 2022 redistricting layer:
  - d1_boundary.geojson      (District 1 only, emphasized overlay)
  - council_districts.geojson (all 8 districts, faint context lines)

These are current district lines and are drawn on EVERY election. Note: precincts
before the 2021 redistricting do not nest cleanly into these boundaries, so the
overlay is a reference, not a basis for historical D1 vote aggregation.

Usage:
  build_districts.py <council_districts_2022.geojson> <out_dir>
"""
import json
import os
import sys

from shapely.geometry import shape, mapping

TOL = 0.00003
ND = 6


def simp(geom):
    g = shape(geom).simplify(TOL, preserve_topology=True)
    m = mapping(g)
    rc = lambda c: [round(x, ND) for x in c]
    if m["type"] == "Polygon":
        m["coordinates"] = [[rc(p) for p in r] for r in m["coordinates"]]
    else:
        m["coordinates"] = [[[rc(p) for p in r] for r in poly] for poly in m["coordinates"]]
    return m


def main():
    src, out_dir = sys.argv[1], sys.argv[2]
    gj = json.load(open(src))
    feats = gj["features"]

    def feat(f):
        return {"type": "Feature",
                "properties": {"district": f["properties"]["DISTRICT"],
                               "member": f["properties"].get("MEMBER_NAME")},
                "geometry": simp(f["geometry"])}

    d1 = [f for f in feats if str(f["properties"]["DISTRICT"]) == "1"][0]
    json.dump({"type": "FeatureCollection", "features": [feat(d1)]},
              open(os.path.join(out_dir, "d1_boundary.geojson"), "w"), separators=(",", ":"))
    json.dump({"type": "FeatureCollection", "features": [feat(f) for f in feats]},
              open(os.path.join(out_dir, "council_districts.geojson"), "w"), separators=(",", ":"))
    print(f"districts: d1_boundary.geojson + council_districts.geojson ({len(feats)} districts) -> {out_dir}")


if __name__ == "__main__":
    main()
