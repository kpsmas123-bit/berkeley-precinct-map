#!/usr/bin/env python3
"""
Build a PRELIMINARY countywide results file from the county's two live feeds, for an
election whose certified Statement of Vote does not exist yet.

Why this exists
---------------
Alameda County publishes the precinct-level Statement of Vote only at or near
certification, ~30 days after election day, so for a month after an election the
county map had nothing at all for it. But the county does publish two machine-readable
live feeds in the meantime, and between them there is real precinct-level analysis to
be had:

  0. a Cast Vote Record export, when one has been obtained (--from-cvr, parsed by
     ingest/parse_cvr.py). This is the best of the three: one record per ballot, every
     contest, with the precinct on it. When it is supplied, the results-map feed is
     not used at all — the CVR covers every contest the feed would have, and many it
     would not.

  1. electionmaps.alamedacountyca.gov/json/electionResults.json
     The feed behind the county's own results map. Carries PER-PRECINCT votes, but
     only for the one or two contests the county chooses to map (Nov 2026: U.S.
     Representative CD-14 and Measure RTM), plus each precinct's reporting status.

  2. alamedacountyca.gov/rovresults/<id>/
     The running results portal. Every contest on the ballot, but COUNTYWIDE totals
     only — no geography.

So this writes one file in exactly the same shape a certified build produces, with:
  * contests / precincts / cities / aggregates for the precinct-mapped contests, so
    every existing map mode (winner, margin, % for a choice, stands-out) just works;
  * a `county_only` list carrying the countywide totals for every other big race, for
    the panel to show as numbers without a map;
  * a `preliminary` block with the county's own status banner, update number, last
    updated time, next scheduled updates, and countywide registration/turnout.

Honesty constraints baked in
----------------------------
* `preliminary: true` and `precinct_level_contests` are explicit in the output, so the
  frontend cannot show these numbers unlabelled.
* Per-precinct registration and ballots-cast do NOT exist in either feed, so they are
  written as 0 and the map's turnout mode disables itself. Countywide registration and
  turnout DO exist and are recorded as such.
* The precinct sums are reconciled against the feed's own countywide candidate totals
  and the result is recorded in `preliminary.reconciled`; a mismatch is reported.
* City assignment is geometric (a preliminary build has no local contests to infer
  jurisdiction from), with the ballot-derived corrections learned from certified builds
  applied by precinct id — see build_city_overrides.py.
* Nothing here is written into a certified results file. Re-running ./build_county.sh
  <id> after certification overwrites this file by the normal path.

With a CVR the only thing still missing is the county's own status banner and
countywide registration, so the portal is still read for those — and the CVR's
precinct sums are reconciled against the portal's countywide totals, which is a far
stronger check than the results-map feed could offer. The two are snapshots taken at
different moments, so a small shortfall is expected and reported rather than hidden.

Usage:
  fetch_live_county.py <election_id> <county_geo.geojson> <out.json>
                       [--rov-id N] [--from-cvr parsed_cvr.json]
                       [--map-url URL] [--portal-url URL]
                       [--overrides path] [--no-portal]
"""
import json
import os
import re
import sys
import time
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from county_contests import category, included, sort_key  # noqa: E402
from filter_county_results import cities_from_contests  # noqa: E402
import live_map_feed  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MAP_FEED = live_map_feed.FEED_URL
PORTAL = "https://alamedacountyca.gov/rovresults/{eid}/"
UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124.0 Safari/537.36")
UNINC = "Unincorporated"

# ---- portal scraping (same markup as fetch_live_results.py) --------------------
RACE_SPLIT = re.compile(r"<!--\s*Start Race:\s*(.*?)\s*-->", re.I | re.S)
ROW = re.compile(r"<TH[^>]*class=\"resultsRow[^\"]*\"[^>]*>(.*?)</TH>\s*"
                 r"<TD[^>]*>(.*?)</TD>\s*<TD[^>]*>(.*?)</TD>", re.I | re.S)
DIV = lambda cls: re.compile(r"<div[^>]*class=\"" + cls + r"[^\"]*\"[^>]*>(.*?)</div>",
                             re.I | re.S)
REPORTED, PASSING, VOTEFOR = DIV("reported"), DIV("passing"), DIV("votefor")
# The portal emits no "End Race" marker, so a race's body as split runs to the NEXT
# "Start Race" comment — which for the last race in a section swallows whatever
# follows it. In Nov 2026 that made "State Superintendent" absorb the entire
# propositions table and report Prop 3's 4.2M statewide-style figure as a candidate.
# Every race block ends with a "Back to Top" link, so cut there.
BODY_END = re.compile(r'<div[^>]*class="backtotop"|Back to Top', re.I)
# Propositions are NOT emitted as races. They live in one wide table with its own
# layout (Title | YES votes | YES % | NO votes | NO %), so they need their own parse
# or the county map silently loses every state proposition.
PROPS_BLOCK = re.compile(r'id="panelDtlProps".*?</TABLE>', re.I | re.S)
PROP_ROW = re.compile(
    r'<TH[^>]*class="resultsRow[^"]*"[^>]*>(.*?)</TH>\s*'
    r'<TD[^>]*>(.*?)</TD>\s*<TD[^>]*>(.*?)</TD>\s*'
    r'<TD[^>]*>(.*?)</TD>\s*<TD[^>]*>(.*?)</TD>', re.I | re.S)
STATUS_RE = re.compile(r"(Preliminary/Unofficial[^<]*)", re.I)
UPDATED_RE = re.compile(r"lastUpdated[^>]*>\s*<span>\s*Last Updated:\s*([^<]+)", re.I)
REG_RE = re.compile(r"Total Registration:\s*([\d,]+)", re.I)
CAST_RE = re.compile(r"Total Ballots Cast[^\d]*([\d,]+)[^\d]*([\d.]+)\s*%", re.I | re.S)
PCTS_RE = re.compile(r"(\d[\d,]*)\s+of\s+(\d[\d,]*)\s+Precincts[^(]*\(([\d.]+)%\)", re.I)
SCHED_RE = re.compile(r"(?:Mon|Tues|Wednes|Thurs|Fri|Satur|Sun)day,\s+"
                      r"(?:January|February|March|April|May|June|July|August|September|"
                      r"October|November|December)\s+\d{1,2},\s+\d{4}", re.I)


def txt(s):
    s = re.sub(r"(?is)<[^>]+>", " ", s)
    s = s.replace("&nbsp;", " ").replace("&amp;", "&")
    return re.sub(r"\s+", " ", s).strip()


def as_int(s):
    s = re.sub(r"[^\d-]", "", txt(s))
    return int(s) if s not in ("", "-") else 0


def as_pct(s):
    m = re.search(r"-?[\d.]+", txt(s))
    return float(m.group()) if m else 0.0


def fetch(url, timeout=120):
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read().decode("utf-8", "replace")


def parse_props(html):
    """The propositions table, which the portal does not emit as races."""
    m = PROPS_BLOCK.search(html)
    if not m:
        return []
    out = []
    for title, yv, yp, nv, np_ in PROP_ROW.findall(m.group(0)):
        name = txt(title)
        if not name:
            continue
        rows = [{"choice": "Yes", "votes": as_int(yv), "pct": as_pct(yp)},
                {"choice": "No", "votes": as_int(nv), "pct": as_pct(np_)}]
        out.append({"name": name, "rcv": False, "kind": "measure", "choices": rows,
                    "total_votes": sum(r["votes"] for r in rows)})
    return out


def parse_portal(html):
    """Countywide totals for every contest, plus the status banner."""
    ms, mu = STATUS_RE.search(html), UPDATED_RE.search(html)
    head = html[:html.lower().find("start race")] if "start race" in html.lower() else html
    mr, mc, mp = REG_RE.search(head), CAST_RE.search(head), PCTS_RE.search(head)

    banner = {
        "status": txt(ms.group(1)) if ms else "Preliminary/Unofficial",
        "last_updated": txt(mu.group(1)) if mu else "",
        "registered": as_int(mr.group(1)) if mr else 0,
        "ballots_cast": as_int(mc.group(1)) if mc else 0,
        "turnout_pct": float(mc.group(2)) if mc else 0.0,
    }
    if mp:
        banner["precincts_reported"] = as_int(mp.group(1))
        banner["precincts_total"] = as_int(mp.group(2))
        banner["precincts_reported_pct"] = float(mp.group(3))
    sched = SCHED_RE.findall(txt(head))
    # the first schedule date equal to or after "last updated" is the next release;
    # the banner's own date is in the same list, so dedupe against it
    banner["next_updates"] = [d for d in dict.fromkeys(sched)
                              if d.lower() not in banner["last_updated"].lower()]

    contests = []
    parts = RACE_SPLIT.split(html)
    for i in range(1, len(parts) - 1, 2):
        name, body = txt(parts[i]), BODY_END.split(parts[i + 1])[0]
        rows = [{"choice": txt(ch), "votes": as_int(v), "pct": as_pct(p)}
                for ch, v, p in ROW.findall(body) if txt(ch)]
        if not rows:
            continue
        rcv = "(RCV)" in name
        clean = re.sub(r"\s*\(RCV\)\s*$", "", name).strip()
        e = {"name": clean, "rcv": rcv,
             "kind": "measure" if any(re.fullmatch(r"(bonds\s+)?(yes|no)", r["choice"], re.I)
                                      for r in rows) else "candidate",
             "choices": rows, "total_votes": sum(r["votes"] for r in rows)}
        for key, rx in (("reported", REPORTED), ("threshold", PASSING), ("vote_for", VOTEFOR)):
            m = rx.search(body)
            if m:
                e[key] = txt(m.group(1))
        contests.append(e)
    contests.extend(parse_props(html))
    return banner, contests


# The precinct-level feed parse lives in live_map_feed.py — the Berkeley build reads
# the same feed, so there is one parser rather than two that can drift apart.


def from_cvr(cvr):
    """Shape a parsed CVR like parse_map_feed's output, keeping the big contests.

    A precinct whose cards were all redacted under 2 CCR 20126 has a contest row but
    no choices; it is left out of `mapped` so the map shows it as no-data rather than
    as a precinct where nobody voted.
    """
    cat = cvr.get("contests", {})
    mapped, meta = {}, {}
    for name, c in cat.items():
        if not included(name):
            continue
        per = {}
        for pid, p in cvr.get("precincts", {}).items():
            e = (p.get("contests") or {}).get(name)
            if not e:
                continue
            ch = {k: v for k, v in (e.get("choices") or {}).items() if v}
            if ch:
                per[str(pid)] = ch
        if not per:
            continue
        mapped[name] = per
        meta[name] = {"rcv": bool(c.get("rcv")), "kind": c.get("kind", "candidate"),
                      "choices": c.get("choices", []), "feed_totals": {}}
    return mapped, meta, {}


def agg(entries):
    out = {"choices": {}}
    for e in entries:
        for ch, v in e.get("choices", {}).items():
            out["choices"][ch] = out["choices"].get(ch, 0) + v
    return out


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    opt = {a.split("=", 1)[0].lstrip("-"): (a.split("=", 1)[1] if "=" in a else True)
           for a in sys.argv[1:] if a.startswith("--")}
    if len(args) < 3:
        print(__doc__.strip().splitlines()[-1], file=sys.stderr)
        sys.exit(2)
    eid, geo_path, out_path = args[:3]

    geo = json.load(open(geo_path))
    geo_city = {str(f["properties"]["precinct"]): f["properties"].get("city", UNINC)
                for f in geo["features"]}

    ov_path = opt.get("overrides") or os.path.join(ROOT, "data", "processed", "county",
                                                   "city_overrides.json")
    overrides = {}
    if os.path.exists(str(ov_path)):
        overrides = json.load(open(ov_path)).get("overrides", {})
    city_of = dict(geo_city)
    applied = [(p, geo_city[p], c) for p, c in overrides.items()
               if p in geo_city and geo_city[p] != c]
    for pid, _, c in applied:
        city_of[pid] = c

    # ---- precinct-level source: a CVR if we have one, else the live map feed ----
    cvr, feed, map_url = None, {}, None
    if opt.get("from-cvr"):
        cvr = json.load(open(opt["from-cvr"]))
        mapped, meta, reporting = from_cvr(cvr)
        if not mapped:
            print(f"ERROR: no big contests in {opt['from-cvr']}", file=sys.stderr)
            sys.exit(1)
        # A CVR carries every local contest, so jurisdiction can be inferred from the
        # ballot the way a certified build does, instead of leaning on geometry plus
        # corrections carried forward from an earlier election.
        city_names = sorted({c for c in geo_city.values() if c != UNINC})
        for pid, p in cvr.get("precincts", {}).items():
            if pid not in geo_city:
                continue
            hits = cities_from_contests(p.get("contests", {}).keys(), city_names)
            if len(hits) == 1:
                city = next(iter(hits))
            elif len(hits) > 1:
                g = geo_city[pid]
                city = g if g in hits else max(hits, key=hits.get)
            else:
                continue
            if city != city_of.get(pid):
                applied = [a for a in applied if a[0] != pid]
                if city != geo_city[pid]:
                    applied.append((pid, geo_city[pid], city))
            city_of[pid] = city
        applied.sort()
    else:
        map_url = opt.get("map-url") or MAP_FEED
        feed = live_map_feed.fetch(map_url)
        mapped, meta, reporting = live_map_feed.parse(feed)
        if not mapped:
            print(f"ERROR: no precinct-level races in {map_url}", file=sys.stderr)
            sys.exit(1)

    unknown = {p for pr in mapped.values() for p in pr} - set(geo_city)
    if unknown:
        print(f"ERROR: {len(unknown)} precincts in the live feed are absent from "
              f"{geo_path} (e.g. {sorted(unknown)[:5]}) — the geometry is for a "
              f"different election", file=sys.stderr)
        sys.exit(1)

    # ---- feed 2: countywide totals for everything else -------------------------
    banner, portal = {}, []
    if not opt.get("no-portal"):
        rov = opt.get("rov-id")
        purl = opt.get("portal-url") or (PORTAL.format(eid=rov) if rov else None)
        if not purl:
            print("ERROR: --rov-id or --portal-url is required (or pass --no-portal)",
                  file=sys.stderr)
            sys.exit(1)
        banner, portal = parse_portal(fetch(purl))
        banner["portal_url"] = purl
    if map_url:
        banner["map_feed_url"] = map_url
        if feed.get("lastUpdatedDateTime"):
            banner["map_feed_updated"] = feed["lastUpdatedDateTime"]
    banner.setdefault("status", "Preliminary/Unofficial")

    # Reconcile precinct sums against the best countywide totals available. For the
    # map feed that is the feed's own totals, which must match exactly. For a CVR it
    # is the portal — a snapshot taken at a different moment, so the CVR is expected
    # to be at or a little below the portal, and the gap is reported rather than
    # hidden. A CVR ahead of the portal means the export is the newer count.
    if cvr is None:
        recon = live_map_feed.reconcile(mapped, meta)
    else:
        portal_by_name = {c["name"]: c for c in portal}
        recon = {}
        for n, pr in mapped.items():
            got = sum(v for ch in pr.values() for v in ch.values())
            pc = portal_by_name.get(n)
            if not pc:
                recon[n] = {"ok": None, "cvr_votes": got,
                            "note": "not reported by the portal"}
                continue
            want = sum(r["votes"] for r in pc["choices"])
            recon[n] = {"ok": True, "cvr_votes": got, "portal_votes": want,
                        "delta": got - want,
                        "delta_pct": round(100 * (got - want) / want, 3) if want else None}

    # ---- assemble, in the shape a certified build produces ---------------------
    contests = {}
    for n in sorted(mapped, key=sort_key):
        contests[n] = {"rcv": meta[n]["rcv"], "kind": meta[n]["kind"],
                       "choices": meta[n]["choices"],
                       "category": category(n) or "regional",
                       "precinct_level": True}
        if meta[n].get("threshold"):
            contests[n]["threshold"] = meta[n]["threshold"]

    precincts, cities = {}, {}
    for pid in sorted(geo_city):
        city = city_of.get(pid, UNINC)
        kept = {n: {"choices": pr[pid]} for n, pr in mapped.items() if pid in pr}
        p = {"registered": 0, "ballots_cast": 0, "city": city, "contests": kept}
        if pid in reporting:
            p["reported_pct"] = reporting[pid]["pct"]
        precincts[pid] = p
        cities.setdefault(city, []).append(pid)
    cities = {c: sorted(p) for c, p in sorted(cities.items())}

    county_totals, city_totals = {}, {}
    for n in contests:
        county_totals[n] = agg([p["contests"][n] for p in precincts.values()
                                if n in p["contests"]])
        city_totals[n] = {c: agg([precincts[p]["contests"][n] for p in pids
                                  if n in precincts[p]["contests"]])
                          for c, pids in cities.items()
                          if any(n in precincts[p]["contests"] for p in pids)}

    # every other big race: countywide numbers, no geography
    county_only = [dict(c) for c in portal
                   if included(c["name"]) and c["name"] not in contests]
    for c in county_only:
        c["category"] = category(c["name"])
    county_only.sort(key=lambda c: sort_key(c["name"]))

    out = {
        "election_id": eid,
        "scope": "county",
        "preliminary": True,
        "contests": contests,
        "precincts": precincts,
        "cities": cities,
        "county_totals": county_totals,
        "city_totals": city_totals,
        "turnout": {"county": {"registered": banner.get("registered", 0),
                               "ballots_cast": banner.get("ballots_cast", 0)},
                    "cities": {}},
        "county_only": county_only,
        **({"cvr": cvr.get("cvr", {})} if cvr else {}),
        "status": {
            **{k: v for k, v in banner.items()},
            "fetched_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
            "precinct_level_contests": sorted(contests),
            "reconciled": all(r["ok"] is not False for r in recon.values()),
            "precinct_source": "cast_vote_record" if cvr else "results_map_feed",
            "reconciliation": recon,
            "city_assignment": "geometric, with ballot-derived corrections carried "
                               "forward from certified builds by precinct id",
            "city_corrections": [{"precinct": p, "outline": g, "city": c}
                                 for p, g, c in sorted(applied)],
            "note": ("Preliminary. Precinct-level figures come from the county's live "
                     "results map feed and cover only the contests the county chooses "
                     "to map; every other big race is countywide-only until the "
                     "certified Statement of Vote is published. Per-precinct "
                     "registration and turnout do not exist in either live feed."),
        },
    }
    json.dump(out, open(out_path, "w"), separators=(",", ":"))

    mb = os.path.getsize(out_path) / 1024 / 1024
    print(f"  {banner.get('status','')} | last updated: {banner.get('last_updated','?')}")
    if banner.get("precincts_total"):
        print(f"    {banner['precincts_reported']:,} of {banner['precincts_total']:,} "
              f"precincts reporting ({banner['precincts_reported_pct']}%); turnout "
              f"{banner.get('ballots_cast',0):,} of {banner.get('registered',0):,} "
              f"({banner.get('turnout_pct',0)}%)")
    if banner.get("next_updates"):
        print(f"    next county update: {banner['next_updates'][0]}")
    print(f"  preliminary county results -> {out_path} ({mb:.2f} MB)")
    src = "cast vote record" if cvr else "results-map feed"
    print(f"    precinct-level from the {src} ({len(contests)}):")
    for n in contests:
        got = sum(1 for p in precincts.values() if n in p["contests"])
        tot = county_totals[n]["choices"]
        lead = max(tot, key=tot.get) if tot else "—"
        d = sum(tot.values()) or 1
        r = recon[n]
        if r.get("ok") is False:
            flag = "  ⚠ does not reconcile"
        elif cvr and r.get("delta_pct") is not None:
            flag = f"  ({r['delta_pct']:+.2f}% vs portal)"
        else:
            flag = ""
        print(f"      {n[:48]:<48} {got:>4} pct  {lead[:22]:<22} "
              f"{100*tot.get(lead,0)/d:>5.1f}%{flag}")
    print(f"    countywide-only ({len(county_only)}): "
          + ", ".join(c["name"][:34] for c in county_only[:6])
          + (" …" if len(county_only) > 6 else ""))
    if applied:
        print(f"    {len(applied)} city corrections carried forward: "
              + ", ".join(f"{p}→{c}" for p, _, c in applied[:6]))
    if not all(r["ok"] for r in recon.values()):
        print("  ⚠ at least one contest's precinct sums disagree with the feed's own "
              "countywide totals — see status.reconciliation", file=sys.stderr)


if __name__ == "__main__":
    main()
