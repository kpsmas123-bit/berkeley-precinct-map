#!/usr/bin/env python3
"""
Feature 2 seed. Creates data/processed/alignment.json with a NEUTRAL, mechanical
default: each ballot measure's YES = 5, NO = 1 (a "supported the measure as written"
axis). Everything else (candidates, judicial retention, party contests) is left
UNSCORED so the user assigns scores deliberately via the in-browser editor.

This is a starting point, not an editorial judgement — flip/adjust any score in the
editor and export. Runs only if alignment.json is absent, so it never clobbers edits.
NOT wired into build.sh (alignment.json is user-owned).

Usage: build_alignment_seed.py
"""
import json
import os
import re

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PROC = os.path.join(ROOT, "data", "processed")
IS_MEASURE = re.compile(r"\b(measure|proposition|prop\.?|bond)\b", re.I)
NOT_MEASURE = re.compile(r"justice|judge|superior court", re.I)


def main():
    out_path = os.path.join(PROC, "alignment.json")
    if os.path.exists(out_path):
        print("alignment.json already exists — not overwriting (user-owned).")
        return
    manifest = json.load(open(os.path.join(PROC, "elections.json")))["elections"]
    out = {"_doc": "election_id -> contest -> choice -> Likert score 1..5 "
                   "(1 oppose, 3 neutral, 5 support). Missing choice = unscored "
                   "(excluded from the composite). Seeded default: ballot-measure "
                   "YES=5, NO=1 — edit freely in the in-browser editor and export."}
    seeded = 0
    for e in manifest:
        rp = os.path.join(PROC, e["results"])
        if not os.path.exists(rp):
            continue
        results = json.load(open(rp))
        for name, meta in results["contests"].items():
            if meta.get("kind") != "measure" or not IS_MEASURE.search(name) or NOT_MEASURE.search(name):
                continue
            scores = {}
            for ch in meta["choices"]:
                if ch.strip().upper() == "YES":
                    scores[ch] = 5
                elif ch.strip().upper() == "NO":
                    scores[ch] = 1
            if scores:
                out.setdefault(e["id"], {})[name] = scores
                seeded += 1
    json.dump(out, open(out_path, "w"), indent=2)
    print(f"seeded alignment.json: {seeded} ballot-measure contests scored (YES=5/NO=1) -> {out_path}")


if __name__ == "__main__":
    main()
