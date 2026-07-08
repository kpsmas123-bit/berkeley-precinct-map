#!/usr/bin/env python3
"""
QA: reconcile Berkeley-precinct-summed results against the certified District
Canvass "City of Berkeley" totals, and TAG each contest verified / unverified in
the results file (catalog[contest]["verified"] = true|false|null).

  true   reconciles within THRESHOLD of the certified City-of-Berkeley total
  false  a City-of-Berkeley total exists but does not match  (investigate)
  null   no City-of-Berkeley total in the canvass -> can't reconcile here

The certified total is accumulated across ALL District Canvass sheets and ALL
"City of Berkeley ... Total" rows for a contest, because primaries wrap wide
contests across multiple sheets and split a jurisdiction across sub-districts.

Exit 1 if any contest is `false` (build treats that as a warning, not a stop).

Usage:
  qa.py <district_canvass.xlsx> <results.json>
"""
import json
import sys

import openpyxl

from parse_canvass import clean_contest_name, display_name, as_int, NUM_PREFIX

THRESHOLD = 0.005
JURIS = "city of berkeley"


def parse_district_canvass(path):
    """contest display name -> {choice -> certified votes}, summed across all sheets."""
    wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
    out = {}
    for sheet in wb.sheetnames:
        if sheet.lower() == "document map":
            continue
        rows = list(wb[sheet].iter_rows(values_only=True))
        title = header_idx = None
        for i, row in enumerate(rows[:10]):
            for c in row[:6]:
                if c and NUM_PREFIX.match(str(c)) and "Registered Voters" not in str(c):
                    title, header_idx = clean_contest_name(c), i + 1
                    break
            if title:
                break
        if not title:
            continue
        header = rows[header_idx]
        choice_cols = {ci: str(h).strip() for ci, h in enumerate(header)
                       if ci >= 5 and h and str(h).strip()
                       and str(h).strip().lower() not in
                       ("registered voters", "voters cast", "turnout (%)",
                        "over votes", "under votes")}
        name = display_name(title)
        bucket = out.setdefault(name, {})
        for row in rows[header_idx + 1:]:
            if len(row) < 2 or row[0] is None or row[1] is None:
                continue
            if str(row[0]).strip().lower() == JURIS and str(row[1]).strip().lower() == "total":
                for ci, choice in choice_cols.items():
                    bucket[choice] = bucket.get(choice, 0) + (as_int(row[ci]) if ci < len(row) else 0)
    return out


def main():
    dc_path, results_path = sys.argv[1], sys.argv[2]
    certified = parse_district_canvass(dc_path)
    results = json.load(open(results_path))
    precincts = results["precincts"]

    false_cnt = true_cnt = null_cnt = 0
    print(f"{'CONTEST':46} {'MINE':>9} {'CERT':>9} {'DIFF':>7}  STATUS")
    print("-" * 88)
    for name, meta in results["contests"].items():
        mine = {}
        for p in precincts.values():
            c = p["contests"].get(name)
            if c:
                for choice, v in c["choices"].items():
                    mine[choice] = mine.get(choice, 0) + v
        mine_tot = sum(mine.values())
        if name not in certified or not certified[name]:
            meta["verified"] = None
            null_cnt += 1
            print(f"{name[:46]:46} {mine_tot:>9} {'—':>9} {'—':>7}  no canvass total")
            continue
        cert_tot = sum(certified[name].values())
        diff = mine_tot - cert_tot
        pct = abs(diff) / cert_tot if cert_tot else (0 if mine_tot == 0 else 1)
        ok = pct <= THRESHOLD
        meta["verified"] = bool(ok)
        true_cnt += ok
        false_cnt += (not ok)
        rcv = " [RCV 1st-choice]" if meta["rcv"] else ""
        print(f"{name[:46]:46} {mine_tot:>9} {cert_tot:>9} {diff:>+7}  {'PASS' if ok else '*** FAIL ***'}{rcv}")

    json.dump(results, open(results_path, "w"), separators=(",", ":"))
    print("-" * 88)
    print(f"verified {true_cnt} | unverified(no canvass) {null_cnt} | MISMATCH {false_cnt}  (threshold {THRESHOLD:.1%})")
    sys.exit(1 if false_cnt else 0)


if __name__ == "__main__":
    main()
