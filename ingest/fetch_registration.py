#!/usr/bin/env python3
"""
Precinct-level VOTER PARTY REGISTRATION, joined onto an election's consolidated
precincts.

Why this exists
---------------
Nothing the county publishes with results carries party. The Statement of Vote, the
live results feed and the Cast Vote Record all give one undifferentiated "registered
voters" count — the CVR does not even give that. Without party there is no way to ask
the question worth asking: not "where did this candidate do well" (that is mostly a
map of where Democrats live) but "where did this candidate do better or worse than
the precinct's registration says they should".

Two public sources, joined here:

1. The **California Statewide Database** (UC Berkeley), the only source publishing
   registration by party at precinct level — the Secretary of State's Report of
   Registration stops at county and district, and the county's own eData is
   countywide.
     https://statewidedatabase.org/pub/data/<CODE>/c001/c001_<code>_registration_by_<code>_rgprec.csv
   Columns: totreg_r, dem, rep, aip, paf, msc, lib, nlp, grn, ref, dcl.
   "dcl" is Declined to State, today's No Party Preference.

2. The county's own **results-map feed**, whose `homePrecincts` lists the registration
   precincts consolidated into each voting precinct. Past elections have their own
   feed file, so the mapping is per-election rather than assumed.

The join is exact, not geometric: SWDB's `rgprec` is the county's 6-digit registration
precinct id plus a 2-digit split suffix (20010000 -> 200100 + 00), so stripping the
suffix gives a home precinct, and `homePrecincts` gives the consolidated precinct it
belongs to. No area-overlap estimation anywhere.

Honesty constraints
-------------------
* The SWDB file is a snapshot taken for one election. Where the matching one does not
  exist yet (G26 at the time of writing), the nearest earlier snapshot is used and
  `meta.as_of` / `meta.is_fallback` say so — registration drifts, so a Nov-2026 map
  carrying June-2026 registration must admit it.
* Precincts are renumbered between elections, so the join never covers everything.
  `meta.coverage` records exactly how much matched, and precincts with no match are
  absent rather than zero-filled.

Usage:
  fetch_registration.py <election_id> <out.json> [--swdb=CODE] [--no-cache]
"""
import csv
import json
import os
import re
import sys
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MANIFEST = os.path.join(ROOT, "data", "processed", "elections.json")
CACHE = os.path.join(ROOT, "data", "raw", "registration")
UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124.0 Safari/537.36")

SWDB = "https://statewidedatabase.org/pub/data/{C}/c001/c001_{c}_registration_by_{c}_rgprec.csv"
LIVE_FEED = "https://electionmaps.alamedacountyca.gov/json/electionResults.json"
PAST_INDEX = "https://electionmaps.alamedacountyca.gov/json/pastelections/pastElections.json"
PAST_FILE = "https://electionmaps.alamedacountyca.gov/json/pastelections/{f}"

# Every SWDB snapshot that exists for Alameda, oldest first. A general election is
# G<yy>, a primary P<yy>, an odd-year statewide special S<yy>. Probed, not assumed.
SNAPSHOTS = [("2014-06-03", "P14"), ("2014-11-04", "G14"),
             ("2016-06-07", "P16"), ("2016-11-08", "G16"),
             ("2018-06-05", "P18"), ("2018-11-06", "G18"),
             ("2020-03-03", "P20"), ("2020-11-03", "G20"),
             ("2021-09-14", "S21"),
             ("2022-06-07", "P22"), ("2022-11-08", "G22"),
             ("2024-03-05", "P24"), ("2024-11-05", "G24"),
             ("2025-11-04", "S25"),
             ("2026-06-02", "P26")]

PARTY_COLS = ["dem", "rep", "aip", "paf", "msc", "lib", "nlp", "grn", "ref", "dcl"]
# what the map actually shows; the long tail is folded into "oth"
OUT_KEYS = ["dem", "rep", "npp", "aip", "grn", "lib", "paf", "oth"]


def fetch_text(url, cache_name=None, use_cache=True):
    path = os.path.join(CACHE, cache_name) if cache_name else None
    if path and use_cache and os.path.exists(path):
        return open(path, encoding="utf-8", errors="replace").read()
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=180) as r:
        text = r.read().decode("utf-8", "replace")
    if path:
        os.makedirs(CACHE, exist_ok=True)
        open(path, "w", encoding="utf-8").write(text)
    return text


def pick_snapshot(date, override=None):
    """The snapshot for this election, or the nearest earlier one."""
    if override:
        return override, True, False
    exact = next((c for d, c in SNAPSHOTS if d == date), None)
    if exact:
        return exact, True, False
    earlier = [(d, c) for d, c in SNAPSHOTS if d <= date]
    if not earlier:
        return None, False, False
    return earlier[-1][1], False, True


MONTHS = ["january", "february", "march", "april", "may", "june", "july",
          "august", "september", "october", "november", "december"]


def feed_date(feed):
    """The election date a feed is for, from its own electionName."""
    m = re.search(r"([A-Za-z]+)\s+(\d{1,2}),\s*(\d{4})", str(feed.get("electionName", "")))
    if not m or m.group(1).lower() not in MONTHS:
        return None
    return f"{m.group(3)}-{MONTHS.index(m.group(1).lower())+1:02d}-{int(m.group(2)):02d}"


def home_precinct_map(eid, date, use_cache=True):
    """consolidated precinct -> [registration precinct ids], from the county's feed.

    The mapping is per-election and precincts are reconsolidated every time, so a
    feed for the WRONG election is worse than none: it silently joins registration
    onto precincts that did not exist. The county's archive starts in 2016, so 2014
    has no mapping and is skipped rather than guessed — an earlier version fell back
    to the current election's feed here and "joined" 25 of 2014's 103 precincts.
    """
    cache = f"map_{eid}.json"
    path = os.path.join(CACHE, cache)
    if use_cache and os.path.exists(path):
        return json.load(open(path)), "cached"

    index = json.loads(fetch_text(PAST_INDEX, "pastElections.json", use_cache))
    fn = next((e["fileName"] for e in index
               if str(e.get("fileName", "")).startswith(date)), None)
    if fn:
        feed = json.loads(fetch_text(PAST_FILE.format(f=fn), None, False))
        src = fn
    else:
        # not in the archive: only the current election's live feed can be right,
        # and only if it is actually for this election
        feed = json.loads(fetch_text(LIVE_FEED, None, False))
        if feed_date(feed) != date:
            return {}, f"no feed for {date}"
        src = "current feed"
    m = {str(pid): [str(h) for h in v.get("homePrecincts", [])]
         for pid, v in feed.get("registrationAndTurnout", {}).items()}
    if m:
        os.makedirs(CACHE, exist_ok=True)
        json.dump(m, open(path, "w"))
    return m, src


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    opt = {a.split("=", 1)[0].lstrip("-"): (a.split("=", 1)[1] if "=" in a else True)
           for a in sys.argv[1:] if a.startswith("--")}
    if len(args) < 2:
        print(__doc__.strip().splitlines()[-1], file=sys.stderr)
        sys.exit(2)
    eid, out_path = args[:2]
    use_cache = not opt.get("no-cache")

    entry = next((e for e in json.load(open(MANIFEST))["elections"] if e["id"] == eid), None)
    if entry is None:
        print(f"ERROR: {eid} is not in the manifest", file=sys.stderr)
        sys.exit(1)
    date = entry["date"]

    code, exact, fallback = pick_snapshot(date, opt.get("swdb"))
    if not code:
        print(f"  registration: no Statewide Database snapshot at or before {date} — skipped")
        sys.exit(0)
    as_of = next(d for d, c in SNAPSHOTS if c == code) if not opt.get("swdb") \
        else next((d for d, c in SNAPSHOTS if c == code), date)

    try:
        text = fetch_text(SWDB.format(C=code, c=code.lower()), f"{code}.csv", use_cache)
    except Exception as e:
        print(f"  registration: could not fetch {code} ({e}) — skipped")
        sys.exit(0)

    byhome = {}
    for r in csv.DictReader(text.splitlines()):
        h = re.sub(r"\D", "", str(r.get("rgprec", "")))[:6]
        if len(h) < 6:
            continue
        d = byhome.setdefault(h, {k: 0 for k in PARTY_COLS} | {"totreg": 0})
        d["totreg"] += int(r.get("totreg_r") or 0)
        for p in PARTY_COLS:
            d[p] += int(r.get(p) or 0)

    hmap, map_src = home_precinct_map(eid, date, use_cache)
    if not hmap:
        print(f"  registration: no precinct mapping published for {date} "
              f"({map_src}) — skipped, rather than joined onto another election's "
              f"precincts")
        sys.exit(0)

    precincts, matched, total_h = {}, 0, 0
    for pid, homes in hmap.items():
        agg = {k: 0 for k in PARTY_COLS} | {"totreg": 0}
        hit = 0
        for h in homes:
            total_h += 1
            if h in byhome:
                hit += 1
                matched += 1
                for k in agg:
                    agg[k] += byhome[h][k]
        if not hit or not agg["totreg"]:
            continue
        precincts[pid] = {
            "totreg": agg["totreg"],
            "dem": agg["dem"], "rep": agg["rep"], "npp": agg["dcl"],
            "aip": agg["aip"], "grn": agg["grn"], "lib": agg["lib"], "paf": agg["paf"],
            "oth": agg["msc"] + agg["nlp"] + agg["ref"],
            "homes": f"{hit}/{len(homes)}",
        }

    totals = {k: sum(p[k] for p in precincts.values()) for k in OUT_KEYS + ["totreg"]}
    out = {
        "election_id": eid,
        "meta": {
            "source": "California Statewide Database (UC Berkeley)",
            "source_url": SWDB.format(C=code, c=code.lower()),
            "snapshot": code,
            "as_of": as_of,
            "is_fallback": bool(fallback),
            "election_date": date,
            "precinct_map_source": map_src,
            "join": ("SWDB rgprec = county registration precinct + 2-digit split; "
                     "rolled up to consolidated precincts via the county feed's "
                     "homePrecincts. Exact id join, no geometric estimation."),
            "coverage": {
                "registration_precincts_matched": matched,
                "registration_precincts_total": total_h,
                "precincts_with_registration": len(precincts),
                "precincts_total": len(hmap),
            },
            "totals": totals,
            "npp_note": "npp = SWDB 'dcl' (Declined to State), today's No Party Preference",
        },
        "precincts": precincts,
    }
    os.makedirs(os.path.dirname(os.path.abspath(out_path)), exist_ok=True)
    json.dump(out, open(out_path, "w"), separators=(",", ":"))

    t = totals["totreg"] or 1
    warn = "  ⚠ FALLBACK" if fallback else ""
    print(f"  registration: {code} snapshot ({as_of}){warn} -> {out_path}")
    print(f"    {len(precincts)}/{len(hmap)} precincts joined "
          f"({matched}/{total_h} registration precincts matched)")
    print(f"    {totals['totreg']:,} registered — "
          + "  ".join(f"{k.upper()} {100*totals[k]/t:.1f}%" for k in ("dem", "rep", "npp")))
    if fallback:
        print(f"    no Statewide Database snapshot for {date} yet; using the {as_of} one")


if __name__ == "__main__":
    main()
