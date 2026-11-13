#!/usr/bin/env python3
"""
Fetch CITYWIDE (not precinct-level) results for an election from the Alameda County
ROV live results portal, for an election whose precinct canvass has not been
published yet.

Only contests whose jurisdiction IS Berkeley are kept: the portal reports county and
state contests countywide, and a countywide number on a Berkeley map would be false.
The portal's markup quirks live in portal.py. See docs/pre-certification.md.

Usage:
  fetch_live_results.py <rov_election_id> <out.json> [--url URL]

Re-run as the count updates; once the SOV is published, add the normal manifest
sources and run ./build.sh <id>, which supersedes this file.
"""
import json
import os
import re
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import portal  # noqa: E402

# A contest total from this portal is a true Berkeley citywide total only when the
# contest's jurisdiction IS Berkeley. County and state contests are reported
# countywide, and a countywide number on a Berkeley map would be false.
BERKELEY = re.compile(r"berkeley", re.I)


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    eid, out_path = args[0], args[1]
    url = next((a.split("=", 1)[1] for a in sys.argv[1:] if a.startswith("--url=")),
               portal.URL.format(eid=eid))

    html = portal.fetch(url=url)
    b = portal.banner(html)
    status, updated = b["status"], b["last_updated"]
    contests = [c for c in portal.races(html) if BERKELEY.search(c["name"])]
    if not contests:
        print(f"ERROR: no Berkeley contests parsed from {url}", file=sys.stderr)
        sys.exit(1)

    out = {
        "rov_election_id": eid,
        "source_url": url,
        "status": status or "Preliminary/Unofficial",
        "county_last_updated": updated,
        "fetched_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "scope": "citywide",
        "precinct_level": False,
        "note": ("Citywide totals scraped from the county's live results portal. "
                 "Berkeley-jurisdiction contests only — countywide and statewide "
                 "contests are excluded because the portal reports them countywide, "
                 "not for Berkeley. Precinct-level figures do not exist until the "
                 "county publishes the certified Statement of Vote."),
        "contests": contests,
    }
    json.dump(out, open(out_path, "w"), indent=2)
    print(f"{status} | county last updated: {updated}")
    print(f"parsed {len(contests)} Berkeley citywide contests -> {out_path}")
    for c in contests:
        lead = max(c["choices"], key=lambda r: r["votes"])
        print(f"  {c['name'][:52]:<52} {lead['choice'][:26]:<26} {lead['pct']:>6.2f}%")


if __name__ == "__main__":
    main()
