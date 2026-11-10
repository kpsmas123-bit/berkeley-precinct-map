#!/usr/bin/env python3
"""
The county's live results-map feed: the only pre-certification source with
PER-PRECINCT votes.

https://electionmaps.alamedacountyca.gov/json/electionResults.json is what the
county's own results map reads. It carries, for the one or two contests the county
chooses to map, every precinct's votes by candidate — plus each precinct's reporting
status. Everything else on the ballot is countywide-only until the certified
Statement of Vote appears, roughly 30 days after election day.

Both the countywide build (ingest/fetch_live_county.py) and the Berkeley build
(ingest/build_pending_results.py) read it, so the parse lives here once.

Shape returned by parse():
  mapped    {contest_name: {precinct_id: {choice: votes}}}   zero-vote entries dropped
  meta      {contest_name: {rcv, kind, choices, feed_totals, threshold}}
  reporting {precinct_id: {category, pct}}

`feed_totals` is the feed's own countywide total per candidate, which exists to be
reconciled against the sum of the precinct rows — see reconcile().

Run directly to inspect what the county is currently mapping:
  live_map_feed.py [--url URL]
"""
import json
import re
import sys
import urllib.request

FEED_URL = "https://electionmaps.alamedacountyca.gov/json/electionResults.json"
UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124.0 Safari/537.36")
YESNO = re.compile(r"^(bonds\s+)?(yes|no)$", re.I)


def fetch(url=FEED_URL, timeout=120):
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8", "replace"))


def _pct(s):
    m = re.search(r"-?[\d.]+", str(s))
    return float(m.group()) if m else 0.0


def parse(feed):
    cands = feed.get("candidates", {})
    by_race = {}
    for key, c in cands.items():
        by_race.setdefault(str(c["RACE_ID"]), {})[str(key)] = c

    mapped, meta = {}, {}
    for rid, race in feed.get("races", {}).items():
        name = str(race.get("description", "")).strip()
        names = {k: v["name"] for k, v in by_race.get(str(rid), {}).items()}
        if not name or not names:
            continue
        # the feed gives each candidate a stable display order per precinct
        order = sorted(names, key=lambda k: next(
            (p["candidates"][k]["order"] for p in race["precincts"].values()
             if k in p.get("candidates", {})), 99))
        per_precinct = {}
        for pid, p in race.get("precincts", {}).items():
            if p.get("noVotesCounted"):
                continue
            ch = {names[k]: v["votes"] for k, v in p.get("candidates", {}).items()
                  if k in names and v.get("votes")}
            if ch:
                per_precinct[str(pid)] = ch
        if not per_precinct:
            continue
        clean = re.sub(r"\s*\(RCV\)\s*$", "", name).strip()
        mapped[clean] = per_precinct
        meta[clean] = {
            "rcv": "(RCV)" in name,
            "kind": "measure" if all(YESNO.fullmatch(n) for n in names.values())
                    else "candidate",
            "choices": [names[k] for k in order],
            "feed_totals": {names[k]: int(v["CAN_VOTES"])
                            for k, v in by_race.get(str(rid), {}).items() if k in names},
            "threshold": race.get("percentagePassDisplayMessage", ""),
        }

    reporting = {str(pid): {"category": v.get("category"),
                            "pct": _pct(v.get("percentReported", ""))}
                 for pid, v in feed.get("registrationAndTurnout", {}).items()}
    return mapped, meta, reporting


def reconcile(mapped, meta, pids=None):
    """Sum the precinct rows and compare with the feed's own countywide totals.

    Only meaningful over the WHOLE county: restrict `pids` to one city and the sums
    will differ from the countywide figure by design, so pass pids=None there and
    treat a city build's reconciliation as not applicable.
    """
    out = {}
    for n, pr in mapped.items():
        summed = {}
        for pid, ch in pr.items():
            if pids is not None and pid not in pids:
                continue
            for c, v in ch.items():
                summed[c] = summed.get(c, 0) + v
        want = meta[n].get("feed_totals", {})
        bad = {c: (summed.get(c, 0), want[c]) for c in want if summed.get(c, 0) != want[c]}
        out[n] = {"ok": not bad, "mismatches": bad}
    return out


if __name__ == "__main__":
    url = next((a.split("=", 1)[1] for a in sys.argv[1:] if a.startswith("--url=")), FEED_URL)
    feed = fetch(url)
    mapped, meta, reporting = parse(feed)
    print(f"{feed.get('electionName','?')} | last updated {feed.get('lastUpdatedDateTime','?')}")
    print(f"{len(reporting)} precincts, {len(mapped)} contest(s) mapped precinct by precinct:")
    rec = reconcile(mapped, meta)
    for n, pr in mapped.items():
        tot = meta[n]["feed_totals"]
        lead = max(tot, key=tot.get) if tot else "—"
        d = sum(tot.values()) or 1
        print(f"  {n[:60]:<60} {len(pr):>4} precincts  {lead[:24]:<24} "
              f"{100*tot.get(lead,0)/d:>5.1f}%  reconciles={rec[n]['ok']}")
