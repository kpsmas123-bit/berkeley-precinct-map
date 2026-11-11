#!/usr/bin/env python3
"""
Split a county results file into a summary plus one file per contest.

Why this exists
---------------
The map shows ONE contest at a time but was downloading all of them. For the Nov
2026 county file that is 110 KB gzipped to render a single choropleth; the summary
plus one contest is 25 KB. Nothing is discarded — the bytes just arrive when they
are needed.

It works because every read in county.html is `precinct.contests[state.contest]`:
nothing iterates a precinct's other contests, so the rest can stay on the server.
The countywide and per-city rollups the panel needs are already precomputed, so they
travel in the summary and the ranked jurisdiction list still renders before any
contest file arrives.

Layout written:
  <outdir>/summary.json        everything except per-precinct tallies, plus
                               contest_files: {contest name -> "c/<slug>.json"}
  <outdir>/c/<slug>.json       {"contest": name, "precincts": {pid: {choices,…}}}
  <outdir>/registration.json   per-precinct party registration, which only the two
                               registration modes need — more than half the
                               summary's weight, for a view most visits never open

Slugs match the frontend's slug() exactly, so a contest's file is predictable from
its permalink. Collisions get a numeric suffix rather than silently overwriting.

Usage:
  split_results.py <results.json> <outdir>
"""
import json
import os
import re
import shutil
import sys


def slug(s):
    return re.sub(r"(^-|-$)", "", re.sub(r"[^a-z0-9]+", "-", str(s).lower()))


def main():
    res_path, outdir = sys.argv[1:3]
    r = json.load(open(res_path))

    names = list(r.get("contests", {}).keys())
    files, seen = {}, {}
    for n in names:
        base = slug(n) or "contest"
        if base in seen:
            seen[base] += 1
            base = f"{base}-{seen[base]}"
        else:
            seen[base] = 1
        files[n] = f"c/{base}.json"

    # per-contest payloads
    per = {n: {} for n in names}
    for pid, p in r.get("precincts", {}).items():
        for n, e in (p.get("contests") or {}).items():
            if n in per:
                per[n][pid] = e

    cdir = os.path.join(outdir, "c")
    if os.path.isdir(outdir):
        shutil.rmtree(outdir)
    os.makedirs(cdir, exist_ok=True)

    sizes = {}
    for n in names:
        path = os.path.join(outdir, files[n])
        json.dump({"contest": n, "precincts": per[n]}, open(path, "w"),
                  separators=(",", ":"))
        sizes[n] = os.path.getsize(path)

    # summary: the same object with per-precinct tallies lifted out
    summary = {k: v for k, v in r.items() if k != "precincts"}
    summary["precincts"] = {
        pid: {k: v for k, v in p.items() if k not in ("contests", "reg")}
        for pid, p in r.get("precincts", {}).items()
    }
    summary["contest_files"] = files
    summary["split"] = True

    reg = {pid: p["reg"] for pid, p in r.get("precincts", {}).items() if p.get("reg")}
    if reg:
        json.dump({"precincts": reg}, open(os.path.join(outdir, "registration.json"), "w"),
                  separators=(",", ":"))
        summary["registration_file"] = "registration.json"
    spath = os.path.join(outdir, "summary.json")
    json.dump(summary, open(spath, "w"), separators=(",", ":"))

    whole = os.path.getsize(res_path)
    s = os.path.getsize(spath)
    biggest = max(sizes.values()) if sizes else 0
    print(f"  split {len(names)} contests -> {outdir}")
    rpath = os.path.join(outdir, "registration.json")
    rsz = os.path.getsize(rpath) if os.path.exists(rpath) else 0
    print(f"    was {whole/1024:,.0f} KB in one file; now {s/1024:,.0f} KB summary "
          f"+ {biggest/1024:,.0f} KB for the largest contest "
          f"({(s+biggest)/whole*100:.0f}% of the old payload to draw one map)"
          + (f"; registration split off into {rsz/1024:,.0f} KB" if rsz else ""))


if __name__ == "__main__":
    main()
