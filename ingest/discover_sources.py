#!/usr/bin/env python3
"""
Find an election's canvass files on the county's election page and write them into
the manifest — so finishing a pending election is one command instead of hand-copying
URLs.

The county does not keep one URL convention. Nov 2024 published to
  .../02_election_information/SOV/20241105/Statement of Vote - General Election.xlsx
while June 2026 published to
  .../02_election_information/PDFs/20260602/Results/PrecinctCanvassJun02.xlsx
so the links are discovered from the election page rather than guessed.

What it does, for one election id:
  1. fetch the election page named in the manifest (sources.election_page),
  2. look for a precinct canvass (Statement of Vote) and a District Canvass in xlsx,
  3. write them into sources.sov / sources.district_canvass_xlsx,
  4. clear "precinct_results": false once a precinct canvass exists, so ./build.sh
     stops treating the election as pending.

Nothing is written unless a precinct canvass is found. Safe to re-run.

Usage:
  discover_sources.py <election_id> [--dry-run]
"""
import json
import os
import re
import sys
import urllib.parse
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MANIFEST = os.path.join(ROOT, "data", "processed", "elections.json")
UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124.0 Safari/537.36")

# A precinct-level canvass is published under either name.
SOV_RX = re.compile(r"(statement[\s_%20-]*of[\s_%20-]*vote|precinct[\s_%20-]*canvass)", re.I)
# "District Canvas" is misspelled with one 's' on several county pages.
DC_RX = re.compile(r"district[\s_%20-]*canvas", re.I)
XLSX_RX = re.compile(r"\.xlsx(\?|$)", re.I)


def fetch(url):
    req = urllib.request.Request(url, headers={"User-Agent": UA,
                                               "Referer": "https://acvote.alamedacountyca.gov/"})
    with urllib.request.urlopen(req, timeout=120) as r:
        return r.read().decode("utf-8", "replace")


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    dry = "--dry-run" in sys.argv
    if not args:
        print(__doc__.strip().splitlines()[-1], file=sys.stderr)
        sys.exit(2)
    eid = args[0]

    manifest = json.load(open(MANIFEST))
    try:
        entry = next(e for e in manifest["elections"] if e["id"] == eid)
    except StopIteration:
        print(f"ERROR: {eid} is not in the manifest", file=sys.stderr)
        sys.exit(1)

    page = entry.get("sources", {}).get("election_page")
    if not page:
        print(f"ERROR: {eid} has no sources.election_page to search", file=sys.stderr)
        sys.exit(1)

    html = fetch(page)
    hrefs = re.findall(r'href="([^"]+)"', html)
    sov = dc = None
    for h in hrefs:
        full = urllib.parse.urljoin(page, h)
        if not XLSX_RX.search(full):
            continue
        tail = full.rsplit("/", 1)[-1]
        if DC_RX.search(tail):
            dc = dc or full
        elif SOV_RX.search(tail):
            sov = sov or full

    print(f"election page: {page}")
    print(f"  precinct canvass : {sov or '— not published yet —'}")
    print(f"  district canvass : {dc or '— none —'}")

    if not sov:
        print("\nNothing to do: the county has not published a precinct canvass yet.\n"
              "Alameda County releases it at or near certification, ~30 days after "
              "election day. Re-run this then.")
        sys.exit(0)

    entry.setdefault("sources", {})["sov"] = sov
    if dc:
        entry["sources"]["district_canvass_xlsx"] = dc
    was_pending = entry.pop("precinct_results", True) is False

    if dry:
        print("\n--dry-run: manifest not written")
        sys.exit(0)

    json.dump(manifest, open(MANIFEST, "w"), indent=2)
    print(f"\nmanifest updated for {eid}"
          + (" (no longer pending)" if was_pending else ""))
    print(f"next:  ./build.sh {eid} && ./build_county.sh {eid}")


if __name__ == "__main__":
    main()
