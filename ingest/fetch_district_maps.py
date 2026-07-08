#!/usr/bin/env python3
"""
Fetch and normalize the Berkeley council-district boundary sets used across the
election range, into data/district_maps/<key>.geojson with uniform properties
{district, member}. Each election in elections.json references one of these by key.

  berkeley-council-2021 : 2021 redistricting (2022+ elections). Source: City of
                          Berkeley ArcGIS "Council Districts 2022" feature service.
  berkeley-council-2013 : 2010-census-adjusted map (2014-2020 elections). Source:
                          UC Berkeley GeoData (shapefile, UTM 10N -> reprojected).

Idempotent; re-run to refresh. Usage: fetch_district_maps.py
"""
import io
import json
import os
import zipfile

import requests
import shapefile
from pyproj import Transformer
from shapely.geometry import shape, mapping
from shapely.ops import transform as shp_transform

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "data", "district_maps")
ND = 6

FS_2021 = ("https://services1.arcgis.com/IYiCpZoSIq9lAxi8/arcgis/rest/services/"
           "Council_Districts_2022/FeatureServer/2/query")
ZIP_2013 = "https://spatial.lib.berkeley.edu/public/berkeley-s7wq14/data.zip"


def round_geom(geom):
    m = mapping(geom)
    rc = lambda c: [round(x, ND) for x in c]
    if m["type"] == "Polygon":
        m["coordinates"] = [[rc(p) for p in r] for r in m["coordinates"]]
    else:
        m["coordinates"] = [[[rc(p) for p in r] for r in poly] for poly in m["coordinates"]]
    return m


def write(key, features):
    features.sort(key=lambda f: int(f["properties"]["district"]))
    path = os.path.join(OUT, key + ".geojson")
    json.dump({"type": "FeatureCollection",
               "crs": {"type": "name", "properties": {"name": "urn:ogc:def:crs:OGC:1.3:CRS84"}},
               "features": features}, open(path, "w"), separators=(",", ":"))
    print(f"  wrote {key}.geojson ({len(features)} districts)")


def fetch_2021():
    params = {"where": "1=1", "outFields": "DISTRICT,MEMBER_NAME",
              "f": "geojson", "outSR": "4326"}
    gj = requests.get(FS_2021, params=params, timeout=90).json()
    feats = []
    for f in gj["features"]:
        p = f["properties"]
        feats.append({"type": "Feature",
                      "properties": {"district": str(p["DISTRICT"]),
                                     "member": p.get("MEMBER_NAME")},
                      "geometry": round_geom(shape(f["geometry"]).buffer(0))})
    write("berkeley-council-2021", feats)


def fetch_2013():
    z = zipfile.ZipFile(io.BytesIO(requests.get(ZIP_2013, timeout=90).content))
    names = {os.path.splitext(n)[1].lower(): n for n in z.namelist() if "." in n}
    reader = shapefile.Reader(shp=io.BytesIO(z.read(names[".shp"])),
                              dbf=io.BytesIO(z.read(names[".dbf"])),
                              shx=io.BytesIO(z.read(names[".shx"])))
    to_wgs = Transformer.from_crs("EPSG:32610", "EPSG:4326", always_xy=True).transform
    fields = [f[0] for f in reader.fields[1:]]
    feats = []
    for sr in reader.shapeRecords():
        rec = dict(zip(fields, sr.record))
        geom = shp_transform(to_wgs, shape(sr.shape.__geo_interface__).buffer(0))
        feats.append({"type": "Feature",
                      "properties": {"district": str(int(rec["District"])), "member": None},
                      "geometry": round_geom(geom)})
    write("berkeley-council-2013", feats)


def main():
    os.makedirs(OUT, exist_ok=True)
    print("fetching district maps ->", OUT)
    fetch_2021()
    fetch_2013()


if __name__ == "__main__":
    main()
