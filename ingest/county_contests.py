#!/usr/bin/env python3
"""
Which contests belong on the COUNTYWIDE map.

The Berkeley map is about local races. The county map is the opposite: only the
big contests that appear on (nearly) every Alameda County ballot, so a countywide
precinct choropleth is actually meaningful. Every local race is deliberately out —
a city council race shown countywide is 95% empty map.

Categories are toggled by ENABLED below. Adding a category back is a one-line
change and needs no other code edits; re-run ./build_county.sh afterwards.

Contest names drift year to year ("Board of Equalization, 2nd District" vs
"Member, State Board of Equalization, 2nd District"; "U.S. Representative, 13th
Congressional District" vs "U.S. Representative  13th Congressional District"), so
matching is by regex on a normalized name.
"""
import re

# Categories included in the countywide build.
ENABLED = {
    "statewide",     # governor + the other constitutional offices
    "federal",       # president, U.S. Senate, U.S. House
    "proposition",   # state propositions
    "recall",        # the 2021 statewide gubernatorial recall
    "regional",      # measures put to the whole county by a region-wide district
}

# Available but off by default — these are not on every county ballot, or add bulk
# without adding much signal. Add the name to ENABLED to turn one on.
#   "legislative" — State Senate / State Assembly (district-limited)
#   "judicial"    — appellate-justice retention yes/no votes (13 of them in 2022)
#   "county"      — county offices and county measures

PATTERNS = [
    # ---- statewide constitutional offices -------------------------------------
    ("statewide", r"^governor$"),
    ("statewide", r"^lieutenant governor$"),
    ("statewide", r"^secretary of state$"),
    ("statewide", r"^controller$"),                 # NOT "auditor-controller/clerk-recorder"
    ("statewide", r"^treasurer$"),                  # NOT "treasurer/tax collector"
    ("statewide", r"^attorney general$"),           # NOT county "district attorney"
    ("statewide", r"^insurance commissioner$"),
    ("statewide", r"^state superintendent of public instruction$"),
    ("statewide", r"^(member,?\s+)?(state\s+)?board of equalization\b.*"),

    # ---- federal ---------------------------------------------------------------
    ("federal", r"^president and vice president$"),
    ("federal", r"^president of the united states$"),
    # party-specific presidential primaries, e.g. "DEM - Presidential Preference"
    ("federal", r"^[a-z]{2,4}\s*-\s*presidential (preference|candidate preference)$"),
    ("federal", r"^presidential (preference|candidate preference)$"),
    ("federal", r"^(u\.?\s?s\.?|united states)\s+senator\b.*"),
    ("federal", r"^(u\.?\s?s\.?|united states)\s+representative\b.*"),

    # ---- state propositions ----------------------------------------------------
    ("proposition", r"^(state\s+)?proposition\s+\d+.*"),

    # ---- region-wide district measures -----------------------------------------
    # A measure from a district that spans the entire county (and beyond) is on
    # (nearly) every county ballot, so it maps as meaningfully as a state
    # proposition. Matched by exact jurisdiction rather than by a loose "district"
    # rule, because most district measures cover one school or park district and
    # would leave the county map 95% empty. A new region-wide measure needs its own
    # line here — deliberately, so adding one is a decision rather than a side effect.
    ("regional", r"^(bond\s+)?measure\s+\S+\s*-\s*public transit revenue measure district$"),

    # ---- 2021 statewide gubernatorial recall -----------------------------------
    ("recall", r"^recall gavin newsom$"),
    ("recall", r"^to succeed gavin newsom if recalled$"),

    # ---- off by default --------------------------------------------------------
    ("legislative", r"^state senator\b.*"),
    ("legislative", r"^state assembly\b.*"),
    ("judicial", r"^(chief justice|associate justice|presiding justice)\b.*"),
    ("county", r"^(sheriff|assessor|district attorney|auditor-controller|"
               r"treasurer/tax collector|county superintendent|supervisor)\b.*"),
    ("county", r"^(bond\s+)?measure\s+\S+\s*-\s*alameda county$"),
]

COMPILED = [(cat, re.compile(p, re.I)) for cat, p in PATTERNS]


def normalize(name: str) -> str:
    """Collapse whitespace so '...Representative  13th...' matches '..., 13th...'."""
    s = re.sub(r"\s+", " ", str(name)).strip()
    s = re.sub(r"\s*,\s*", ", ", s)
    return s


def category(name: str):
    """Return the contest's category, or None if it is not a county-map contest."""
    n = normalize(name)
    for cat, rx in COMPILED:
        if rx.match(n):
            return cat
    return None


def included(name: str) -> bool:
    return category(name) in ENABLED


# Display order for the contest picker: top-of-ticket first, then props.
CATEGORY_ORDER = ["federal", "statewide", "recall", "proposition", "regional",
                  "legislative", "judicial", "county"]


def sort_key(name: str):
    cat = category(name) or "zzz"
    ci = CATEGORY_ORDER.index(cat) if cat in CATEGORY_ORDER else 99
    n = normalize(name)
    # propositions sort numerically, not lexically (Prop 2 before Prop 13)
    m = re.search(r"proposition\s+(\d+)", n, re.I)
    return (ci, int(m.group(1)) if m else 0, n)


if __name__ == "__main__":
    import sys
    for arg in sys.argv[1:]:
        print(f"{arg!r} -> {category(arg)} (included={included(arg)})")
