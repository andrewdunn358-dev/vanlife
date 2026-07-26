#!/usr/bin/env python3
"""
Generate the static site from the site research records.

No dependencies, no server, no build step beyond running this. Output is
plain HTML in site/ - drop it on any hosting, including free shared.

Design note: the subject here is regulatory evidence, not travel
romance, so the treatment borrows from parking signage and statutory
notices rather than from every other vanlife site. The signature is that
the site foregrounds what it does not know - completeness is stated
plainly on every page, because a legality product that hides its gaps is
the dangerous kind.

    python3 scripts/build_site.py
    python3 scripts/build_site.py --out site
"""
import argparse
import glob
import html
import json
import os
import shutil
import urllib.parse
from collections import Counter
from datetime import date

CSS = """
:root {
  --ink: #1A1815;
  --ink-soft: #56524C;
  --paper: #FBFAF8;
  --rule: #D8D4CC;
  --permit: #1F5C3D;
  --restrict: #A8620F;
  --unknown: #6B6864;
  --sign: #0B3C7A;
  --measure: 66ch;
}
* { box-sizing: border-box; }
html { -webkit-text-size-adjust: 100%; }
body {
  margin: 0;
  background: var(--paper);
  color: var(--ink);
  font-family: "Source Serif 4", Georgia, serif;
  font-size: 17px;
  line-height: 1.55;
}
.wrap { max-width: 74ch; margin: 0 auto; padding: 0 1.25rem 5rem; }

/* masthead ------------------------------------------------------------ */
.masthead { border-bottom: 3px solid var(--ink); margin-bottom: 0; padding: 2.5rem 0 1rem; }
.masthead a { color: inherit; text-decoration: none; }
.wordmark {
  font-family: Overpass, "Helvetica Neue", Arial, sans-serif;
  font-weight: 800; font-size: clamp(1.6rem, 5vw, 2.3rem);
  letter-spacing: -0.02em; text-transform: uppercase; margin: 0; line-height: 1;
}
.standfirst {
  font-family: Overpass, Arial, sans-serif; font-size: 0.82rem;
  letter-spacing: 0.09em; text-transform: uppercase;
  color: var(--ink-soft); margin: 0.6rem 0 0;
}

/* the honesty bar ----------------------------------------------------- */
.state {
  font-family: "Overpass Mono", ui-monospace, monospace;
  font-size: 0.78rem; border-bottom: 1px solid var(--rule);
  padding: 0.75rem 0; margin-bottom: 2.5rem;
  display: flex; flex-wrap: wrap; gap: 0 1.5rem; color: var(--ink-soft);
}
.state b { color: var(--ink); font-weight: 600; }
.state .warn { color: var(--restrict); }

/* notices -------------------------------------------------------------- */
.authority { margin: 0 0 3.5rem; }
.authority-head { border-bottom: 1px solid var(--ink); padding-bottom: 0.5rem; margin-bottom: 1.5rem; }
.authority-head h2 {
  font-family: Overpass, Arial, sans-serif; font-weight: 700;
  font-size: 1.35rem; letter-spacing: -0.01em; margin: 0; line-height: 1.2;
}
.authority-head h2 a { color: inherit; text-decoration: none; }
.authority-head h2 a:hover { text-decoration: underline; }
.meta {
  font-family: "Overpass Mono", monospace; font-size: 0.72rem;
  text-transform: uppercase; letter-spacing: 0.06em;
  color: var(--ink-soft); margin: 0.4rem 0 0;
}
.summary { color: var(--ink-soft); margin: 0 0 1.75rem; max-width: var(--measure); }

.notice { border-left: 5px solid var(--unknown); padding: 0 0 0 1rem; margin: 0 0 1.75rem; }
.notice.is-provision { border-left-color: var(--permit); }
.notice.is-restriction { border-left-color: var(--restrict); }
.notice h3 {
  font-family: Overpass, Arial, sans-serif; font-weight: 700;
  font-size: 1rem; margin: 0 0 0.15rem; line-height: 1.3;
}
.kind {
  font-family: "Overpass Mono", monospace; font-size: 0.68rem;
  letter-spacing: 0.11em; text-transform: uppercase; display: block;
  margin-bottom: 0.3rem; color: var(--unknown);
}
.is-provision .kind { color: var(--permit); }
.is-restriction .kind { color: var(--restrict); }

.terms { list-style: none; margin: 0.6rem 0 0; padding: 0;
         font-family: "Overpass Mono", monospace; font-size: 0.78rem; }
.terms li { padding: 0.15rem 0; }
.terms .k { display: inline-block; min-width: 12ch; color: var(--ink-soft); }
.notice p.note { font-size: 0.92rem; color: var(--ink-soft); margin: 0.7rem 0 0; max-width: var(--measure); }

.goto { font-family: "Overpass Mono", monospace; font-size: 0.72rem;
        margin: 0.7rem 0 0; display: flex; flex-wrap: wrap; gap: 0 1rem; align-items: baseline; }
.goto a { color: var(--sign); }
.goto .coords { color: var(--ink-soft); }

.provenance {
  font-family: "Overpass Mono", monospace; font-size: 0.7rem;
  color: var(--ink-soft); border-top: 1px dotted var(--rule);
  margin-top: 0.9rem; padding-top: 0.5rem;
}
.provenance a { color: var(--sign); }
.gap { color: var(--restrict); }

/* index list ----------------------------------------------------------- */
.roll { list-style: none; padding: 0; margin: 0; }
.roll li { border-bottom: 1px solid var(--rule); padding: 0.8rem 0;
           display: flex; justify-content: space-between; gap: 1rem; align-items: baseline; }
.roll a { color: var(--ink); text-decoration: none; font-family: Overpass, Arial, sans-serif;
          font-weight: 600; font-size: 1rem; }
.roll a:hover { text-decoration: underline; }
.roll .tally { font-family: "Overpass Mono", monospace; font-size: 0.72rem;
               color: var(--ink-soft); white-space: nowrap; }

/* map ------------------------------------------------------------------ */
.map-wrap { margin: 0 0 2.5rem; }
#map { height: 380px; border: 1px solid var(--ink); background: var(--rule); }
.map-key {
  font-family: "Overpass Mono", monospace; font-size: 0.7rem;
  color: var(--ink-soft); margin: 0.5rem 0 0;
  display: flex; flex-wrap: wrap; gap: 0 1.25rem;
}
.map-key .dot { display: inline-block; width: 9px; height: 9px; margin-right: 5px; }
.dot.p { background: var(--permit); }
.dot.r { background: var(--restrict); }
.awaiting {
  border: 1px dashed var(--rule); padding: 1.25rem; margin: 0 0 2.5rem;
}
.awaiting h4 {
  font-family: Overpass, Arial, sans-serif; font-size: 0.9rem;
  margin: 0 0 0.5rem; font-weight: 700;
}
.awaiting p { font-size: 0.9rem; color: var(--ink-soft); margin: 0 0 0.75rem; max-width: var(--measure); }
.awaiting ul { font-family: "Overpass Mono", monospace; font-size: 0.76rem;
               margin: 0; padding-left: 1.2rem; color: var(--ink-soft); }
.maplibregl-popup-content {
  font-family: "Overpass Mono", monospace !important; font-size: 0.72rem !important;
  border-radius: 0 !important; border: 1px solid var(--ink); padding: 0.6rem 0.75rem !important;
}
.maplibregl-popup-content b { font-family: Overpass, Arial, sans-serif; font-size: 0.85rem; }

.back { font-family: "Overpass Mono", monospace; font-size: 0.75rem;
        display: inline-block; margin: 2rem 0 0; color: var(--sign); }
footer { border-top: 1px solid var(--rule); margin-top: 3rem; padding-top: 1rem;
         font-family: "Overpass Mono", monospace; font-size: 0.7rem; color: var(--ink-soft); }
a:focus-visible { outline: 2px solid var(--sign); outline-offset: 3px; }
@media (max-width: 30rem) { .terms .k { display: block; min-width: 0; } }
"""

HEAD = """<!DOCTYPE html>
<html lang="en-GB"><head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{title}</title>
<meta name="description" content="{desc}">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Overpass:wght@400;600;700;800&family=Overpass+Mono:wght@400;600&family=Source+Serif+4:opsz,wght@8..60,400;8..60,600&display=swap" rel="stylesheet">
{mapassets}<style>{css}</style>
</head><body><div class="wrap">
<header class="masthead">
  <h1 class="wordmark"><a href="{root}index.html">Overnight</a></h1>
  <p class="standfirst">Where you can stay in a van, and who says so</p>
</header>
"""

MAP_ASSETS = (
    '<link href="https://unpkg.com/maplibre-gl@4.7.1/dist/maplibre-gl.css" rel="stylesheet">\n'
    '<script src="https://unpkg.com/maplibre-gl@4.7.1/dist/maplibre-gl.js"></script>\n'
)

MAP_JS = """<script>
(function () {
  var data = %s;
  if (!data.features.length || typeof maplibregl === "undefined") return;
  var map = new maplibregl.Map({
    container: "map",
    style: { version: 8, sources: { osm: {
      type: "raster",
      tiles: ["https://tile.openstreetmap.org/{z}/{x}/{y}.png"],
      tileSize: 256, attribution: "&copy; OpenStreetMap contributors" } },
      layers: [{ id: "osm", type: "raster", source: "osm" }] },
    center: %s, zoom: %s, attributionControl: { compact: true }
  });
  map.addControl(new maplibregl.NavigationControl({ showCompass: false }), "top-right");
  map.on("load", function () {
    data.features.forEach(function (f) {
      var el = document.createElement("div");
      var permit = f.properties.kind === "provision";
      el.style.cssText = "width:15px;height:15px;border:2px solid #FBFAF8;cursor:pointer;"
        + "background:" + (permit ? "#1F5C3D" : "#A8620F");
      new maplibregl.Marker({ element: el })
        .setLngLat(f.geometry.coordinates)
        .setPopup(new maplibregl.Popup({ offset: 14, closeButton: false })
          .setHTML(f.properties.popup))
        .addTo(map);
    });
    if (data.features.length > 1) {
      var b = new maplibregl.LngLatBounds();
      data.features.forEach(function (f) { b.extend(f.geometry.coordinates); });
      map.fitBounds(b, { padding: 55, maxZoom: 13 });
    }
  });
})();
</script>"""

FOOT = """<footer>
<p>Compiled from published sources. Informational only &mdash; never advice.
Every record shows where it came from and when it was last checked.
Rules change; verify before you rely on this.</p>
<p>Generated {when} &middot; <a href="https://github.com/andrewdunn358-dev/vanlife">source and data</a></p>
</footer>
</div></body></html>"""


def esc(v):
    return html.escape(str(v)) if v is not None else ""


def slug(name):
    keep = "".join(c.lower() if c.isalnum() else "-" for c in name)
    while "--" in keep:
        keep = keep.replace("--", "-")
    return keep.strip("-")


def money(v, cur="GBP"):
    if v is None:
        return None
    sym = {"GBP": "\u00a3", "EUR": "\u20ac"}.get(cur, "")
    return f"{sym}{v:.2f}".replace(".00", "")


def term_rows(s):
    """The operative facts, in the order someone actually needs them."""
    rows = []
    p = money(s.get("price_per_night"), s.get("currency", "GBP"))
    if p:
        label = f"{p} per night"
        if s.get("price_confidence") == "disputed":
            label += "  (disputed)"
        rows.append(("price", label))
    elif s.get("kind") == "provision":
        rows.append(("price", "not recorded"))
    if s.get("arrival_from") or s.get("departure_by"):
        rows.append(("hours", f"{s.get('arrival_from') or '?'} to {s.get('departure_by') or '?'}"))
    if s.get("time_from") or s.get("time_to"):
        rows.append(("in force", f"{s.get('time_from') or '?'} to {s.get('time_to') or '?'}"))
    if s.get("max_nights"):
        n = s["max_nights"]
        rows.append(("max stay", f"{n} night" + ("s" if n != 1 else "")))
    if s.get("bays"):
        rows.append(("bays", str(s["bays"])))
    if s.get("requires_self_contained"):
        rows.append(("vehicle", "self-contained only"))
    if s.get("self_contained_definition"):
        rows.append(("defined as", s["self_contained_definition"]))
    if s.get("restricts"):
        rows.append(("restricts", s["restricts"]))
    if s.get("applies_to") and s["applies_to"] != "unknown":
        rows.append(("applies to", s["applies_to"].replace("_", " ")))
    if s.get("booking"):
        rows.append(("booking", s["booking"].replace("_", " ")))
    if s.get("payment_methods"):
        rows.append(("pay by", ", ".join(s["payment_methods"]).replace("_", " ")))
    if s.get("payment_deferrable"):
        rows.append(("if no signal", f"settle {s.get('payment_grace', 'later')}"))
    if s.get("prohibits"):
        rows.append(("not allowed", ", ".join(s["prohibits"])))
    if s.get("facilities"):
        rows.append(("facilities", ", ".join(s["facilities"])))
    if s.get("enforcement") and s["enforcement"] != "unknown":
        rows.append(("enforced by", s["enforcement"].upper()))
    if s.get("postcode"):
        rows.append(("postcode", s["postcode"]))
    return rows


def site_geojson(records):
    """Only sites with real coordinates. Nothing is invented to fill the map."""
    feats, awaiting = [], []
    for d in records:
        for s in d["sites"]:
            if s.get("lat") is None or s.get("lon") is None:
                awaiting.append((d["authority"], s.get("name", "?")))
                continue
            p = money(s.get("price_per_night"), s.get("currency", "GBP"))
            lines = [f"<b>{esc(s.get('name'))}</b>",
                     esc(d["authority"])]
            if s.get("kind") == "provision":
                lines.append(f"{p} per night" if p else "price not recorded")
            else:
                lines.append("no overnight " + esc(s.get("restricts", "stays")))
            lines.append(f"checked {esc(s.get('last_verified', 'never'))}")
            feats.append({
                "type": "Feature",
                "geometry": {"type": "Point", "coordinates": [s["lon"], s["lat"]]},
                "properties": {"kind": s.get("kind"), "popup": "<br>".join(lines)},
            })
    return {"type": "FeatureCollection", "features": feats}, awaiting


def map_block(gj, awaiting):
    """A map when there is something to map, an honest to-do list when not."""
    if gj["features"]:
        n = len(gj["features"])
        centre = gj["features"][0]["geometry"]["coordinates"] if n == 1 else [-3.2, 54.6]
        zoom = 12 if n == 1 else 5
        out = ['<div class="map-wrap"><div id="map"></div>',
               '<p class="map-key">',
               '<span><span class="dot p"></span>you can stay</span>',
               '<span><span class="dot r"></span>you cannot stay</span>']
        if awaiting:
            out.append(f'<span class="gap">{len(awaiting)} more not yet located</span>')
        out.append("</p></div>")
        out.append(MAP_JS % (json.dumps(gj), json.dumps(centre), zoom))
        return "\n".join(out), True

    out = ['<div class="awaiting">',
           "<h4>No map yet</h4>",
           "<p>None of these records has coordinates, so there is nothing to plot. "
           "Rather than guess at where these car parks are, the map stays off until "
           "the locations have been looked up and checked.</p>",
           f"<p>{len(awaiting)} record" + ("s" if len(awaiting) != 1 else "") +
           " waiting on a location:</p><ul>"]
    for auth, name in awaiting[:12]:
        out.append(f"<li>{esc(name)}</li>")
    if len(awaiting) > 12:
        out.append(f"<li>and {len(awaiting) - 12} more</li>")
    out.append("</ul></div>")
    return "\n".join(out), False


def notice_html(s, parent):
    kind = s.get("kind", "unknown")
    cls = "is-provision" if kind == "provision" else "is-restriction"
    label = "You can stay" if kind == "provision" else "You cannot stay"

    out = [f'<article class="notice {cls}">',
           f'<span class="kind">{label}</span>',
           f'<h3>{esc(s.get("name"))}</h3>']

    rows = term_rows(s)
    if rows:
        out.append('<ul class="terms">')
        for k, v in rows:
            out.append(f'<li><span class="k">{esc(k)}</span>{esc(v)}</li>')
        out.append("</ul>")

    if s.get("notes"):
        out.append(f'<p class="note">{esc(s["notes"])}</p>')

    # Getting there. Deep links, not an embedded map - no keys, no tracking,
    # and it opens in whatever the person already uses.
    if s.get("lat") is not None:
        ll = f"{s['lat']},{s['lon']}"
        out.append(
            '<p class="goto">'
            f'<a href="https://www.google.com/maps/search/?api=1&amp;query={ll}">Google Maps</a>'
            f'<a href="https://maps.apple.com/?ll={ll}&amp;q={urllib.parse.quote(s.get("name",""))}">Apple Maps</a>'
            f'<a href="https://www.openstreetmap.org/?mlat={s["lat"]}&amp;mlon={s["lon"]}#map=17/{s["lat"]}/{s["lon"]}">OpenStreetMap</a>'
            f'<span class="coords">{ll}</span>'
            "</p>")
    elif s.get("postcode"):
        out.append(
            '<p class="goto"><a href="https://www.google.com/maps/search/?api=1&amp;query='
            f'{urllib.parse.quote(s["postcode"])}">Google Maps (postcode only)</a>'
            '<span class="coords gap">exact location not yet recorded</span></p>')

    # Provenance block - the signature. Never hidden, never softened.
    bits = []
    lv = s.get("last_verified")
    bits.append(f"checked {esc(lv)}" if lv else '<span class="gap">never checked</span>')
    conf = s.get("confidence", "unknown")
    bits.append(f"confidence {esc(conf)}")
    st = s.get("status", "unknown")
    bits.append(f"status {esc(st)}")
    inst = s.get("instrument", "unknown")
    bits.append(f"under {esc(inst.replace('_', ' '))}")
    if s.get("lat") is None:
        bits.append('<span class="gap">location not yet recorded</span>')
    elif s.get("geocode_checked") is False:
        bits.append('<span class="gap">location from '
                    + esc(s.get("geocode_precision", "lookup"))
                    + ", not eyeballed</span>")
    srcs = parent.get("sources") or []
    if srcs:
        host = srcs[0].split("/")[2] if "//" in srcs[0] else srcs[0]
        bits.append(f'<a href="{esc(srcs[0])}">{esc(host)}</a>')
    else:
        bits.append('<span class="gap">no source recorded</span>')
    out.append('<p class="provenance">' + " &middot; ".join(bits) + "</p>")
    out.append("</article>")
    return "\n".join(out)


def authority_page(d, out_dir, root="../"):
    name = d["authority"]
    sites = d["sites"]
    prov = sum(1 for s in sites if s.get("kind") == "provision")
    rest = len(sites) - prov
    mappable = sum(1 for s in sites if s.get("lat") is not None)

    gj, awaiting = site_geojson([d])
    mapping, has_map = map_block(gj, awaiting)

    body = [HEAD.format(
        title=f"{html.escape(name)} - overnight parking rules",
        desc=f"Published overnight parking and sleeping rules for {html.escape(name)}, with sources and dates.",
        css=CSS, root=root, mapassets=MAP_ASSETS if has_map else "")]

    body.append('<div class="state">')
    body.append(f"<span><b>{len(sites)}</b> records</span>")
    body.append(f"<span><b>{prov}</b> permitted &middot; <b>{rest}</b> restricted</span>")
    cls = "" if mappable == len(sites) else ' class="warn"'
    body.append(f"<span{cls}><b>{mappable}</b> of {len(sites)} mapped</span>")
    body.append("</div>")

    body.append(mapping)
    body.append('<section class="authority">')
    body.append('<div class="authority-head">')
    body.append(f"<h2>{esc(name)}</h2>")
    body.append(f'<p class="meta">{esc(d.get("authority_type", ""))} &middot; {esc(d.get("nation"))} '
                f'&middot; source format {esc(d.get("source_format", "unknown"))}</p>')
    body.append("</div>")

    if d.get("warning"):
        body.append(f'<p class="summary"><strong class="gap">{esc(d["warning"])}</strong></p>')
    if d.get("policy_summary"):
        body.append(f'<p class="summary">{esc(d["policy_summary"])}</p>')

    for s in sorted(sites, key=lambda x: (x.get("kind") != "provision", x.get("name", ""))):
        body.append(notice_html(s, d))

    if d.get("open_questions"):
        body.append('<p class="meta">Still to find out</p><ul class="terms">')
        for q in d["open_questions"]:
            body.append(f"<li>{esc(q)}</li>")
        body.append("</ul>")

    body.append("</section>")
    body.append(f'<a class="back" href="{root}index.html">&larr; All authorities</a>')
    body.append(FOOT.format(when=date.today().isoformat()))

    path = os.path.join(out_dir, "authority", f"{slug(name)}.html")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    open(path, "w", encoding="utf-8").write("\n".join(body))
    return path


def index_page(records, out_dir):
    total = sum(len(d["sites"]) for d in records)
    prov = sum(1 for d in records for s in d["sites"] if s.get("kind") == "provision")
    mapped = sum(1 for d in records for s in d["sites"] if s.get("lat") is not None)

    gj, awaiting = site_geojson(records)
    mapping, has_map = map_block(gj, awaiting)

    body = [HEAD.format(
        title="Overnight - where you can stay in a van in the UK",
        desc="Published overnight parking and sleeping rules for UK councils, "
             "national parks and landowners. Every record shows its source and date.",
        css=CSS, root="", mapassets=MAP_ASSETS if has_map else "")]

    body.append('<div class="state">')
    body.append(f"<span><b>{len(records)}</b> authorities</span>")
    body.append(f"<span><b>{total}</b> records</span>")
    body.append(f"<span><b>{prov}</b> where you can stay</span>")
    cls = "" if mapped == total else ' class="warn"'
    body.append(f"<span{cls}><b>{mapped}</b> of {total} mapped</span>")
    body.append("</div>")

    body.append("<p class=\"summary\">Councils, national parks, water companies and forestry bodies "
                "all set their own overnight rules, under at least five different kinds of legal power. "
                "This is what they publish, in one place, with the source and the date it was last "
                "checked against every record.</p>")
    body.append("<p class=\"summary\">Where something has not been checked, or the location has not been "
                "recorded yet, the record says so rather than leaving you to guess.</p>")

    body.append(mapping)
    body.append('<ul class="roll">')
    for d in sorted(records, key=lambda x: x["authority"]):
        p = sum(1 for s in d["sites"] if s.get("kind") == "provision")
        r = len(d["sites"]) - p
        body.append(
            f'<li><a href="authority/{slug(d["authority"])}.html">{esc(d["authority"])}</a>'
            f'<span class="tally">{p} permitted &middot; {r} restricted</span></li>')
    body.append("</ul>")
    body.append(FOOT.format(when=date.today().isoformat()))

    path = os.path.join(out_dir, "index.html")
    open(path, "w", encoding="utf-8").write("\n".join(body))
    return path


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", default="data/sites")
    ap.add_argument("--out", default="site")
    args = ap.parse_args()

    files = sorted(glob.glob(os.path.join(args.dir, "*.json")))
    if not files:
        raise SystemExit(f"No records in {args.dir}")

    records = [json.load(open(f, encoding="utf-8")) for f in files]

    if os.path.isdir(args.out):
        shutil.rmtree(args.out)
    os.makedirs(args.out, exist_ok=True)

    for d in records:
        authority_page(d, args.out)
    index_page(records, args.out)

    n = sum(len(d["sites"]) for d in records)
    mapped = sum(1 for d in records for s in d["sites"] if s.get("lat") is not None)
    print(f"built {len(records) + 1} pages in {args.out}/")
    print(f"  {len(records)} authorities, {n} records, {mapped} with coordinates")
    if mapped < n:
        print(f"  {n - mapped} records cannot be mapped until coordinates are added")


if __name__ == "__main__":
    main()
