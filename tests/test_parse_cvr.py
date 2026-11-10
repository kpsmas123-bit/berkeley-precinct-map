#!/usr/bin/env python3
"""
Regression test for ingest/parse_cvr.py.

Builds a synthetic Dominion CVR export in a temp directory and checks the parser
against it. The fixture deliberately reproduces the things that were wrong, or nearly
wrong, when this was written against Alameda's real Nov 2026 export:

  * contests nested under `Cards` (Democracy Suite 5.19) AND the older shape with
    `Contests` directly on the element — reading only one silently yields zero votes;
  * a precinct portion whose `Description` is the real precinct id while its
    `ExternalId` is a meaningless sequence number, which is what defeats the join
    order the vendor document implies;
  * Youth Voting counting groups, which must not be folded into contest results;
  * contests redacted under 2 CCR 20126, where `Marks` is the string
    "*** REDACTED ***" rather than a list — iterating it crashes, and treating it as
    empty would invent undervotes;
  * a precinct where EVERY card is redacted, which must end up with no usable result
    rather than a row of zeros;
  * an adjudicated ballot, where `Modified` supersedes `Original`;
  * ambiguous marks and RCV lower rankings, which are not votes.

Usage:  .venv/bin/python tests/test_parse_cvr.py       (exit 0 = pass)
"""
import json
import os
import subprocess
import sys
import tempfile
import zipfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PARSER = os.path.join(ROOT, "ingest", "parse_cvr.py")

CD = "U.S. Representative, 12th Congressional District"
RTM = "Measure RTM - Public Transit Revenue Measure District"
CC = "Member, City Council, District 1 - Berkeley"


def mark(cid, rank=1, vote=True, amb=False):
    return {"CandidateId": cid, "PartyId": 0, "Rank": rank, "MarkDensity": 93,
            "IsAmbiguous": amb, "IsVote": vote, "OutstackConditionIds": []}


REDACTED = "*** REDACTED ***"


def contest(cid, marks, under=0, over=0):
    if marks == REDACTED:          # the whole row is withheld, counts included
        return {"Id": cid, "ManifestationId": 1, "Undervotes": REDACTED,
                "Overvotes": REDACTED, "OutstackConditionIds": REDACTED,
                "Marks": REDACTED}
    return {"Id": cid, "ManifestationId": 1, "Undervotes": under, "Overvotes": over,
            "OutstackConditionIds": [], "Marks": marks}


def session(rec, portion, contests, group=2, modified=None, legacy=False):
    """A ballot. `legacy` emits the pre-5.19 shape with no Cards layer."""
    def el(cons, current):
        e = {"PrecinctPortionId": portion, "BallotTypeId": 1, "IsCurrent": current}
        e["Contests" if legacy else "Cards"] = (
            cons if legacy else [{"Id": 1, "PaperIndex": 1, "Contests": cons}])
        return e
    s = {"TabulatorId": 1, "BatchId": 1, "RecordId": rec, "CountingGroupId": group,
         "SessionType": "ScannedVote", "Original": el(contests, modified is None)}
    if modified is not None:
        s["Modified"] = el(modified, True)
    return s


def build(d):
    w = lambda n, o: json.dump(o, open(os.path.join(d, n + ".json"), "w"), indent=1)
    V = "5.19.7.5"
    w("ContestManifest", {"Version": V, "List": [
        {"Id": 10, "Description": CD, "VoteFor": 1, "NumOfRanks": 0},
        {"Id": 20, "Description": RTM, "VoteFor": 1, "NumOfRanks": 0},
        {"Id": 30, "Description": CC, "VoteFor": 1, "NumOfRanks": 3},
        {"Id": 40, "Description": "Contest Nobody Voted In", "VoteFor": 1, "NumOfRanks": 0}]})
    w("CandidateManifest", {"Version": V, "List": [
        {"Id": 101, "Description": "Lateefah Simon", "ContestId": 10, "Type": "Regular"},
        {"Id": 102, "Description": "Jamie Joyce", "ContestId": 10, "Type": "Regular"},
        {"Id": 201, "Description": "Yes", "ContestId": 20, "Type": "Regular"},
        {"Id": 202, "Description": "No", "ContestId": 20, "Type": "Regular"},
        {"Id": 301, "Description": "Ada Ark", "ContestId": 30, "Type": "Regular"},
        {"Id": 302, "Description": "Ben Birch", "ContestId": 30, "Type": "Regular"},
        {"Id": 401, "Description": "Nobody", "ContestId": 40, "Type": "Regular"}]})
    # Alameda's real shape: Description is the precinct id, ExternalId is a counter.
    # Portion 3 hides the id inside a longer label, to exercise the substring path.
    w("PrecinctPortionManifest", {"Version": V, "List": [
        {"Id": 1, "Description": "203880", "ExternalId": "0001", "PrecinctId": 1},
        {"Id": 2, "Description": "203880", "ExternalId": "0002", "PrecinctId": 1},
        {"Id": 3, "Description": "PCT 400300 - Portion 1", "ExternalId": "0003",
         "PrecinctId": 99},            # dangling on purpose: forces the substring path
        {"Id": 4, "Description": "500500", "ExternalId": "0004", "PrecinctId": 3}]})
    w("PrecinctManifest", {"Version": V, "List": [
        {"Id": 1, "Description": "203880", "ExternalId": "0001"},
        {"Id": 2, "Description": "400300", "ExternalId": "0002"},
        {"Id": 3, "Description": "500500", "ExternalId": "0004"}]})
    w("CountingGroupManifest", {"Version": V, "List": [
        {"Id": 1, "Description": "Election Day", "ExternalId": ""},
        {"Id": 2, "Description": "Vote by Mail", "ExternalId": ""},
        {"Id": 3, "Description": "Youth Voting Election Day", "ExternalId": ""},
        {"Id": 4, "Description": "Youth Voting Vote by Mail", "ExternalId": ""}]})
    w("Configuration", {"Version": V, "SplitFilesPerBatch": True})

    w("CvrExport_0", {"Version": V, "ElectionId": "Test", "Sessions": [
        # clean ballot, RCV ranks 1 and 2
        session(1, 1, [contest(10, [mark(101)]), contest(20, [mark(201)]),
                       contest(30, [mark(301, 1), mark(302, 2)])]),
        # overvote and undervote, as the export states them
        session(2, 1, [contest(10, [mark(102)]),
                       contest(20, [mark(201, vote=False), mark(202, vote=False)], over=1)]),
        session(3, 2, [contest(10, [], under=1), contest(20, [mark(201)])]),
        # Youth Voting — must not reach any tally
        session(4, 1, [contest(10, [mark(102)]), contest(20, [mark(202)])], group=3),
        session(5, 1, [contest(10, [mark(102)]), contest(20, [mark(202)])], group=4)]})
    w("CvrExport_1", {"Version": V, "ElectionId": "Test", "Sessions": [
        # adjudicated: Original says Joyce, Modified says Simon
        session(1, 3, [contest(10, [mark(102)]), contest(20, [mark(202)])],
                modified=[contest(10, [mark(101)]), contest(20, [mark(202)])]),
        # ambiguous mark alongside a real one — pre-5.19 shape, to test the fallback
        session(2, 3, [contest(10, [mark(102, vote=False, amb=True), mark(101)]),
                       contest(20, [mark(202)])], legacy=True),
        # one redacted contest on an otherwise readable ballot
        session(3, 1, [contest(10, REDACTED), contest(20, [mark(201)])]),
        # precinct 500500: every card redacted -> no usable result
        session(4, 4, [contest(10, REDACTED), contest(20, REDACTED)]),
        session(5, 4, [contest(10, REDACTED), contest(20, REDACTED)])]})
    json.dump(["203880", "400300", "500500"], open(os.path.join(d, "ids.json"), "w"))


def run(export, out, *extra):
    cmd = [sys.executable, PARSER, export, "2026-11-general", out, "--quiet"] + list(extra)
    r = subprocess.run(cmd, capture_output=True, text=True)
    return r, (json.load(open(out)) if os.path.exists(out) else None)


def main():
    fails = []

    def eq(label, got, want):
        ok = got == want
        print(("  ok   " if ok else "  FAIL ") + f"{label}: {got!r}"
              + ("" if ok else f"   (want {want!r})"))
        if not ok:
            fails.append(label)

    with tempfile.TemporaryDirectory() as tmp:
        exp = os.path.join(tmp, "export")
        os.makedirs(exp)
        build(exp)
        ids = os.path.join(exp, "ids.json")

        r, d = run(exp, os.path.join(tmp, "o.json"), "--precinct-ids=" + ids)
        assert d, r.stderr
        P = d["precincts"]

        print("precinct join + schema")
        eq("portions joined by Description", d["cvr"]["precinct_join"].get("portion_description"), 3)
        eq("id recovered from a longer label",
           d["cvr"]["precinct_join"].get("portion_description_substring"), 1)
        eq("precincts found", sorted(P), ["203880", "400300", "500500"])

        print("redaction (2 CCR 20126)")
        eq("redacted contest-cards counted", d["cvr"]["redacted_contest_cards"], 5)
        eq("redacted card still counts as cast",
           P["203880"]["contests"][CD]["cast"], 4)
        eq("redacted card is not a vote", P["203880"]["contests"][CD]["choices"],
           {"Lateefah Simon": 1, "Jamie Joyce": 1})
        eq("redacted card is not an undervote",
           P["203880"]["contests"][CD]["under"], 1)
        eq("redaction tracked per contest",
           P["203880"]["contests"][CD].get("redacted"), 1)
        eq("fully redacted precinct flagged", d["cvr"]["redacted_precincts"], ["500500"])
        eq("fully redacted precinct has no votes",
           P["500500"]["contests"][CD]["choices"], {})

        print("counting groups")
        eq("youth ballots excluded", d["cvr"]["excluded_ballots"], 2)
        eq("excluded group names", d["cvr"]["excluded_groups"],
           ["Youth Voting Election Day", "Youth Voting Vote by Mail"])
        eq("youth votes absent from tally", P["203880"]["contests"][RTM]["choices"], {"Yes": 3})

        print("tallies")
        eq("ballots 203880 (top-of-ticket proxy)", P["203880"]["ballots_cast"], 4)
        eq("cards 203880", P["203880"]["cards"], 4)
        eq("ballots 400300", P["400300"]["ballots_cast"], 2)
        eq("undervote from the export", P["203880"]["contests"][CD]["under"], 1)
        eq("overvote from the export", P["203880"]["contests"][RTM]["over"], 1)


        print("marks")
        eq("RCV: rank 1 only", P["203880"]["contests"][CC]["choices"], {"Ada Ark": 1})
        eq("adjudication: Modified wins", P["400300"]["contests"][CD]["choices"],
           {"Lateefah Simon": 2})
        eq("legacy Contests shape parsed", P["400300"]["contests"][RTM]["choices"], {"No": 2})

        print("catalog")
        eq("measure kind", d["contests"][RTM]["kind"], "measure")
        eq("rcv flag", d["contests"][CC]["rcv"], True)
        eq("unvoted contest dropped", "Contest Nobody Voted In" in d["contests"], False)
        eq("registered unknown to a CVR", P["203880"]["registered"], 0)

        print("options")
        _, da = run(exp, os.path.join(tmp, "a.json"), "--rcv-all-ranks")
        eq("--rcv-all-ranks counts rank 2",
           da["precincts"]["203880"]["contests"][CC]["choices"],
           {"Ada Ark": 1, "Ben Birch": 1})
        _, dg = run(exp, os.path.join(tmp, "g.json"), "--counting-groups=all")
        eq("--counting-groups=all includes youth",
           dg["precincts"]["203880"]["cards"], 6)

        zp = os.path.join(tmp, "export.zip")
        with zipfile.ZipFile(zp, "w") as z:
            for f in os.listdir(exp):
                z.write(os.path.join(exp, f), f)
        _, dz = run(zp, os.path.join(tmp, "z.json"), "--precinct-ids=" + ids)
        eq("zip input matches directory input", dz["precincts"], P)

        bad = os.path.join(tmp, "bad_ids.json")
        json.dump(["999998", "999999"], open(bad, "w"))
        rb, _ = run(exp, os.path.join(tmp, "b.json"), "--precinct-ids=" + bad)
        eq("a join matching nothing exits non-zero", rb.returncode, 1)

    print()
    print("ALL PASS" if not fails else f"{len(fails)} FAILED: {fails}")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
