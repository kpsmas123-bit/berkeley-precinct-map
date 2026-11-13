#!/usr/bin/env python3
"""
Parse a Dominion Democracy Suite **Cast Vote Record** export into the same results
shape the canvass parsers emit, so the rest of the county pipeline consumes it
unchanged.

See docs/pre-certification.md for why a CVR is read at all.

The export is a directory (often zipped) of JSON manifests plus CvrExport*.json,
the ballots ("Sessions"); field names follow the vendor's "CVR export file format".

Where the vendor spec and the real export disagree
--------------------------------------------------
Alameda's export is Democracy Suite 5.19, and two things differ from the published
"CVR export file format" document, both of which silently produce wrong numbers if
taken on trust:

* The spec says the Original/Modified element "Lists all contests for the current
  ballot type" as `Contests`. In 5.19 contests are nested one level deeper, under
  `Cards` — a ballot can be several physical cards. Reading `element["Contests"]`
  finds nothing and every precinct comes out empty. Both shapes are handled here.
* The spec does not mention it, but each contest carries its own `Undervotes` and
  `Overvotes` counts. Those are used directly rather than inferred from the marks.
* A Session is one **card**, not one ballot. A multi-card ballot is split across
  several sessions, each holding one card, and nothing in the export links them back
  together. Counting sessions as ballots overstated Alameda's turnout by 3.2x
  (1,824,937 sessions against 562,851 ballots cast). Since every contest lives on
  exactly one card, per-contest tallies are unaffected; only a ballot count is, so
  `ballots_cast` is taken as the largest number of cards any one contest appeared on
  in that precinct — the same top-of-ticket proxy parse_canvass.py uses.

Redaction
---------
California requires a published CVR to have "the voter choices corresponding to any
ballot susceptible to being personally identified with an individual voter" removed
(2 CCR 20126). Alameda does this in place: the contest row stays, and `Marks`,
`Undervotes` and `Overvotes` become the string "*** REDACTED ***". Iterating that as
a list of marks crashes; treating it as empty would silently count the card as an
undervote. It is counted as a card the contest appeared on, with its choices unknown
and tracked in `redacted`.

This is not a rounding error in small precincts: in Alameda's Nov 2026 export 527
cards are redacted across 42 precincts, and in all 42 EVERY card is redacted, so those
precincts carry no usable result at all. They are listed in `cvr.redacted_precincts`
so the map can show them as no-data rather than as zeros.

Each Session has an `Original` element and, where a ballot was adjudicated, a
`Modified` one. Only the element flagged `IsCurrent` counts, and `Modified` wins —
reading `Original` unconditionally would report pre-adjudication marks. (In the first
Alameda file, 17 of 732 ballots were adjudicated.)

Within a contest, a mark counts only when `IsVote` is true: Dominion also records
ambiguous marks, marks on overvoted contests, and write-in positions that resolved to
nothing. For a ranked contest only `Rank: 1` is counted, matching how the rest of this
project reports RCV ("1st choice") — the CVR carries the full ranking, so a proper
round-by-round count is possible later from the same file.

**Youth Voting ballots are excluded by default.** Counting groups 3 and 4 are ballots
cast by minors in the county's youth programme; the Registrar reports them in a
separate turnout block and they are not part of any contest result. Folding them in
would quietly inflate precinct tallies. `--counting-groups` overrides the choice.

The precinct join
-----------------
A CVR identifies a **precinct portion**, not a consolidated precinct, and which field
carries the real precinct id varies by county. In Alameda's export the portion's
`Description` IS the six-digit precinct id and `ExternalId` is a meaningless sequence
number ("0001"), so preferring `ExternalId` — which the vendor doc implies — joins to
nothing. Candidates are therefore tried in order (explicit override, the portion's
Description, the precinct it names via `PrecinctId`, then the ExternalIds) and, when
`--precinct-ids` is given, the first candidate that actually matches a known precinct
wins. The strategy used is reported, and a join matching nothing exits non-zero.

Usage:
  parse_cvr.py <export.zip | export_dir> <election_id> <out.json>
               [--precinct-ids ids.json] [--portion-map map.json]
               [--counting-groups 1,2] [--rcv-all-ranks] [--limit N] [--quiet]
"""
import collections
import io
import json
import os
import re
import sys
import zipfile

DIGITS = re.compile(r"(\d{3,8})")
# The CVR names a ranked contest "Auditor - Berkeley (RCV)"; the county's results
# portal, its results map and the certified Statement of Vote all call it "Auditor -
# Berkeley" and carry the ranking separately. Keeping the suffix would list the same
# race twice under two names, and would rename every ranked contest the moment the
# certified canvass replaced this file. Strip it and keep the flag.
RCV_SUFFIX = re.compile(r"\s*\(RCV\)\s*$", re.I)


# ---------------------------------------------------------------- file access
class Export:
    """A CVR export, read from a directory or straight out of its zip."""

    def __init__(self, path):
        self.path, self.zip = path, None
        if zipfile.is_zipfile(path):
            self.zip = zipfile.ZipFile(path)
            self.names = self.zip.namelist()
        elif os.path.isdir(path):
            self.names = []
            for root, _, files in os.walk(path):
                for f in files:
                    self.names.append(os.path.relpath(os.path.join(root, f), path))
        else:
            raise SystemExit(f"ERROR: {path} is neither a zip nor a directory")

    def _find(self, stem):
        stem = stem.lower()
        hits = [n for n in self.names
                if os.path.basename(n).lower() == stem + ".json"]
        return hits[0] if hits else None

    def read_json(self, stem, required=True):
        n = self._find(stem)
        if n is None:
            if required:
                raise SystemExit(f"ERROR: {stem}.json not found in {self.path}")
            return None
        return json.loads(self._raw(n).decode("utf-8-sig"))

    def cvr_files(self):
        """Every CvrExport*.json, smallest path first for stable ordering.

        A large export is usually split per batch (the exporter's SplitFilesPerBatch
        option), which is what keeps this streamable one file at a time.
        """
        out = [n for n in self.names
               if re.match(r"cvrexport.*\.json$", os.path.basename(n), re.I)]
        return sorted(out)

    def _raw(self, name):
        if self.zip:
            return self.zip.read(name)
        with open(os.path.join(self.path, name), "rb") as f:
            return f.read()

    def load_cvr(self, name):
        return json.loads(self._raw(name).decode("utf-8-sig"))


# ------------------------------------------------------------------ manifests
def by_id(manifest):
    """Dominion manifests are {"Version":..,"List":[{...}]} — index them by Id."""
    rows = (manifest or {}).get("List", manifest if isinstance(manifest, list) else [])
    return {str(r["Id"]): r for r in rows if "Id" in r}


def portion_to_precinct(portions, precincts, override, known=None):
    """Resolve each precinct portion to a precinct id, and say how.

    Candidates are tried in order of how likely they are to BE the precinct id, and
    when the election's real precinct list is supplied the first candidate that
    matches it wins outright — which is what stops a county whose ExternalId is a
    sequence number from joining to nothing.
    """
    known = {str(k) for k in known} if known else None
    out, how = {}, collections.Counter()
    for pid, p in portions.items():
        if pid in override:
            out[pid] = str(override[pid]); how.update(["override"]); continue

        prec = precincts.get(str(p.get("PrecinctId"))) or {}
        base = [
            ("portion_description", str(p.get("Description") or "").strip()),
            ("precinct_description", str(prec.get("Description") or "").strip()),
            ("precinct_external_id", str(prec.get("ExternalId") or "").strip()),
            ("portion_external_id", str(p.get("ExternalId") or "").strip()),
        ]
        # a precinct id embedded in a longer label, e.g. "PCT 203880 (Portion A)"
        extra = [(label + "_substring", d) for label, v in base
                 for d in DIGITS.findall(v) if d != v]
        cands = base + extra

        pick = None
        if known is not None:
            pick = next(((l, v) for l, v in cands if v in known), None)
        if pick is None:
            pick = next(((l, v) for l, v in cands if v), None)
        if pick is None:
            out[pid] = pid; how.update(["unresolved"]); continue
        out[pid] = pick[1]; how.update([pick[0]])
    return out, how


# ------------------------------------------------------------------ the count
def contests_of(element):
    """Every contest on the ballot, whichever schema the export uses.

    5.19 nests contests under Cards (a ballot can be several physical cards); older
    exports put them directly on the element. Reading only one shape silently yields
    zero votes on the other.
    """
    cards = element.get("Cards")
    if isinstance(cards, list):
        return [c for card in cards for c in (card.get("Contests") or [])]
    return element.get("Contests") or []


def current_element(session):
    """The ballot's current state: Modified where a ballot was adjudicated.

    `IsCurrent` is what the spec says to trust; where neither element carries it,
    Modified still wins, because its presence means an adjudicator changed something.
    """
    mod, orig = session.get("Modified"), session.get("Original")
    for el in (mod, orig):
        if isinstance(el, dict) and el.get("IsCurrent"):
            return el
    return mod if isinstance(mod, dict) else orig


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    opt = {a.split("=", 1)[0].lstrip("-"): (a.split("=", 1)[1] if "=" in a else True)
           for a in sys.argv[1:] if a.startswith("--")}
    if len(args) < 3:
        print(__doc__.strip().splitlines()[-3], file=sys.stderr)
        sys.exit(2)
    src, election_id, out_path = args[:3]
    quiet = bool(opt.get("quiet"))
    groups_opt = opt.get("counting-groups")
    all_ranks = bool(opt.get("rcv-all-ranks"))
    limit = int(opt["limit"]) if opt.get("limit") else None

    ex = Export(src)
    contests_m = by_id(ex.read_json("ContestManifest"))
    cands_m = by_id(ex.read_json("CandidateManifest"))
    portions_m = by_id(ex.read_json("PrecinctPortionManifest"))
    precincts_m = by_id(ex.read_json("PrecinctManifest", required=False)) or {}
    groups_m = by_id(ex.read_json("CountingGroupManifest", required=False)) or {}

    # Youth Voting ballots are cast by minors and are reported separately by the
    # Registrar; they are not part of any contest result.
    youth = {i for i, g in groups_m.items()
             if "youth" in str(g.get("Description", "")).lower()}
    if groups_opt is True or groups_opt is None:
        keep_groups = None if not youth else {i for i in groups_m if i not in youth}
    elif str(groups_opt).lower() == "all":
        keep_groups = None
    else:
        keep_groups = {s.strip() for s in str(groups_opt).split(",") if s.strip()}

    override = {}
    if opt.get("portion-map"):
        override = {str(k): str(v) for k, v in json.load(open(opt["portion-map"])).items()}
    known_ids = None
    if opt.get("precinct-ids"):
        known_ids = set(map(str, json.load(open(opt["precinct-ids"]))))
    pmap, how = portion_to_precinct(portions_m, precincts_m, override, known_ids)

    cname = {i: RCV_SUFFIX.sub("", str(c.get("Description", "")).strip())
             for i, c in contests_m.items()}
    ranked_by_name = {i: bool(RCV_SUFFIX.search(str(c.get("Description", ""))))
                      for i, c in contests_m.items()}
    vote_for = {i: int(c.get("VoteFor", 1) or 1) for i, c in contests_m.items()}
    ranks = {i: int(c.get("NumOfRanks", 0) or 0) for i, c in contests_m.items()}
    chname = {i: str(c.get("Description", "")).strip() for i, c in cands_m.items()}
    chcontest = {i: str(c.get("ContestId")) for i, c in cands_m.items()}

    catalog, precincts = {}, {}
    seen_cands = collections.defaultdict(set)
    n_sessions = n_skipped = n_group_skipped = n_redacted = 0
    by_group = collections.Counter()
    files = ex.cvr_files()
    if not files:
        raise SystemExit(f"ERROR: no CvrExport*.json found in {src}")

    for fi, fn in enumerate(files, 1):
        blob = ex.load_cvr(fn)
        sessions = blob.get("Sessions", blob if isinstance(blob, list) else [])
        for s in sessions:
            gid = str(s.get("CountingGroupId"))
            if keep_groups is not None and gid not in keep_groups:
                n_group_skipped += 1
                continue
            el = current_element(s)
            if not isinstance(el, dict):
                n_skipped += 1
                continue
            pid = pmap.get(str(el.get("PrecinctPortionId")), None)
            if pid is None:
                n_skipped += 1
                continue
            n_sessions += 1
            by_group[str(groups_m.get(gid, {}).get("Description", gid))] += 1
            p = precincts.setdefault(pid, {"registered": 0, "ballots_cast": 0,
                                           "cards": 0, "contests": {}})
            p["cards"] += 1
            for con in contests_of(el):
                cid = str(con.get("Id"))
                name = cname.get(cid)
                if not name:
                    continue
                entry = p["contests"].setdefault(name, {"choices": {}, "cast": 0,
                                                        "over": 0, "under": 0})
                entry["cast"] += 1          # cards on which this contest appeared
                marks = con.get("Marks")
                if isinstance(marks, str):
                    # redacted under 2 CCR 20126 — the card is real, its choices are
                    # withheld. Counting it as an undervote would be a fabrication.
                    entry["redacted"] = entry.get("redacted", 0) + 1
                    n_redacted += 1
                    continue
                counted = 0
                for m in (marks or []):
                    if not isinstance(m, dict):
                        continue
                    if not m.get("IsVote"):
                        continue
                    if not all_ranks and int(m.get("Rank", 1) or 1) != 1:
                        continue
                    ch = chname.get(str(m.get("CandidateId")))
                    if not ch:
                        continue
                    entry["choices"][ch] = entry["choices"].get(ch, 0) + 1
                    seen_cands[cid].add(str(m.get("CandidateId")))
                    counted += 1
                # 5.19 states these per contest; only fall back to inferring them
                # from the marks on an export that omits them.
                if isinstance(con.get("Undervotes"), (int, float)) \
                        or isinstance(con.get("Overvotes"), (int, float)):
                    entry["under"] += int(con.get("Undervotes") or 0)
                    entry["over"] += int(con.get("Overvotes") or 0)
                else:
                    vf = vote_for.get(cid, 1)
                    if counted == 0:
                        if con.get("Marks"):
                            entry["over"] += 1      # marks present, none counted
                        else:
                            entry["under"] += 1
                    elif counted < vf:
                        entry["under"] += vf - counted
            if limit and n_sessions >= limit:
                break
        if not quiet:
            print(f"    [{fi}/{len(files)}] {os.path.basename(fn)}: "
                  f"{n_sessions:,} ballots so far", file=sys.stderr)
        if limit and n_sessions >= limit:
            break

    # contest catalog, with choices in the manifest's own (ballot) order
    for cid, name in cname.items():
        chs = [chname[i] for i in cands_m
               if chcontest.get(i) == cid and chname.get(i)]
        if not chs:
            continue
        kind = "measure" if all(re.fullmatch(r"(bonds\s+)?(yes|no)", c, re.I)
                                for c in chs) else "candidate"
        catalog[name] = {"rcv": ranks.get(cid, 0) > 1 or ranked_by_name.get(cid, False),
                         "kind": kind,
                         "choices": chs, "vote_for": vote_for.get(cid, 1)}
    catalog = {n: catalog[n] for n in sorted(catalog)
               if any(n in p["contests"] for p in precincts.values())}
    for p in precincts.values():
        p["contests"] = {n: e for n, e in p["contests"].items() if n in catalog}
        # a Session is a card, so the nearest honest ballot count is the busiest
        # contest's card count — the top-of-ticket proxy used across this project
        p["ballots_cast"] = max((e["cast"] for e in p["contests"].values()), default=0)

    # precincts where every card had its choices withheld carry no usable result
    fully_redacted = sorted(
        pid for pid, p in precincts.items()
        if p["contests"] and all(
            e.get("redacted", 0) >= e["cast"] for e in p["contests"].values()))

    out = {"election_id": election_id,
           "source": "cast_vote_record",
           "cvr": {"export": os.path.basename(src.rstrip("/")),
                   "cards": n_sessions,
                   "ballots_cast": sum(p["ballots_cast"] for p in precincts.values()),
                   "cards_skipped": n_skipped,
                   "redacted_contest_cards": n_redacted,
                   "redacted_precincts": fully_redacted,
                   "files": len(files),
                   "rcv_counting": "all ranks" if all_ranks else "first choice only",
                   "precinct_join": dict(how),
                   "counting_groups": dict(by_group),
                   "excluded_ballots": n_group_skipped,
                   "excluded_groups": sorted(
                       str(groups_m[i].get("Description", i)) for i in groups_m
                       if keep_groups is not None and i not in keep_groups),
                   "note": ("Built from a Dominion CVR export. A record is one CARD, "
                            "not one ballot, so 'ballots_cast' is the busiest contest's "
                            "card count in that precinct, not a session count. "
                            "'registered' is unknown to a CVR and is 0. Everything here "
                            "reflects ballots PROCESSED at export time, not final "
                            "turnout. Cards whose choices were redacted under 2 CCR "
                            "20126 are counted in 'cast' and in 'redacted', never as "
                            "votes or undervotes.")},
           "contests": catalog,
           "precincts": precincts}
    json.dump(out, open(out_path, "w"), separators=(",", ":"))

    mb = os.path.getsize(out_path) / 1024 / 1024
    print(f"  CVR: {n_sessions:,} cards in {len(files)} file(s) -> "
          f"{len(precincts)} precincts, {len(catalog)} contests -> {out_path} ({mb:.2f} MB)")
    print(f"    ballots_cast (top-of-ticket proxy): "
          f"{sum(p['ballots_cast'] for p in precincts.values()):,}")
    print(f"    precinct join: " + ", ".join(f"{k}={v}" for k, v in how.most_common()))
    print(f"    counting groups: "
          + ", ".join(f"{k} {v:,}" for k, v in by_group.most_common()))
    if n_group_skipped:
        print(f"    {n_group_skipped:,} ballots excluded ("
              + ", ".join(sorted(str(groups_m[i].get("Description", i)) for i in groups_m
                                 if keep_groups is not None and i not in keep_groups))
              + ")")
    if n_redacted:
        print(f"    {n_redacted:,} contest-cards redacted under 2 CCR 20126"
              + (f"; {len(fully_redacted)} precincts fully redacted (no usable result)"
                 if fully_redacted else ""))
    if n_skipped:
        print(f"    {n_skipped:,} records skipped (no current element or no precinct)")

    if known_ids is not None:
        want, got = known_ids, set(precincts)
        miss, extra = sorted(want - got), sorted(got - want)
        print(f"    vs known precinct list: {len(got & want)} matched, "
              f"{len(miss)} missing, {len(extra)} unknown")
        if miss[:5]:
            print(f"      missing e.g. {miss[:5]}")
        if extra[:5]:
            print(f"      unknown e.g. {extra[:5]}")
        if not (got & want):
            print("  ⚠ the precinct join produced NOTHING matching this election's "
                  "precinct ids — pass --portion-map", file=sys.stderr)
            sys.exit(1)


if __name__ == "__main__":
    main()
