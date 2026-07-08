#!/usr/bin/env python3
"""
Feature 3 plumbing (DATA STUB — no summaries are written here). Scan every
election's parsed results for ballot measures / propositions / recalls, compute the
jurisdiction-level final margin from the certified totals we have, and emit a slot
(summary: null) for the COMPETITIVE ones (margin < 10 pts, i.e. result ~45-55%).

We only hold Berkeley precinct data, so:
  - City of Berkeley / Berkeley USD measures: Berkeley IS the jurisdiction, and for
    reconciled (verified) elections the precinct sum equals the certified canvass —
    margin_basis "jurisdiction" (a true jurisdiction margin).
  - County / statewide / recall contests: we only have Berkeley's share, so the
    margin is a Berkeley-local proxy — margin_basis "berkeley_subset" (the true
    jurisdiction margin must be looked up externally; flagged in the todo queue).

Unverified contests (verified == false) are skipped — no margin claims on unreliable
totals. Existing summaries/source_urls in measures.json are preserved (merge).

Outputs (merged across all elections):
  data/processed/measures.json       competitive measures -> {summary, jurisdiction, ...}
  data/processed/measures_todo.json  the research queue (qualifying + unsummarized)

Usage: build_measures.py            (reads every election in the manifest)
"""
import json
import os
import re

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PROC = os.path.join(ROOT, "data", "processed")
COMPETITIVE_PCT = 10.0

IS_MEASURE = re.compile(r"\b(measure|proposition|prop\.?|bond|recall)\b", re.I)
NOT_MEASURE = re.compile(r"justice|judge|superior court", re.I)


def jurisdiction_of(name):
    low = name.lower()
    if "city of berkeley" in low:
        return "City of Berkeley", "jurisdiction"
    if re.search(r"berkeley\s+usd|berkeley\s+unified|busd", low):
        return "Berkeley USD", "jurisdiction"
    if "alameda county" in low:
        return "Alameda County", "berkeley_subset"
    if "proposition" in low or re.search(r"\bprop\.?\b", low):
        return "California (statewide)", "berkeley_subset"
    if "recall" in low:
        return "recall (jurisdiction varies)", "berkeley_subset"
    return "Berkeley (local)", "jurisdiction"


def yes_no(precincts, contest):
    yes = no = 0
    for p in precincts.values():
        c = p["contests"].get(contest)
        if not c:
            continue
        for k, v in c["choices"].items():
            ku = k.strip().upper()
            if ku == "YES":
                yes += v
            elif ku == "NO":
                no += v
    return yes, no


def main():
    manifest = json.load(open(os.path.join(PROC, "elections.json")))["elections"]
    mpath = os.path.join(PROC, "measures.json")
    existing = json.load(open(mpath)) if os.path.exists(mpath) else {}

    out = {}
    todo = []
    for e in manifest:
        eid = e["id"]
        rp = os.path.join(PROC, e["results"])
        if not os.path.exists(rp):
            continue
        results = json.load(open(rp))
        precincts = results["precincts"]
        for name, meta in results["contests"].items():
            if meta.get("kind") != "measure":
                continue
            if not IS_MEASURE.search(name) or NOT_MEASURE.search(name):
                continue
            if meta.get("verified") is False:          # honor verified: no claims on bad totals
                continue
            yes, no = yes_no(precincts, name)
            tot = yes + no
            if tot == 0:
                continue
            margin = 100.0 * abs(yes - no) / tot
            if margin >= COMPETITIVE_PCT:
                continue
            juris, basis = jurisdiction_of(name)
            prev = existing.get(eid, {}).get(name, {})
            out.setdefault(eid, {})[name] = {
                "jurisdiction": juris,
                "margin_basis": basis,
                "final_margin_pct": round(margin, 1),
                "yes_pct": round(100.0 * yes / tot, 1),
                "reconciled": results.get("qa") != "none" and meta.get("verified") is True,
                "summary": prev.get("summary"),
                "source_url": prev.get("source_url"),
            }
            if not out[eid][name]["summary"]:
                todo.append({"election": eid, "contest": name, "jurisdiction": juris,
                             "margin_basis": basis, "final_margin_pct": round(margin, 1),
                             "yes_pct": round(100.0 * yes / tot, 1)})

    json.dump(out, open(mpath, "w"), indent=2)
    todo.sort(key=lambda x: (x["margin_basis"] != "jurisdiction", x["final_margin_pct"]))
    json.dump({"note": "Competitive ballot measures (<10pt margin) still needing a "
                       "verified summary. 'berkeley_subset' margins are Berkeley-local "
                       "proxies — verify the true jurisdiction margin before summarizing.",
               "count": len(todo), "queue": todo},
              open(os.path.join(PROC, "measures_todo.json"), "w"), indent=2)

    n = sum(len(v) for v in out.values())
    print(f"measures: {n} competitive slots across {len(out)} elections; "
          f"{len(todo)} still need summaries -> measures.json, measures_todo.json")


if __name__ == "__main__":
    main()
