#!/usr/bin/env python3
"""
Build the results file for an election whose PRECINCT canvass is not published yet.

The county releases precinct-level figures only at/near certification. For an
election in that window we still know two real things:

  1. the precinct geometry (the county publishes it before election day), and
  2. the citywide contest outcomes (from the live results portal).

So this emits a results file with the precinct roster and district assignment
present but every precinct's `contests` empty, plus the citywide block embedded.
`precinct_results: false` tells the frontend to disable the choropleth and show the
citywide summary instead of pretending a precinct pattern exists.

Once the SOV is published, drop `precinct_results` from the manifest entry, add the
`sov` / `district_canvass_xlsx` sources, and run ./build.sh <id> — the normal path
overwrites this file and the map lights up with no frontend changes.

Usage:
  build_pending_results.py <election_id> <precincts.geojson> <berkeley_ids.json> \
                           <citywide.json> <out_results.json>
"""
import json
import sys


def main():
    eid, geo_path, ids_path, city_path, out_path = sys.argv[1:6]

    ids = sorted(json.load(open(ids_path)))
    citywide = json.load(open(city_path))

    precincts = {pid: {"registered": 0, "ballots_cast": 0, "contests": {}} for pid in ids}

    out = {
        "election_id": eid,
        "berkeley_precincts": ids,
        "precinct_results": False,
        "contests": {},
        "precincts": precincts,
        "citywide": citywide,
        "qa": "pending-certification",
    }
    json.dump(out, open(out_path, "w"), separators=(",", ":"))
    print(f"  pending-election results: {len(ids)} Berkeley precincts, no precinct "
          f"tallies, {len(citywide.get('contests', []))} citywide contests -> {out_path}")


if __name__ == "__main__":
    main()
