#!/usr/bin/env python3
"""
Feature 3 plumbing (DATA STUB — no summaries or thresholds are written here). Scan
every election's parsed results for ballot measures / propositions / recalls and emit
a slot in measures.json.

Scope (Fix 3):
  - EVERY LOCAL measure (City of Berkeley / Berkeley USD / Berkeley-specific district)
    gets a slot regardless of margin — the user wants a description for each.
  - County / statewide / recall contests get a slot only when COMPETITIVE (margin
    < 10 pts) and are flagged margin_basis "berkeley_subset" (Berkeley-local proxy;
    the true jurisdiction margin must be pulled externally).

`competitive` (margin < 10 pts, jurisdiction basis) is stored as a SEPARATE flag for
the star/featured logic — it no longer gates whether a description slot exists.

Pass/fail (Fix 4): `pass_threshold` (majority | 55 | two_thirds | null) and
`threshold_note` are RESEARCHED per measure and must NOT be inferred from the name —
left null here. yes_pct is stored so the frontend can compute pass/fail once a
threshold is supplied.

Unverified contests are skipped. Existing summary / source_url / pass_threshold /
threshold_note in measures.json are preserved (merge).

Outputs (merged across all elections):
  data/processed/measures.json       election -> contest -> {summary, jurisdiction, ...}
  data/processed/measures_todo.json  research queue (local measures missing summary or threshold)

Usage: build_measures.py
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
    # regional / special districts (AC Transit, EBMUD, BART, East Bay Regional Park,
    # SF Bay Restoration, Peralta/Chabot CCD, ...) span many cities — Berkeley is a
    # subset, not the jurisdiction.
    return "regional / other district", "berkeley_subset"


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
    rpath = os.path.join(PROC, "measure_research.json")   # curated summaries + thresholds
    research = json.load(open(rpath)) if os.path.exists(rpath) else {}

    out, todo = {}, []
    for e in manifest:
        eid = e["id"]
        rp = os.path.join(PROC, e["results"])
        if not os.path.exists(rp):
            continue
        results = json.load(open(rp))
        precincts = results["precincts"]
        for name, meta in results["contests"].items():
            if meta.get("kind") != "measure" or not IS_MEASURE.search(name) or NOT_MEASURE.search(name):
                continue
            if meta.get("verified") is False:
                continue
            yes, no = yes_no(precincts, name)
            tot = yes + no
            if tot == 0:
                continue
            margin = 100.0 * abs(yes - no) / tot
            yes_pct = 100.0 * yes / tot
            juris, basis = jurisdiction_of(name)
            local = basis == "jurisdiction"
            competitive = margin < COMPETITIVE_PCT
            if not (local or competitive):        # county/state only when competitive
                continue
            prev = existing.get(eid, {}).get(name, {})
            r = research.get(eid, {}).get(name, {})   # curated research overrides placeholders
            out.setdefault(eid, {})[name] = {
                "jurisdiction": juris,
                "margin_basis": basis,
                "local": local,
                "competitive": bool(competitive),
                "final_margin_pct": round(margin, 1),
                "yes_pct": round(yes_pct, 1),
                "reconciled": results.get("qa") != "none" and meta.get("verified") is True,
                "summary": r.get("summary") or prev.get("summary"),
                "source_url": r.get("source_url") or prev.get("source_url"),
                "pass_threshold": r.get("pass_threshold") or prev.get("pass_threshold"),   # majority | 55 | two_thirds | null
                "threshold_note": r.get("threshold_note") or prev.get("threshold_note"),
            }
            if local and (not out[eid][name]["summary"] or not out[eid][name]["pass_threshold"]):
                todo.append({"election": eid, "contest": name, "jurisdiction": juris,
                             "yes_share": round(yes_pct, 1), "margin": round(margin, 1),
                             "summary": out[eid][name]["summary"],
                             "pass_threshold": out[eid][name]["pass_threshold"]})

    json.dump(out, open(mpath, "w"), indent=2)
    todo.sort(key=lambda x: (x["election"], x["contest"]))
    json.dump({"note": "Research queue: every LOCAL Berkeley measure still missing a "
                       "summary and/or a pass_threshold. pass_threshold is one of "
                       "majority | 55 | two_thirds and MUST be read from the measure text "
                       "(general vs special tax), not guessed. Fill summary + pass_threshold "
                       "in measures.json; rebuild preserves them.",
               "count": len(todo), "queue": todo},
              open(os.path.join(PROC, "measures_todo.json"), "w"), indent=2)

    n = sum(len(v) for v in out.values())
    nl = sum(1 for v in out.values() for m in v.values() if m["local"])
    print(f"measures: {n} slots ({nl} local, {n - nl} competitive county/state) across "
          f"{len(out)} elections; {len(todo)} local measures need summary/threshold")


if __name__ == "__main__":
    main()
