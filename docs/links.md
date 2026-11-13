# Links between the maps

*Part of the [Berkeley Precinct Election Map](../README.md) documentation.*

## Moving between the two maps

A Berkeley reader looking at a countywide race — Congress, Governor, a proposition —
usually wants to know how Berkeley compares with everywhere else, and that answer is on
the other map. So when the selected contest is not Berkeley-specific, the Berkeley map's
corner link becomes **"This race countywide →"** and carries the election, contest, mode
and chosen candidate across, instead of dropping the reader on the county map's default
view to find the race again. Berkeley-only contests keep the plain "County map" link,
since the county map does not carry them.

## Shareable links

Both maps keep their full state in the URL hash, so any view can be linked:

```
site/index.html#<election>/<contest>/<mode>[/<choice>][/b-<baseline>][/d<district>]
site/county.html#<election>/<contest>/<mode>[/c-<choice>][/<city>]
```

Embedded on samkp.com the same views are reachable as
`samkp.com/precinct-map.html#<berkeley hash>` and
`samkp.com/precinct-map.html#county/<county hash>`; the embedded map posts its hash to
the parent page, which keeps the address bar in step and answers the map's "copy link"
button with the samkp.com URL. Only that origin is trusted, and only the hash is sent.

**Candidate slugs are written without the party prefix** (`c-lateefah-simon`, not
`c-dem-lateefah-simon`) and read tolerantly, because the county prefixes choices with
the party in some elections and not others — she is `DEM - LATEEFAH SIMON` in the Nov
2024 canvass and plain `Lateefah Simon` in the Nov 2026 results. Without this a link
shared in one cycle would break in the next.

`data/processed/elections.json` is the manifest (id, date, name, source URLs, file paths).
