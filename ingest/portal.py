#!/usr/bin/env python3
"""
The county's running results portal: alamedacountyca.gov/rovresults/<id>/

Every contest on the ballot with countywide totals, plus the status banner, with no
geography at all. Both live builds read it — the Berkeley one keeps the contests whose
jurisdiction is Berkeley, the county one keeps the big shared-ballot races — so the
markup quirks are handled here once.

Two of them are not optional:

* There is no "End Race" marker. A body split on the "Start Race" comments runs to the
  next one, so the last race in a section swallows whatever follows it. In Nov 2026
  that made "State Superintendent" absorb the propositions table and report Prop 3's
  figure as a candidate with 4.2M votes. Every block ends with a "Back to Top" link,
  so each body is cut there.
* Propositions are not emitted as races at all. They live in one wide table with its
  own layout, and a parser that only walks the race comments loses every one of them.

Both were found in the county scraper and had to be fixed in the Berkeley one too.
"""
import re
import urllib.request

URL = "https://alamedacountyca.gov/rovresults/{eid}/"
UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124.0 Safari/537.36")

RACE_SPLIT = re.compile(r"<!--\s*Start Race:\s*(.*?)\s*-->", re.I | re.S)
ROW = re.compile(r"<TH[^>]*class=\"resultsRow[^\"]*\"[^>]*>(.*?)</TH>\s*"
                 r"<TD[^>]*>(.*?)</TD>\s*<TD[^>]*>(.*?)</TD>", re.I | re.S)
BODY_END = re.compile(r'<div[^>]*class="backtotop"|Back to Top', re.I)
_DIV = lambda cls: re.compile(r"<div[^>]*class=\"" + cls + r"[^\"]*\"[^>]*>(.*?)</div>",
                              re.I | re.S)
REPORTED, PASSING, VOTEFOR = _DIV("reported"), _DIV("passing"), _DIV("votefor")

STATUS_RE = re.compile(r"(Preliminary/Unofficial[^<]*)", re.I)
UPDATED_RE = re.compile(r"lastUpdated[^>]*>\s*<span>\s*Last Updated:\s*([^<]+)", re.I)
REG_RE = re.compile(r"Total Registration:\s*([\d,]+)", re.I)
CAST_RE = re.compile(r"Total Ballots Cast[^\d]*([\d,]+)[^\d]*([\d.]+)\s*%", re.I | re.S)
PCTS_RE = re.compile(r"(\d[\d,]*)\s+of\s+(\d[\d,]*)\s+Precincts[^(]*\(([\d.]+)%\)", re.I)
SCHED_RE = re.compile(r"(?:Mon|Tues|Wednes|Thurs|Fri|Satur|Sun)day,\s+"
                      r"(?:January|February|March|April|May|June|July|August|September|"
                      r"October|November|December)\s+\d{1,2},\s+\d{4}", re.I)

PROPS_BLOCK = re.compile(r'id="panelDtlProps".*?</TABLE>', re.I | re.S)
PROP_ROW = re.compile(r'<TH[^>]*class="resultsRow[^"]*"[^>]*>(.*?)</TH>\s*'
                      r'<TD[^>]*>(.*?)</TD>\s*<TD[^>]*>(.*?)</TD>\s*'
                      r'<TD[^>]*>(.*?)</TD>\s*<TD[^>]*>(.*?)</TD>', re.I | re.S)

YESNO = re.compile(r"(bonds\s+)?(yes|no)", re.I)


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


def fetch(eid=None, url=None, timeout=120):
    req = urllib.request.Request(url or URL.format(eid=eid), headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read().decode("utf-8", "replace")


def banner(html):
    """Status, last-updated stamp, countywide registration/turnout, next releases."""
    ms, mu = STATUS_RE.search(html), UPDATED_RE.search(html)
    head = html[:html.lower().find("start race")] if "start race" in html.lower() else html
    mr, mc, mp = REG_RE.search(head), CAST_RE.search(head), PCTS_RE.search(head)
    out = {
        "status": txt(ms.group(1)) if ms else "Preliminary/Unofficial",
        "last_updated": txt(mu.group(1)) if mu else "",
        "registered": as_int(mr.group(1)) if mr else 0,
        "ballots_cast": as_int(mc.group(1)) if mc else 0,
        "turnout_pct": float(mc.group(2)) if mc else 0.0,
    }
    if mp:
        out["precincts_reported"] = as_int(mp.group(1))
        out["precincts_total"] = as_int(mp.group(2))
        out["precincts_reported_pct"] = float(mp.group(3))
    sched = SCHED_RE.findall(txt(head))
    out["next_updates"] = [d for d in dict.fromkeys(sched)
                           if d.lower() not in out["last_updated"].lower()]
    return out


def props(html):
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


def races(html):
    """Every contest the portal emits as a race, plus the propositions table."""
    out = []
    parts = RACE_SPLIT.split(html)
    for i in range(1, len(parts) - 1, 2):
        name, body = txt(parts[i]), BODY_END.split(parts[i + 1])[0]
        rows = [{"choice": txt(ch), "votes": as_int(v), "pct": as_pct(p)}
                for ch, v, p in ROW.findall(body) if txt(ch)]
        if not rows:
            continue
        e = {"name": re.sub(r"\s*\(RCV\)\s*$", "", name).strip(),
             "rcv": "(RCV)" in name,
             "kind": "measure" if any(YESNO.fullmatch(r["choice"]) for r in rows)
                     else "candidate",
             "choices": rows,
             "total_votes": sum(r["votes"] for r in rows)}
        for key, rx in (("reported", REPORTED), ("threshold", PASSING), ("vote_for", VOTEFOR)):
            m = rx.search(body)
            if m:
                e[key] = txt(m.group(1))
        seats = re.search(r"Vote for no more than\s+\w+\s*\((\d+)\)", e.get("vote_for", ""), re.I)
        if seats:
            e["seats"] = int(seats.group(1))
        out.append(e)
    out.extend(props(html))
    return out


def parse(html):
    return banner(html), races(html)
