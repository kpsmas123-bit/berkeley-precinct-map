#!/usr/bin/env python3
"""
QA: reconcile Berkeley-precinct-summed results against the certified District
Canvass "City of Berkeley" jurisdiction totals.

Only contests fully contained in Berkeley (Mayor, City Council, Rent Board, School
Directors, City measures) can be reconciled this way — for those, the sum of the
Berkeley precincts must equal the certified citywide total. County/state/federal
contests and statewide props are NOT Berkeley-jurisdictional, so they are reported
as "not reconcilable here" rather than failed.

Fails loudly (exit 1) on any reconcilable contest mismatching by > THRESHOLD.

Usage:
  qa.py <district_canvass.xlsx> <results.json>
"""
import json
import sys

import openpyxl

from parse_canvass import clean_contest_name, display_name, is_rcv, as_int, NUM_PREFIX

THRESHOLD = 0.005  # 0.5%
JURIS = "city of berkeley"


def parse_district_canvass(path):
    """contest display name -> {choice -> certified votes} for the Berkeley juris."""
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
                    title = clean_contest_name(c)
                    header_idx = i + 1
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
        for row in rows[header_idx + 1:]:
            if len(row) < 2 or row[0] is None or row[1] is None:
                continue
            if str(row[0]).strip().lower() == JURIS and str(row[1]).strip().lower() == "total":
                out[display_name(title)] = {name: as_int(row[ci]) if ci < len(row) else 0
                                            for ci, name in choice_cols.items()}
                break
    return out


def main():
    dc_path, results_path = sys.argv[1], sys.argv[2]
    certified = parse_district_canvass(dc_path)
    results = json.load(open(results_path))
    precincts = results["precincts"]

    failures = 0
    reconciled = 0
    print(f"{'CONTEST':46} {'MINE':>9} {'CERT':>9} {'DIFF':>7}  STATUS")
    print("-" * 88)
    for name, meta in results["contests"].items():
        # sum my Berkeley precinct choices
        mine = {}
        for p in precincts.values():
            c = p["contests"].get(name)
            if not c:
                continue
            for choice, v in c["choices"].items():
                mine[choice] = mine.get(choice, 0) + v
        if name not in certified:
            print(f"{name[:46]:46} {sum(mine.values()):>9} {'—':>9} {'—':>7}  not reconcilable (non-Berkeley juris)")
            continue
        cert = certified[name]
        reconciled += 1
        mine_tot, cert_tot = sum(mine.values()), sum(cert.values())
        diff = mine_tot - cert_tot
        pct = abs(diff) / cert_tot if cert_tot else 0
        status = "PASS" if pct <= THRESHOLD else "*** FAIL ***"
        if pct > THRESHOLD:
            failures += 1
        rcv = " [RCV 1st-choice]" if meta["rcv"] else ""
        print(f"{name[:46]:46} {mine_tot:>9} {cert_tot:>9} {diff:>+7}  {status}{rcv}")
        # per-choice detail on any mismatch
        if pct > THRESHOLD or set(mine) != set(cert):
            for choice in sorted(set(mine) | set(cert)):
                m, c = mine.get(choice, 0), cert.get(choice, 0)
                flag = "" if m == c else "  <-- differs"
                print(f"      {choice[:38]:38} mine={m:>8} cert={c:>8}{flag}")

    print("-" * 88)
    print(f"reconciled {reconciled} Berkeley contests; {failures} FAILED (>{THRESHOLD:.1%})")
    sys.exit(1 if failures else 0)


if __name__ == "__main__":
    main()
