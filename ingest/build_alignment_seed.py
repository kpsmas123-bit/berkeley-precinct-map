#!/usr/bin/env python3
"""
Feature 2 init. Creates an EMPTY data/processed/alignment.json (just the _doc note)
if it is absent. There is deliberately NO mechanical seed — auto-generated scores
(e.g. YES=5/NO=1) produce fake signal, so alignment scores are human-authored only,
via the in-browser editor (export) or by hand. Never overwrites an existing file.

Usage: build_alignment_seed.py
"""
import json
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PROC = os.path.join(ROOT, "data", "processed")
DOC = ("election_id -> contest -> choice -> Likert score 1..5 (1 oppose, 3 neutral, "
       "5 support). Human-authored ONLY — there is no mechanical seed. A contest counts "
       "as 'scored' only if a real value appears here (added via the in-browser editor "
       "and exported, or committed by hand). Alignment map mode is hidden for an election "
       "until at least one of its contests is scored.")


def main():
    path = os.path.join(PROC, "alignment.json")
    if os.path.exists(path):
        print("alignment.json already exists — not overwriting (user-owned).")
        return
    json.dump({"_doc": DOC}, open(path, "w"), indent=2)
    print("initialized empty alignment.json (no seed — scores are human-authored)")


if __name__ == "__main__":
    main()
