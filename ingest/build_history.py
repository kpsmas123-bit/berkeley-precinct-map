#!/usr/bin/env python3
"""
Build data/processed/history.json — comparable indicators for every election,
apportioned through the crosswalk onto today's precincts and today's council
districts, so they can be charted and differenced across elections.

Only genuinely comparable quantities are published. Candidate-level comparison
across years is mostly meaningless here (different candidates every cycle, RCV
first-choice only, redistricting), so the indicators are:

  turnout    ballots cast / registered voters. The one near-universal measure —
             available for every election except Nov 2018, whose canvass has no
             registration column.
  major_dem  Democratic share of the two-party vote in the top-of-ticket statewide
             race (President in a presidential year, Governor otherwise). Generals
             only. The nominees are named explicitly per election in TOP_OF_TICKET
             below rather than guessed, because the county only prefixes choices
             with "DEM - "/"REP - " in some years.
  local_yes  YES share across every "City of Berkeley" ballot measure on that
             ballot, pooled. A composite: it measures appetite for the local
             measures actually put to voters that year, NOT one consistent
             question, and it only exists for generals.

Each election also carries the crosswalk's quality numbers, so the frontend can say
how much of a figure is measured and how much is apportioned.

Usage: build_history.py
"""
import json
import os
import re

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PROC = os.path.join(ROOT, "data", "processed")
OUT = os.path.join(PROC, "history.json")

# Top-of-ticket statewide race per general, with the two major-party nominees named
# explicitly. Matching is on the choice string (case-insensitive substring).
TOP_OF_TICKET = {
    "2014-11-general": ("Governor",                   r"BROWN",   r"KASHKARI"),
    "2016-11-general": ("President and Vice President", r"CLINTON", r"TRUMP"),
    "2018-11-general": ("Governor",                   r"NEWSOM",  r"COX"),
    "2020-11-general": ("President and Vice President", r"BIDEN",   r"TRUMP"),
    "2022-11-general": ("Governor",                   r"NEWSOM",  r"DAHLE"),
    "2024-11-general": ("President and Vice President", r"HARRIS",  r"TRUMP"),
}

LOCAL_MEASURE = re.compile(r"(City of Berkeley|Berkeley USD)", re.I)
YES = re.compile(r"^(bonds\s+)?yes$", re.I)
NO = re.compile(r"^(bonds\s+)?no$", re.I)

INDICATORS = {
    "turnout": {
        "label": "Turnout",
        "help": ("Ballots cast as a share of registered voters. Available for every "
                 "election except November 2018, whose canvass has no registration column."),
    },
    "major_dem": {
        "label": "Democratic share (top of ticket)",
        "help": ("Democratic share of the two-party vote for President (presidential "
                 "years) or Governor (otherwise). General elections only; the two "
                 "nominees are named per election in the build script."),
    },
    "local_yes": {
        "label": "YES on Berkeley measures",
        "help": ("Pooled YES share across every City of Berkeley / Berkeley USD measure "
                 "on that ballot. A composite of whatever was on the ballot that year — "
                 "not one consistent question — and generals only."),
    },
}


def per_source_turnout(res):
    return {pid: (p.get("ballots_cast", 0), p.get("registered", 0))
            for pid, p in res["precincts"].items()}


def per_source_major_dem(res, eid):
    spec = TOP_OF_TICKET.get(eid)
    if not spec:
        return None
    contest, dem_rx, rep_rx = spec
    if contest not in res.get("contests", {}):
        return None
    drx, rrx = re.compile(dem_rx, re.I), re.compile(rep_rx, re.I)
    out = {}
    for pid, p in res["precincts"].items():
        c = p["contests"].get(contest)
        if not c:
            continue
        dem = sum(v for ch, v in c["choices"].items() if drx.search(ch))
        rep = sum(v for ch, v in c["choices"].items() if rrx.search(ch))
        out[pid] = (dem, dem + rep)
    return out or None


def per_source_local_yes(res):
    names = [n for n, meta in res.get("contests", {}).items()
             if meta.get("kind") == "measure" and LOCAL_MEASURE.search(n)]
    if not names:
        return None
    out = {}
    for pid, p in res["precincts"].items():
        y = n = 0
        for name in names:
            c = p["contests"].get(name)
            if not c:
                continue
            for ch, v in c["choices"].items():
                if YES.match(ch.strip()):
                    y += v
                elif NO.match(ch.strip()):
                    n += v
        if y + n:
            out[pid] = (y, y + n)
    return out or None


def apportion(per_source, weights):
    """num/den pairs on source precincts -> num/den pairs on base units."""
    num, den = {}, {}
    for spid, (n, d) in per_source.items():
        row = weights.get(spid)
        if not row or not d:
            continue
        for bpid, w in row:
            num[bpid] = num.get(bpid, 0.0) + n * w
            den[bpid] = den.get(bpid, 0.0) + d * w
    return {k: round(num[k] / den[k], 5) for k in den if den[k] > 0}


def main():
    manifest = json.load(open(os.path.join(PROC, "elections.json")))
    cw = json.load(open(os.path.join(PROC, "crosswalk.json")))

    out = {
        "base_election": cw["base_election"],
        "base_district_map": cw["base_district_map"],
        "base_precincts": cw["base_precincts"],
        "districts": cw["districts"],
        "crosswalk_method": cw["method"],
        "indicators": INDICATORS,
        "elections": [],
    }

    for e in sorted(manifest["elections"], key=lambda x: x["date"]):
        eid = e["id"]
        if eid not in cw["elections"]:
            continue
        res_path = os.path.join(PROC, e["results"])
        if not os.path.exists(res_path):
            continue
        res = json.load(open(res_path))
        if not res.get("precincts") or res.get("precinct_results") is False:
            continue   # nothing to measure yet

        cwe = cw["elections"][eid]
        pw, dw = cwe["weights"], cwe["district_weights"]

        sources = {
            "turnout": per_source_turnout(res),
            "major_dem": per_source_major_dem(res, eid),
            "local_yes": per_source_local_yes(res),
        }

        values = {}
        for key, per_src in sources.items():
            if not per_src:
                continue
            tn = sum(n for n, d in per_src.values() if d)
            td = sum(d for n, d in per_src.values() if d)
            if not td:
                continue
            values[key] = {
                "city": round(tn / td, 5),
                "districts": apportion(per_src, dw),
                "precincts": apportion(per_src, pw),
            }

        if not values:
            continue
        out["elections"].append({
            "id": eid,
            "date": e["date"],
            "name": e["name"],
            "kind": ("general" if "general" in eid else
                     "primary" if "primary" in eid else "special"),
            "quality": {
                "precinct": cwe["mean_exactness"],
                "district": cwe["mean_district_exactness"],
                "precinct_exactness": cwe["exactness"],
                "district_exactness": cwe["district_exactness"],
            },
            "values": values,
        })

    json.dump(out, open(OUT, "w"), separators=(",", ":"))
    kb = os.path.getsize(OUT) / 1024
    print(f"history: {len(out['elections'])} elections -> {OUT} ({kb:.0f} KB)")
    hdr = f"{'ELECTION':<18} {'TURNOUT':>8} {'DEM TOP':>8} {'YES LOCAL':>10}  {'DIST QUALITY':>12}"
    print(hdr); print("-" * len(hdr))
    for e in out["elections"]:
        v = e["values"]
        f = lambda k: (f"{100*v[k]['city']:.1f}%" if k in v else "—")
        print(f"{e['id']:<18} {f('turnout'):>8} {f('major_dem'):>8} {f('local_yes'):>10}"
              f"  {e['quality']['district']:>12}")


if __name__ == "__main__":
    main()
