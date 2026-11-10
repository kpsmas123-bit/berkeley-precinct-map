#!/usr/bin/env python3
"""
Trim a full-county parsed canvass down to the countywide map's contest set, attach
each precinct's city, and precompute city + county aggregates.

The upstream parsers (parse_canvass.py / parse_sovc_csv.py) are reused unchanged for
the county build: they are handed the county precinct-id list instead of the Berkeley
one, so they emit every precinct and every contest. This script then drops every
contest that is not a big shared-ballot race (see county_contests.py) — which is most
of them — and rolls up the aggregates the panel needs so the browser does no summing.

Usage:
  filter_county_results.py <full_results.json> <county_geo.geojson> <out.json>
"""
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from county_contests import category, included, sort_key  # noqa: E402

UNINC = "Unincorporated"

# A contest only proves city residency if it is a CITY office or a "City of X"
# measure. City-named school and special districts are the trap: "Hayward Area
# Recreation & Park District" and "Hayward USD" both reach well past Hayward's city
# limits into unincorporated county, so matching a bare city name would relabel
# hundreds of unincorporated precincts.
CITY_OFFICE = re.compile(
    r"(city of\b|^mayor\b|\bmayor\s*[-,]|\bcity council\b|\bcity auditor\b"
    r"|\bcity attorney\b|\bcity clerk\b|\bcity treasurer\b"
    r"|\brent stabilization board\b)", re.I)
NOT_CITY = re.compile(
    r"(\bunified\b|\bschool\b|\bu\.?s\.?d\b|\bccd\b|\bcommunity college\b"
    r"|\bpark district\b|\brecreation\b|\bhealthcare\b|\bhospital\b"
    r"|\btransit\b|\butility\b|\bsanitary\b|\bwater\b|\bfire protection\b"
    r"|\bregional park\b|\bboard of directors\b)", re.I)


def cities_from_contests(contest_names, city_names):
    """Infer a precinct's jurisdiction from the city contests it votes in.

    This beats pure geometry on city borders. Some precincts are slivers whose
    polygon falls inside a neighbour's published outline while their voters are on
    the other city's ballot — e.g. in Nov 2024 precincts 203880/203890/208690 sit
    ~100% inside Oakland's outline but vote for Mayor of Berkeley and Berkeley city
    measures. What a precinct votes ON is its jurisdiction; the polygon is a guess.

    Only city offices and "City of X" measures count (see CITY_OFFICE / NOT_CITY).
    Geometry remains the fallback for precincts with no such contest — unincorporated
    areas, and elections with no local races at all.

    A city token followed by "County" is ignored, so "Measure A - Alameda County"
    does not make a precinct part of the city of Alameda.
    """
    hits = {}
    for n in contest_names:
        if NOT_CITY.search(n) or not CITY_OFFICE.search(n):
            continue
        for c in city_names:
            if re.search(rf"\b{re.escape(c)}\b(?!\s+County\b)", n, re.I):
                hits[c] = hits.get(c, 0) + 1
    return hits


def agg(entries):
    """Sum a list of per-precinct contest entries into one tally."""
    out = {"choices": {}, "cast": 0}
    for e in entries:
        for ch, v in e.get("choices", {}).items():
            out["choices"][ch] = out["choices"].get(ch, 0) + v
        out["cast"] += e.get("cast", 0) or 0
    return out


def main():
    full_path, geo_path, out_path = sys.argv[1:4]
    full = json.load(open(full_path))
    geo = json.load(open(geo_path))

    geo_city = {str(f["properties"]["precinct"]): f["properties"].get("city", UNINC)
                for f in geo["features"]}
    city_names = sorted({c for c in geo_city.values() if c != UNINC})

    # Resolve each precinct's jurisdiction: local-contest evidence first, geometry
    # as the fallback. Tracked so the build logs how often the two disagree.
    city_of, by_contest, overrides = {}, 0, []
    for pid, p in full.get("precincts", {}).items():
        gcity = geo_city.get(pid, UNINC)
        hits = cities_from_contests(p.get("contests", {}).keys(), city_names)
        if len(hits) == 1:
            city = next(iter(hits))
        elif len(hits) > 1:
            city = gcity if gcity in hits else max(hits, key=hits.get)
        else:
            city = gcity
        if hits:
            by_contest += 1
        if city != gcity:
            overrides.append((pid, gcity, city))
        city_of[pid] = city
    for pid in geo_city:
        city_of.setdefault(pid, geo_city[pid])

    keep = [n for n in full.get("contests", {}) if included(n)]
    keep_set = set(keep)
    dropped = len(full.get("contests", {})) - len(keep)

    contests = {}
    for n in sorted(keep, key=sort_key):
        c = dict(full["contests"][n])
        c["category"] = category(n)
        contests[n] = c

    precincts, cities = {}, {}
    zeros_dropped = 0
    for pid, p in full.get("precincts", {}).items():
        city = city_of.get(pid, UNINC)
        kept_contests = {}
        for n, e in p.get("contests", {}).items():
            if n not in keep_set:
                continue
            # Drop zero-vote choices. In a primary most minor candidates poll 0 in
            # most precincts, and those entries are the bulk of the payload. The
            # contest catalog still lists every choice and the frontend reads a
            # missing choice as 0, so nothing is lost.
            trimmed = dict(e)
            ch = {k: v for k, v in e.get("choices", {}).items() if v}
            zeros_dropped += len(e.get("choices", {})) - len(ch)
            trimmed["choices"] = ch
            kept_contests[n] = trimmed
        precincts[pid] = {
            "registered": p.get("registered", 0),
            "ballots_cast": p.get("ballots_cast", 0),
            "city": city,
            "contests": kept_contests,
        }
        cities.setdefault(city, []).append(pid)
    cities = {c: sorted(p) for c, p in sorted(cities.items())}

    # aggregates: per contest -> countywide, and per contest -> per city
    county_totals, city_totals = {}, {}
    for n in contests:
        entries = [p["contests"][n] for p in precincts.values() if n in p["contests"]]
        county_totals[n] = agg(entries)
        per_city = {}
        for city, pids in cities.items():
            ce = [precincts[pid]["contests"][n] for pid in pids
                  if n in precincts[pid]["contests"]]
            if ce:
                per_city[city] = agg(ce)
        city_totals[n] = per_city

    # turnout rollups (registered / ballots cast), countywide and per city
    turnout = {"county": {"registered": sum(p["registered"] for p in precincts.values()),
                          "ballots_cast": sum(p["ballots_cast"] for p in precincts.values())},
               "cities": {}}
    for city, pids in cities.items():
        turnout["cities"][city] = {
            "registered": sum(precincts[p]["registered"] for p in pids),
            "ballots_cast": sum(precincts[p]["ballots_cast"] for p in pids)}

    out = {
        "election_id": full.get("election_id"),
        "scope": "county",
        "contests": contests,
        "precincts": precincts,
        "cities": cities,
        "county_totals": county_totals,
        "city_totals": city_totals,
        "turnout": turnout,
    }
    json.dump(out, open(out_path, "w"), separators=(",", ":"))

    mb = os.path.getsize(out_path) / 1024 / 1024
    cats = {}
    for n, c in contests.items():
        cats[c["category"]] = cats.get(c["category"], 0) + 1
    catstr = ", ".join(f"{k}:{v}" for k, v in sorted(cats.items()))
    print(f"  county results: kept {len(contests)} contests ({catstr}), dropped {dropped} local; "
          f"{len(precincts)} precincts in {len(cities)} jurisdictions -> {out_path} ({mb:.2f} MB)")
    print(f"    dropped {zeros_dropped:,} zero-vote precinct/choice entries")
    print(f"    jurisdiction: {by_contest} precincts resolved by local contests, "
          f"{len(precincts) - by_contest} by geometry"
          + (f"; {len(overrides)} corrected vs the city outline" if overrides else ""))
    for pid, g, c in overrides[:8]:
        print(f"      {pid}: outline said {g}, ballot says {c}")
    if len(overrides) > 8:
        print(f"      … and {len(overrides) - 8} more")


if __name__ == "__main__":
    main()
