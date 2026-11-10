#!/usr/bin/env python3
"""
Build the results file for an election whose certified PRECINCT canvass is not
published yet.

The county releases precinct-level figures only at/near certification. For an
election in that window we know three real things:

  1. the precinct geometry (published before election day),
  2. the citywide contest outcomes (the live results portal), and
  3. per-precinct votes for the one or two contests the county puts on its own live
     results map — see ingest/live_map_feed.py.

(3) is the difference between a blank map and a usable one. Berkeley is in CD-12,
which the county does not map, but the Nov 2026 transit measure is countywide and
covers all 31 Berkeley precincts, so that contest maps for real.

So this emits one of two shapes:

  precinct_results: "partial"   at least one contest has Berkeley precinct votes.
                                Those contests are in `contests` / `precincts` and
                                behave exactly like certified ones; everything else
                                on the ballot stays in the `citywide` block.
  precinct_results: false       nothing mapped — the roster is present and every
                                precinct's `contests` is empty, so the frontend
                                blanks the choropleth rather than guessing.

Either way per-precinct registration and ballots cast are 0: neither live feed
carries them, so turnout is not available and the frontend must disable it.

Once the SOV is published, drop `precinct_results` from the manifest entry, add the
`sov` / `district_canvass_xlsx` sources, and run ./build.sh <id> — the normal path
overwrites this file.

Usage:
  build_pending_results.py <election_id> <precincts.geojson> <berkeley_ids.json> \
                           <citywide.json> <out_results.json> [--map-url URL] [--no-map]
"""
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import live_map_feed  # noqa: E402


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    opt = {a.split("=", 1)[0].lstrip("-"): (a.split("=", 1)[1] if "=" in a else True)
           for a in sys.argv[1:] if a.startswith("--")}
    eid, geo_path, ids_path, city_path, out_path = args[:5]

    ids = sorted(json.load(open(ids_path)))
    idset = set(ids)
    citywide = json.load(open(city_path))

    # ---- (3) the contests the county maps precinct by precinct ------------------
    contests, per_precinct, live_meta = {}, {}, {}
    if not opt.get("no-map"):
        url = opt.get("map-url") or live_map_feed.FEED_URL
        try:
            feed = live_map_feed.fetch(url)
            mapped, meta, reporting = live_map_feed.parse(feed)
        except Exception as e:                      # the feed is best-effort
            print(f"  live map feed unavailable ({e}) — citywide only")
            mapped, meta, reporting = {}, {}, {}
        for name, rows in mapped.items():
            hit = {pid: ch for pid, ch in rows.items() if pid in idset}
            if not hit:
                continue                            # not on Berkeley's ballot, or not mapped here
            contests[name] = {"rcv": meta[name]["rcv"], "kind": meta[name]["kind"],
                              "choices": meta[name]["choices"],
                              "multi": False, "seats": None, "precinct_level": True}
            if meta[name].get("threshold"):
                contests[name]["threshold"] = meta[name]["threshold"]
            per_precinct[name] = hit
            tot = {}
            for ch in hit.values():
                for c, v in ch.items():
                    tot[c] = tot.get(c, 0) + v
            live_meta[name] = {"precincts": len(hit), "totals": tot}
        if contests:
            live_meta["_feed"] = {
                "url": url,
                "county_last_updated": feed.get("lastUpdatedDateTime", ""),
                "election_name": feed.get("electionName", ""),
                "reporting": {pid: reporting[pid]["pct"] for pid in ids if pid in reporting},
            }

    precincts = {}
    for pid in ids:
        precincts[pid] = {
            "registered": 0, "ballots_cast": 0,
            "contests": {n: {"choices": rows[pid]}
                         for n, rows in per_precinct.items() if pid in rows},
        }

    partial = bool(contests)
    out = {
        "election_id": eid,
        "berkeley_precincts": ids,
        "precinct_results": "partial" if partial else False,
        "preliminary": True,
        "contests": contests,
        "precincts": precincts,
        "citywide": citywide,
        "live": {
            "fetched_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
            "note": ("Per-precinct votes for the contests the county publishes on its "
                     "live results map; every other contest on the ballot is citywide "
                     "totals only until the certified Statement of Vote. Per-precinct "
                     "registration and turnout exist in neither feed."),
            **live_meta,
        },
        "qa": "pending-certification",
    }
    json.dump(out, open(out_path, "w"), separators=(",", ":"))

    n_city = len(citywide.get("contests", []))
    if partial:
        print(f"  pending-election results: {len(ids)} Berkeley precincts, "
              f"{len(contests)} contest(s) mapped precinct by precinct, "
              f"{n_city} citywide contests -> {out_path}")
        for n in contests:
            m = live_meta[n]
            lead = max(m["totals"], key=m["totals"].get) if m["totals"] else "—"
            d = sum(m["totals"].values()) or 1
            cover = f"{m['precincts']}/{len(ids)} precincts"
            print(f"    {n[:52]:<52} {cover:<16} {lead[:18]:<18} "
                  f"{100*m['totals'].get(lead,0)/d:>5.1f}% in Berkeley")
    else:
        print(f"  pending-election results: {len(ids)} Berkeley precincts, no precinct "
              f"tallies, {n_city} citywide contests -> {out_path}")


if __name__ == "__main__":
    main()
