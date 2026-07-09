#!/usr/bin/env python3
"""
Annotate a parsed results file's contest catalog with:
  multi (bool)        at-large / vote-for-N contest (votes-per-ballot > 1.3, or a
                      captured "vote for N" > 1). Significance must use ballots, not
                      total votes, for these (see the frontend).
  seats (int|null)    seat count when the source exposed it; null if only inferred.
  margin_pct (float)  the decisive margin — top-two for candidate races (ballot-share
                      for multi-seat, vote-share otherwise), |YES-NO| for measures.
  consequential (bool) verified AND margin < 10 pts (city/school measures only for the
                      measure gate; county/state measures are "margin pending").
  reason (str)        human explanation for the tooltip.

Unverified contests (verified == false) are never consequential.

Usage: annotate_contests.py <results.json>
"""
import json
import sys

from build_measures import IS_MEASURE, NOT_MEASURE, jurisdiction_of

MULTI_RATIO = 1.3
CONSEQUENTIAL_PCT = 10.0


def main():
    path = sys.argv[1]
    r = json.load(open(path))
    P, cat = r["precincts"], r["contests"]
    for name, meta in cat.items():
        agg, cast = {}, 0
        for p in P.values():
            c = p["contests"].get(name)
            if not c:
                continue
            for k, v in c["choices"].items():
                agg[k] = agg.get(k, 0) + v
            cast += c.get("cast", 0)
        tv = sum(agg.values())
        ratio = tv / cast if cast else None
        src_seats = meta.get("seats")
        multi = bool((src_seats and src_seats > 1) or (ratio and ratio > MULTI_RATIO))
        meta["multi"] = multi
        meta["seats"] = src_seats if (src_seats and src_seats > 1) else None

        margin = None; conseq = False; reason = None
        is_measure = meta.get("kind") == "measure" and IS_MEASURE.search(name) and not NOT_MEASURE.search(name)
        if meta.get("verified") is False:
            reason = "unverified"
        elif is_measure:
            yes = sum(v for k, v in agg.items() if k.strip().upper() == "YES")
            no = sum(v for k, v in agg.items() if k.strip().upper() == "NO")
            if yes + no > 0:
                margin = 100.0 * abs(yes - no) / (yes + no)
                juris, basis = jurisdiction_of(name)
                if basis == "jurisdiction":
                    conseq = margin < CONSEQUENTIAL_PCT
                    reason = f"{juris} margin {margin:.1f} pts"
                else:
                    reason = f"margin pending ({juris})"
        else:
            entries = sorted(((k, v) for k, v in agg.items() if not k.startswith("_")), key=lambda kv: -kv[1])
            if len(entries) >= 2:
                v1, v2 = entries[0][1], entries[1][1]
                if multi and cast > 0:
                    margin = 100.0 * (v1 - v2) / cast
                elif tv > 0:
                    margin = 100.0 * (v1 - v2) / tv
                if margin is not None:
                    conseq = margin < CONSEQUENTIAL_PCT
                    reason = f"top-two margin {margin:.1f} pts" + (" · multi-seat" if multi else "")
            elif len(entries) == 1:
                reason = "uncontested"
            elif multi and not cast:
                reason = "ballots not published"

        meta["margin_pct"] = round(margin, 1) if margin is not None else None
        meta["consequential"] = bool(conseq)
        meta["reason"] = reason

    json.dump(r, open(path, "w"), separators=(",", ":"))
    nm = sum(1 for m in cat.values() if m.get("multi"))
    nc = sum(1 for m in cat.values() if m.get("consequential"))
    print(f"annotated {len(cat)} contests: {nm} multi-seat, {nc} consequential")


if __name__ == "__main__":
    main()
