#!/usr/bin/env python3
"""
Write data/processed/county/elections.json — the manifest the countywide map loads
first. One entry per election that actually has a built county results file, newest
first, carrying the contest list so the frontend can populate its pickers without
fetching every election's results.

An election built in PRELIMINARY mode (live feeds, no certified canvass yet) carries
`preliminary: true` plus the county's own status banner, so the picker can label it
and the panel can state which count it is showing without first loading results. One
with neither a certified canvass nor a usable live feed is recorded under `pending`
with the reason, so the UI can say so instead of silently skipping it.

Usage: build_county_manifest.py
"""
import json
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PROC = os.path.join(ROOT, "data", "processed")
CDIR = os.path.join(PROC, "county")
OUT = os.path.join(CDIR, "elections.json")


def main():
    master = json.load(open(os.path.join(PROC, "elections.json")))
    entries, pending = [], []

    for e in master["elections"]:
        res = os.path.join(CDIR, "results", f"{e['id']}.json")
        if not os.path.exists(res):
            if not e.get("precinct_results", True):
                pending.append({"id": e["id"], "date": e["date"], "name": e["name"],
                                "reason": "precinct canvass not published yet"})
            continue
        r = json.load(open(res))
        prelim = bool(r.get("preliminary"))
        contests = [{"name": n,
                     "category": c.get("category"),
                     "kind": c.get("kind"),
                     "rcv": bool(c.get("rcv")),
                     "choices": c.get("choices", [])}
                    for n, c in r["contests"].items()]
        entry = {
            "id": e["id"],
            "date": e["date"],
            "name": e["name"],
            "results": f"results/{e['id']}.json",
            "geo": f"geo/{e['id']}.geojson",
            "n_precincts": len(r["precincts"]),
            "n_contests": len(contests),
            "cities": sorted(r["cities"].keys()),
            "contests": contests,
            "sources": e.get("sources", {}),
        }
        if prelim:
            st = r.get("status", {})
            entry["preliminary"] = True
            entry["status"] = {k: st.get(k) for k in (
                "status", "last_updated", "next_updates", "registered", "ballots_cast",
                "turnout_pct", "precincts_reported", "precincts_total",
                "precincts_reported_pct", "portal_url", "map_feed_url", "fetched_at",
                "reconciled", "note") if st.get(k) is not None}
            entry["precinct_level_contests"] = st.get("precinct_level_contests", [])
            entry["n_county_only"] = len(r.get("county_only", []))
        entries.append(entry)

    out = {
        "scope": "county",
        "jurisdiction": "Alameda County, California",
        "cities_geo": "cities.geojson",
        "contest_policy": ("Big shared-ballot contests only: statewide constitutional "
                           "offices, U.S. President/Senate/House, state propositions, and "
                           "the 2021 statewide recall. Local city, school and county races "
                           "are deliberately excluded — see ingest/county_contests.py."),
        "elections": entries,
        "pending": pending,
    }
    json.dump(out, open(OUT, "w"), indent=2)
    print(f"  county manifest: {len(entries)} elections"
          + (f", {len(pending)} pending" if pending else "") + f" -> {OUT}")
    for e in entries:
        tag = ""
        if e.get("preliminary"):
            tag = (f"  PRELIMINARY — {e['status'].get('status','')}"
                   f" ({e.get('n_county_only',0)} more countywide-only)")
        print(f"    {e['id']:<18} {e['n_precincts']:>4} precincts  "
              f"{e['n_contests']:>3} contests{tag}")
    for p in pending:
        print(f"    {p['id']:<18} pending — {p['reason']}")


if __name__ == "__main__":
    main()
