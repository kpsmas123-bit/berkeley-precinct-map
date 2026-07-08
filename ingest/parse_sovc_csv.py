#!/usr/bin/env python3
"""
Parse an Alameda County SOVC (Statement of Vote by Consolidation) CSV — the
precinct-level canvass format used for elections without an XLSX SOV (2018-2021) —
into the same normalized results schema as parse_canvass.py.

The CSV is long format: one row per precinct x contest x candidate, with total vote
columns. Column NAMES drift across years (e.g. 2020 "Precinct_name/candidate_name/
total_votes" vs 2018 "PRECINCT_NAME/CANDIDATE_FULL_NAME/..."), so columns are
auto-detected by fuzzy header matching.

Usage:
  parse_sovc_csv.py <sov.csv> <election_id> <out_results.json> <berkeley_ids.json>
"""
import csv
import json
import re
import sys


def as_int(v):
    if v is None:
        return 0
    s = str(v).strip().replace(",", "")
    if not s or s in ("-", "*"):
        return 0
    try:
        return int(round(float(s)))
    except ValueError:
        return 0


def find_col(header, *needles_groups):
    """Return index of the first header cell matching ALL needles in any group."""
    low = [h.strip().lower() for h in header]
    for group in needles_groups:
        for i, h in enumerate(low):
            if all(n in h for n in group):
                return i
    return None


def detect_votes(header):
    """The candidate vote-COUNT column. Avoid 'vote-for-N' fields
    (contest_vote_for, VOTES_ALLOWED) that also contain 'vote'."""
    low = [h.strip().lower() for h in header]
    for want in ("total_votes", "vote_count", "votes", "total_vote"):  # exact names, in priority
        if want in low:
            return low.index(want)
    if "total" in low:               # 2018 uses a bare "TOTAL" column for the count
        return low.index("total")
    bad = ("for", "allowed", "order", "seq", "flag", "type", "writein",
           "processed", "party", "ballot", "cast", "reg", "under", "over",
           "turn", "split", "reporting", "option", "selectable", "update")
    for i, h in enumerate(low):
        if ("vote" in h or "count" in h) and not any(b in h for b in bad):
            return i
    return None


def detect_columns(header):
    c = {}
    c["prec"] = find_col(header, ["precinct", "name"], ["precinct"], ["pct", "name"])
    c["contest"] = find_col(header, ["contest", "title"], ["contest", "full"], ["contest", "name"], ["contest"])
    c["cand"] = find_col(header, ["candidate", "full"], ["candidate", "name"], ["candidate"], ["choice"])
    c["votes"] = detect_votes(header)
    c["reg"] = find_col(header, ["reg", "voter"], ["registered"])
    c["under"] = find_col(header, ["under", "vote"], ["under"])
    c["over"] = find_col(header, ["over", "vote"], ["over"])
    c["ballots"] = find_col(header, ["total", "ballot"], ["ballots", "cast"], ["ballot", "cast"], ["ballot"])
    return c


def main():
    csv_path, election_id, out_path, ids_path = sys.argv[1:5]
    berkeley = set(json.load(open(ids_path)))

    with open(csv_path, newline="", encoding="utf-8-sig", errors="replace") as f:
        reader = csv.reader(f)
        header = next(reader)
        c = detect_columns(header)
        if c["prec"] is None or c["contest"] is None or c["cand"] is None or c["votes"] is None:
            print(f"ERROR: could not detect required columns: {c}\n header={header}", file=sys.stderr)
            sys.exit(1)

        precincts = {}
        catalog = {}
        maxcol = max(x for x in c.values() if x is not None)
        for row in reader:
            if len(row) <= maxcol:
                continue
            pid = str(row[c["prec"]]).strip()
            if pid not in berkeley:
                continue
            contest = str(row[c["contest"]]).strip()
            cand = str(row[c["cand"]]).strip()
            if not contest or not cand:
                continue
            rcv = "(RCV)" in contest
            name = re.sub(r"\s*\(RCV\)\s*$", "", contest).strip()
            votes = as_int(row[c["votes"]])

            p = precincts.setdefault(pid, {"registered": 0, "ballots_cast": 0, "contests": {}})
            if c["reg"] is not None:
                p["registered"] = max(p["registered"], as_int(row[c["reg"]]))
            entry = p["contests"].setdefault(name, {"choices": {}, "cast": 0})
            entry["choices"][cand] = max(entry["choices"].get(cand, 0), votes)
            if c["ballots"] is not None:
                entry["cast"] = max(entry["cast"], as_int(row[c["ballots"]]))
            if c["under"] is not None:
                entry["under"] = max(entry.get("under", 0), as_int(row[c["under"]]))
            if c["over"] is not None:
                entry["over"] = max(entry.get("over", 0), as_int(row[c["over"]]))
            p["ballots_cast"] = max(p["ballots_cast"], entry["cast"])

            cat = catalog.setdefault(name, {"rcv": rcv, "kind": None, "choices": []})
            if cand not in cat["choices"]:
                cat["choices"].append(cand)

    # classify measure vs candidate; drop empty over/under
    for name, cat in catalog.items():
        cat["kind"] = "measure" if any(ch.upper() in ("YES", "NO") for ch in cat["choices"]) else "candidate"
    for p in precincts.values():
        for e in p["contests"].values():
            if not e.get("over") and not e.get("under"):
                e.pop("over", None); e.pop("under", None)

    out = {"election_id": election_id, "berkeley_precincts": sorted(berkeley),
           "contests": catalog, "precincts": precincts}
    json.dump(out, open(out_path, "w"), separators=(",", ":"))
    print(f"parsed CSV; {len(precincts)} Berkeley precincts; {len(catalog)} contests -> {out_path}")


if __name__ == "__main__":
    main()
