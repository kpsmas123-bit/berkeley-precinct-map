#!/usr/bin/env python3
"""
Merge a registration file (ingest/fetch_registration.py) into a results file.

Kept separate from the parsers because registration comes from a different publisher
on a different schedule: re-running this never re-parses a canvass, and a results
file is perfectly usable without it.

Adds, per precinct that joined:
    "reg": {"totreg":…, "dem":…, "rep":…, "npp":…, "aip":…, "grn":…, "lib":…,
            "paf":…, "oth":…, "homes":"4/5"}
and a top-level "registration" block carrying the snapshot's provenance and coverage
— including how much of the electorate joined, which is the number that matters:
precinct counts understate it badly, because the precincts that fail to join are the
tiny ones.

Usage:
  attach_registration.py <results.json> <registration.json>
"""
import json
import os
import sys


def main():
    res_path, reg_path = sys.argv[1:3]
    if not os.path.exists(reg_path):
        print(f"  registration: {reg_path} missing — results left unchanged")
        return
    res = json.load(open(res_path))
    reg = json.load(open(reg_path))
    meta, rp = dict(reg.get("meta", {})), reg.get("precincts", {})

    joined = 0
    for pid, p in res.get("precincts", {}).items():
        r = rp.get(pid)
        if r:
            p["reg"] = r
            joined += 1
        else:
            p.pop("reg", None)

    reg_total = sum(rp[pid]["totreg"] for pid in rp if pid in res.get("precincts", {}))
    # the canvass's own registered total, where the election has one (0 before
    # certification), so coverage can be stated by voters rather than by precinct
    canvass_total = sum(p.get("registered", 0) or 0 for p in res.get("precincts", {}).values())
    county_total = ((res.get("turnout") or {}).get("county") or {}).get("registered", 0)
    denom = canvass_total or county_total or 0
    meta["coverage"] = dict(meta.get("coverage", {}))
    meta["coverage"]["precincts_joined_here"] = joined
    meta["coverage"]["registered_joined"] = reg_total
    if denom:
        meta["coverage"]["registered_total"] = denom
        meta["coverage"]["registered_pct"] = round(100.0 * reg_total / denom, 2)
    res["registration"] = meta
    json.dump(res, open(res_path, "w"), separators=(",", ":"))

    n = len(res.get("precincts", {}))
    pctbit = (f", {meta['coverage']['registered_pct']}% of registered voters"
              if denom else "")
    print(f"  registration attached: {joined}/{n} precincts{pctbit} "
          f"({meta.get('snapshot')} snapshot{' — FALLBACK' if meta.get('is_fallback') else ''})")


if __name__ == "__main__":
    main()
