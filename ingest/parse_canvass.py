#!/usr/bin/env python3
"""
Parse an Alameda County ROV "Statement of Vote" (SOV) precinct canvass workbook
into the normalized results schema, filtered to Berkeley precincts.

Format notes (Nov 2024 SOV adapter):
  - Workbook has a "Document map" TOC sheet plus one sheet per contest.
  - Each contest sheet:
      row 4 (0-based): contest title in a cell, prefixed with a hyperlink number "1 ".
      row 5: header row. Cols: A/B unlabeled (precinct id / vote type),
             C="Registered Voters", D="Voters Cast", E="Turnout (%)",
             then candidate/choice columns (with blank spacer columns between some).
             Measures also carry "Over Votes" / "Under Votes" choice columns.
      row 6+: data rows. Col A = consolidated precinct id (digits), col B = vote type
             ("Election Day", "Vote by Mail", "Youth Voting ...", "Total").
             We keep only the per-precinct "Total" row.

Berkeley filter:
  The Berkeley precinct-id set is supplied by build_geo.py (selected spatially, so
  it works even for primaries with no Berkeley-specific contest). Every contest is
  kept only for those precincts, which yields exactly the contests on a Berkeley ballot.

Usage:
  parse_canvass.py <sov.xlsx> <election_id> <out_results.json> <berkeley_ids.json>
"""
import json
import re
import sys
import warnings

import openpyxl

warnings.filterwarnings("ignore")

LABEL_COLS = {"registered voters", "voters cast", "turnout (%)"}
NOVOTE_CHOICES = {"over votes", "under votes"}
NUM_PREFIX = re.compile(r"^\s*\d+\s+")  # strips the "1 " hyperlink prefix


def clean_contest_name(raw: str) -> str:
    name = NUM_PREFIX.sub("", str(raw)).strip()
    return name


def is_rcv(name: str) -> bool:
    return "(RCV)" in name


def display_name(name: str) -> str:
    # keep the human contest name but drop the "(RCV)" marker (tracked in meta)
    return re.sub(r"\s*\(RCV\)\s*$", "", name).strip()


def as_int(v):
    if v is None or v == "":
        return 0
    if isinstance(v, (int, float)):
        return int(round(v))
    s = str(v).strip().replace(",", "")
    if s in ("", "-", "*"):
        return 0
    try:
        return int(round(float(s)))
    except ValueError:
        return 0


def parse_contest_sheet(ws):
    """Return (contest_name, rcv, choice_cols, novote_cols, rows) or None."""
    rows = list(ws.iter_rows(values_only=True))
    if len(rows) < 7:
        return None

    # locate the contest title row (first cell containing the numbered prefix in cols A-E)
    title = None
    header_idx = None
    for i, row in enumerate(rows[:10]):
        for c in row[:6]:
            if c and NUM_PREFIX.match(str(c)) and "Registered Voters" not in str(c):
                title = clean_contest_name(c)
                break
        if title is not None:
            header_idx = i + 1
            break
    if title is None or header_idx is None:
        return None

    header = rows[header_idx]
    choice_cols, novote_cols = {}, {}
    for ci, h in enumerate(header):
        if ci < 5 or h is None or str(h).strip() == "":
            continue
        label = str(h).strip()
        low = label.lower()
        if low in LABEL_COLS:
            continue
        if low in NOVOTE_CHOICES:
            novote_cols[ci] = label
        else:
            choice_cols[ci] = label

    data = []
    for row in rows[header_idx + 1:]:
        pid = row[0] if len(row) > 0 else None
        vtype = row[1] if len(row) > 1 else None
        if pid is None or vtype is None:
            continue
        pid = str(pid).strip()
        if not pid.isdigit():
            continue
        if str(vtype).strip().lower() != "total":
            continue
        registered = as_int(row[2]) if len(row) > 2 else 0
        cast = as_int(row[3]) if len(row) > 3 else 0
        choices = {name: as_int(row[ci]) if ci < len(row) else 0
                   for ci, name in choice_cols.items()}
        over = sum(as_int(row[ci]) for ci, n in novote_cols.items()
                   if "over" in n.lower() and ci < len(row))
        under = sum(as_int(row[ci]) for ci, n in novote_cols.items()
                    if "under" in n.lower() and ci < len(row))
        data.append({"pid": pid, "registered": registered, "cast": cast,
                     "choices": choices, "over": over, "under": under})
    return {"name": display_name(title), "raw_name": title, "rcv": is_rcv(title),
            "choice_order": [choice_cols[c] for c in sorted(choice_cols)],
            "rows": data}


def main():
    sov_path, election_id, out_path, ids_path = sys.argv[1:5]
    berkeley = set(json.load(open(ids_path)))
    wb = openpyxl.load_workbook(sov_path, read_only=True, data_only=True)

    contests = []
    for sheet in wb.sheetnames:
        if sheet.lower() == "document map":
            continue
        parsed = parse_contest_sheet(wb[sheet])
        if parsed and parsed["rows"]:
            contests.append(parsed)

    precincts = {}
    catalog = {}  # contest name -> {rcv, choices, kind}
    for c in contests:
        keep = [r for r in c["rows"] if r["pid"] in berkeley]
        if not keep:
            continue
        kind = "measure" if any(ch.upper() in ("YES", "NO") for ch in c["choice_order"]) else "candidate"
        cat = catalog.setdefault(c["name"], {"rcv": c["rcv"], "kind": kind, "choices": []})
        # merge choice order across sheets (SOV paginates wide contests across sheets)
        for ch in c["choice_order"]:
            if ch not in cat["choices"]:
                cat["choices"].append(ch)
        for r in keep:
            p = precincts.setdefault(r["pid"], {"registered": 0, "ballots_cast": 0, "contests": {}})
            p["registered"] = max(p["registered"], r["registered"])
            p["ballots_cast"] = max(p["ballots_cast"], r["cast"])  # turnout proxy = top-of-ticket
            entry = p["contests"].setdefault(c["name"], {"choices": {}, "cast": 0})
            for ch, v in r["choices"].items():           # union candidate columns across sheets
                entry["choices"][ch] = max(entry["choices"].get(ch, 0), v)
            entry["cast"] = max(entry["cast"], r["cast"])
            if r["over"] or r["under"]:
                entry["over"] = max(entry.get("over", 0), r["over"])
                entry["under"] = max(entry.get("under", 0), r["under"])

    out = {"election_id": election_id, "berkeley_precincts": sorted(berkeley),
           "contests": catalog, "precincts": precincts}
    with open(out_path, "w") as f:
        json.dump(out, f, separators=(",", ":"))
    print(f"parsed {len(contests)} contest-sheets; {len(berkeley)} Berkeley precincts; "
          f"{len(catalog)} contests on Berkeley ballots -> {out_path}")


if __name__ == "__main__":
    main()
