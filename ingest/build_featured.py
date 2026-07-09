#!/usr/bin/env python3
"""
Rank contests across ALL elections by an insight score and write a hand-editable
featured.json (top ~10). The frontend pins each election's featured contests to the
top of the contest picker.

Insight score (0..1), objective starting point — the user overrides in featured.json:
  competitiveness  closer top-two / measure margin  (weight .40)
  D1 spread        stddev of the leading choice's share across the D1 precincts (.30)
  D1 relevance     D1 council > citywide Berkeley/Mayor > county/state proxy (.30)
  gate             x1 if consequential else x0.4; unverified contests excluded.

Requires results already annotated (annotate_contests.py). Writes featured.json only
if absent (hand-editable thereafter); always prints the ranked list with scores.

Usage: build_featured.py
"""
import json
import math
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PROC = os.path.join(ROOT, "data", "processed")
TOP_N = 10


def stddev(vals):
    if len(vals) < 2:
        return 0.0
    m = sum(vals) / len(vals)
    return math.sqrt(sum((x - m) ** 2 for x in vals) / len(vals))


def relevance(name):
    low = name.lower()
    if "city council" in low and ("dist. 1" in low or "district 1" in low):
        return 1.0
    if "berkeley" in low or low.startswith("mayor"):
        return 0.8
    if "proposition" in low or "supervisor" in low or "county" in low or "assembly" in low or "senator" in low:
        return 0.45
    return 0.55


def main():
    manifest = json.load(open(os.path.join(PROC, "elections.json")))["elections"]
    ranked = []
    for e in manifest:
        rp = os.path.join(PROC, e["results"])
        if not os.path.exists(rp):
            continue
        r = json.load(open(rp))
        P = r["precincts"]
        d1 = r.get("districts", {}).get("1", [])
        for name, meta in r["contests"].items():
            if meta.get("verified") is False:
                continue
            margin = meta.get("margin_pct")
            comp = max(0.0, (10.0 - margin) / 10.0) if margin is not None else 0.0
            # leading choice citywide, then its share spread across D1
            city = {}
            for p in P.values():
                c = p["contests"].get(name)
                if c:
                    for k, v in c["choices"].items():
                        city[k] = city.get(k, 0) + v
            if not city:
                continue
            lead = max(city, key=city.get)
            shares, denoms = [], []
            for pid in d1:
                c = P.get(pid, {}).get("contests", {}).get(name)
                if not c:
                    continue
                denom = c.get("cast", 0) if meta.get("multi") else sum(c["choices"].values())
                if denom > 0:
                    shares.append(c["choices"].get(lead, 0) / denom); denoms.append(denom)
            d1_ballots = sum(denoms)
            if d1_ballots < 300:          # too few D1 voters to be a story (minor-party noise)
                continue
            # EXCESS spread: dispersion beyond binomial sampling noise (else tiny contests
            # read as "high variance" purely from small n). Noise var = p(1-p)/mean_n.
            sd = stddev(shares)
            pbar = sum(shares) / len(shares)
            mean_n = d1_ballots / len(denoms)
            noise = math.sqrt(max(0.0, pbar * (1 - pbar) / max(mean_n, 1)))
            excess = math.sqrt(max(0.0, sd * sd - noise * noise))
            spread = min(1.0, excess / 0.12)
            rel = relevance(name)
            score = (comp * 0.40 + spread * 0.30 + rel * 0.30) * (1.0 if meta.get("consequential") else 0.40)
            ranked.append({"election": e["id"], "contest": name, "score": round(score, 3),
                           "margin_pct": margin, "multi": bool(meta.get("multi")),
                           "consequential": bool(meta.get("consequential")),
                           "why": f"comp={comp:.2f} spread={spread:.2f} rel={rel:.2f}"})

    ranked.sort(key=lambda x: -x["score"])
    top = ranked[:TOP_N]
    print("TOP FEATURED (auto-rank):")
    for t in top:
        print(f"  {t['score']:.3f}  {t['election']:16} {t['contest'][:46]:46} [{t['why']}]")

    fpath = os.path.join(PROC, "featured.json")
    if os.path.exists(fpath):
        print("featured.json exists — not overwriting (hand-editable).")
    else:
        json.dump({"_doc": "Hand-editable curation. Contests here are pinned to the top of "
                          "the contest picker (per election). Auto-ranked by competitiveness + "
                          "D1 within-district spread + D1 relevance, gated on consequential+verified. "
                          "Reorder / add / remove freely; delete this file to regenerate.",
                   "featured": [{"election": t["election"], "contest": t["contest"]} for t in top]},
                  open(fpath, "w"), indent=2)
        print(f"wrote featured.json ({len(top)})")


if __name__ == "__main__":
    main()
