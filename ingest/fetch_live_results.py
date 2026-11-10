#!/usr/bin/env python3
"""
Fetch CITYWIDE (not precinct-level) results for an election from the Alameda County
ROV live results portal, for an election whose precinct canvass has not been
published yet.

Why this exists
---------------
The county publishes the precinct-level Statement of Vote only at (or near)
certification, ~28-30 days after election day. Between election night and then, the
only machine-readable figures are the portal's running contest totals. This script
captures those so the map can show an election's real outcome, clearly flagged as
preliminary, while the choropleth stays disabled until precinct data exists.

Honesty constraints baked in
----------------------------
* Only contests whose name contains "Berkeley" are kept. For those the jurisdiction
  IS Berkeley (council, school board, rent board, auditor, city measures), so the
  portal's contest total is a genuine Berkeley citywide total. County/state contests
  are deliberately DROPPED: the portal reports them countywide, and a countywide
  number presented on a Berkeley map would be a lie.
* The portal's "Preliminary/Unofficial - Update #N / Last Updated" banner is recorded
  verbatim, so the page can state exactly which count it is showing.
* Nothing here is ever written into a precinct results file. Output is a separate
  citywide blob consumed only by the summary panel.

Usage:
  fetch_live_results.py <rov_election_id> <out.json> [--url URL]

Re-run as the count updates; once the SOV is published, add the normal manifest
sources and run ./build.sh <id>, which supersedes this file.
"""
import json
import re
import sys
import time
import urllib.request

UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124.0 Safari/537.36")
PORTAL = "https://alamedacountyca.gov/rovresults/{eid}/"

# A contest total from this portal is a true Berkeley citywide total only when the
# contest's jurisdiction is Berkeley itself.
BERKELEY = re.compile(r"berkeley", re.I)

RACE_SPLIT = re.compile(r"<!--\s*Start Race:\s*(.*?)\s*-->", re.I | re.S)
ROW = re.compile(
    r"<TH[^>]*class=\"resultsRow[^\"]*\"[^>]*>(.*?)</TH>\s*"
    r"<TD[^>]*>(.*?)</TD>\s*<TD[^>]*>(.*?)</TD>",
    re.I | re.S)
DIV = lambda cls: re.compile(r"<div[^>]*class=\"" + cls + r"[^\"]*\"[^>]*>(.*?)</div>", re.I | re.S)
REPORTED, PASSING, VOTEFOR = DIV("reported"), DIV("passing"), DIV("votefor")
# No "End Race" marker is emitted, so a split body runs to the next "Start Race"
# comment and the last race in a section swallows what follows it. Every block ends
# with a "Back to Top" link; cut there.
BODY_END = re.compile(r'<div[^>]*class="backtotop"|Back to Top', re.I)
STATUS_RE = re.compile(r"(Preliminary/Unofficial[^<]*)", re.I)
UPDATED_RE = re.compile(r"lastUpdated[^>]*>\s*<span>\s*Last Updated:\s*([^<]+)", re.I)


def txt(s):
    s = re.sub(r"(?is)<[^>]+>", " ", s)
    s = s.replace("&nbsp;", " ").replace("&amp;", "&")
    return re.sub(r"\s+", " ", s).strip()


def as_int(s):
    s = re.sub(r"[^\d-]", "", txt(s))
    return int(s) if s not in ("", "-") else 0


def as_pct(s):
    m = re.search(r"-?[\d.]+", txt(s))
    return float(m.group()) if m else 0.0


def fetch(url):
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=60) as r:
        return r.read().decode("utf-8", "replace")


def parse(html):
    ms, mu = STATUS_RE.search(html), UPDATED_RE.search(html)
    status = txt(ms.group(1)) if ms else ""
    updated = txt(mu.group(1)) if mu else ""

    contests = []
    parts = RACE_SPLIT.split(html)
    # parts = [pre, name1, body1, name2, body2, ...]
    for i in range(1, len(parts) - 1, 2):
        name, body = txt(parts[i]), BODY_END.split(parts[i + 1])[0]
        if not BERKELEY.search(name):
            continue
        rows = []
        for ch, votes, pct in ROW.findall(body):
            ch = txt(ch)
            if not ch:
                continue
            rows.append({"choice": ch, "votes": as_int(votes), "pct": as_pct(pct)})
        if not rows:
            continue
        rep = REPORTED.search(body)
        pas = PASSING.search(body)
        vf = VOTEFOR.search(body)
        rcv = "(RCV)" in name
        entry = {
            "name": re.sub(r"\s*\(RCV\)\s*$", "", name).strip(),
            "rcv": rcv,
            "kind": "measure" if any(re.fullmatch(r"(bonds\s+)?(yes|no)", r["choice"], re.I)
                                     for r in rows) else "candidate",
            "choices": rows,
            "total_votes": sum(r["votes"] for r in rows),
        }
        if rep:
            entry["reported"] = txt(rep.group(1))
        if pas:
            entry["threshold"] = txt(pas.group(1))
        if vf:
            entry["vote_for"] = txt(vf.group(1))
        seats = re.search(r"Vote for no more than\s+\w+\s*\((\d+)\)", entry.get("vote_for", ""), re.I)
        if seats:
            entry["seats"] = int(seats.group(1))
        contests.append(entry)
    return status, updated, contests


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    eid, out_path = args[0], args[1]
    url = next((a.split("=", 1)[1] for a in sys.argv[1:] if a.startswith("--url=")),
               PORTAL.format(eid=eid))

    html = fetch(url)
    status, updated, contests = parse(html)
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
