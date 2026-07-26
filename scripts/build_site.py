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

CSS = None  # loaded from assets/site.css


HEAD = """<!DOCTYPE html>
<html lang="en-GB"><head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{title}</title>
<meta name="description" content="{desc}">
<link rel="icon" href="{root}favicon.svg" type="image/svg+xml">
<link rel="apple-touch-icon" href="{root}favicon.svg">
<meta name="theme-color" content="#2F6A4B">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Space+Grotesk:wght@400;500;700&family=Source+Serif+4:opsz,wght@8..60,400;8..60,600&display=swap" rel="stylesheet">
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
      var n = f.properties.count || 1;
      var size = Math.min(30, 13 + Math.round(Math.sqrt(n) * 3));
      el.style.cssText = "width:" + size + "px;height:" + size + "px;"
        + "border:2px solid #FBFAF8;cursor:pointer;background:"
        + (permit ? "#1F5C3D" : "#A8620F");
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

HOWTO = '<div class="howto">\n<h4>How to read this</h4>\n<dl>\n<dt>You can stay / you cannot stay</dt>\n<dd>Green edges mark places an authority has set aside for overnight stays.\nAmber marks places it has restricted. Neither is advice &mdash; both report\nwhat was published, and the rules change.</dd>\n<dt>Restricts sleeping, or restricts parking?</dt>\n<dd>These are different offences and councils use both. Gwynedd lets you park\nanywhere and sleep almost nowhere. Cornwall has fined people for leaving a\nmotorhome overnight without sleeping in it at all.</dd>\n<dt>Self-contained</dt>\n<dd>Usually a fixed toilet plus sealed containers for waste water and sewage.\nDefinitions vary by authority and there is no UK certification scheme, so it\nis a claim rather than a standard. A converted van with a portable loo often\ndoes not qualify.</dd>\n<dt>The line under each record</dt>\n<dd>Where the information came from, when it was last checked, and what legal\npower it sits under. If it says the location has not been checked, the pin is\na rough lookup rather than the car park entrance.</dd>\n<dt>What this is not</dt>\n<dd>Not complete, not current, and not advice. It covers a handful of\nauthorities so far. Check with the authority before relying on anything here.</dd>\n</dl>\n</div>'

FOOT = """<footer>
<p>Compiled from published sources. Informational only &mdash; never advice.
Every record shows where it came from and when it was last checked.
Rules change; verify before you rely on this.</p>
<p>Generated {when} &middot; <a href="https://github.com/andrewdunn358-dev/vanlife">source and data</a></p>
</footer>
</div></body></html>"""


# Plain English for the schema vocabulary. The site should be readable by
# someone who has never seen the data model.
INSTRUMENT_PLAIN = {
    "off_street_parking_order": ("a parking order",
        "The rules for a council car park. Breaking one gets you a "
        "penalty charge notice, the same as overstaying."),
    "on_street_tro": ("a traffic order",
        "A traffic regulation order covering a road or lay-by rather than "
        "a car park. Also enforced by penalty charge notice."),
    "etro": ("an experimental traffic order",
        "A trial version of a traffic order, usually 18 months, which the "
        "council can then make permanent, change or drop."),
    "pspo": ("a public spaces protection order",
        "An anti-social behaviour power. Breaking one is a criminal "
        "offence with a fixed penalty, and it can reach a court fine. "
        "These run for up to three years and must be renewed."),
    "byelaw": ("a byelaw",
        "A local law, often old, common on beaches and commons."),
    "opening_hours": ("the car park's opening hours",
        "No order at all - the car park is simply shut. You are not "
        "banned from sleeping, you are banned from being there."),
    "landowner_policy": ("the landowner's own rules",
        "Not a law. A condition of entry set by whoever owns the land - a "
        "water company, forestry body or trust. No penalty charge, but "
        "they can require you to leave, and private parking charges may "
        "apply."),
    "policy_only": ("a stated policy",
        "Published guidance rather than a legal instrument. How it would "
        "be enforced is unclear."),
    "unknown": ("an unidentified power",
        "We have not yet established what legal power this sits under."),
}

CONFIDENCE_PLAIN = {
    "high": "from the authority's own published pages",
    "medium": "from a reliable source, but not the authority itself",
    "low": "from news reporting or a third party - treat as a lead, not a fact",
    "very_low": "uncertain, possibly out of date - do not rely on this",
}



ASSETS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "assets")


def asset(name):
    return open(os.path.join(ASSETS, name), encoding="utf-8").read()


def vehicle_picker():
    """Photos when they exist, drawn silhouettes until then.

    Manifest-driven so images can be dropped in one at a time. Any image
    used must have its source and licence recorded alongside it - press
    photos from manufacturers are editorial-use-only and are not safe here.
    """
    man = json.load(open(os.path.join(ASSETS, "vehicles.json"), encoding="utf-8"))
    svgs = json.load(open(os.path.join(ASSETS, "vehicle-svgs.json"), encoding="utf-8"))

    cards, credits = [], []
    for v in man["vehicles"]:
        if v.get("image"):
            art = (f'<img src="vehicles/{esc(v["image"])}" alt="" loading="lazy" '
                   f'width="1200" height="800">')
            if v.get("credit"):
                credits.append(f'{esc(v["name"])}: {esc(v["credit"])}'
                               + (f' ({esc(v["licence"])})' if v.get("licence") else ""))
        else:
            art = svgs.get(v["key"], "")
        cards.append(
            f'  <button class="vcard" data-v="{esc(v["key"])}" role="radio" '
            f'aria-checked="false">\n    {art}\n'
            f'    <span class="vname">{esc(v["name"])}</span>\n'
            f'    <span class="vdim">{v["dims"]}</span>\n  </button>')

    tail = ""
    if credits:
        sources = {c.split(": ", 1)[1] for c in credits}
        if len(sources) == 1:
            tail = f'<p class="vcredit">Vehicle images: {sources.pop()}</p>'
        else:
            tail = ('<p class="vcredit">Vehicle images: '
                    + " &middot; ".join(credits) + "</p>")

    grid = ('<div class="vgrid" role="radiogroup" aria-label="Vehicle type">\n'
            + "\n".join(cards) + "\n</div>" + tail)
    shell = open(os.path.join(ASSETS, "vehicle-picker.html"), encoding="utf-8").read()
    if "<!--VGRID-->" not in shell:
        raise SystemExit("vehicle-picker.html is missing its <!--VGRID--> marker")
    return shell.replace("<!--VGRID-->", grid)


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


def by_area(records):
    """Group authorities under the places they operate in.

    Landowners span several counties and a council spans one, so this is
    many-to-many rather than a tree. An authority appears under every area
    it covers.
    """
    cfg = json.load(open(os.path.join(ASSETS, "areas.json"), encoding="utf-8"))
    nations = cfg["nations"]
    lookup = cfg["authorities"]

    areas = {}
    unmapped = []
    for d in records:
        # config first, then any areas set on the record itself
        a = lookup.get(d["authority"]) or d.get("areas")
        if not a:
            unmapped.append(d["authority"])
            a = ["Unassigned"]
        for area in a:
            areas.setdefault(area, []).append(d)
    if unmapped:
        print("  no area mapped for: " + ", ".join(unmapped))

    regions = cfg.get("regions", {})
    grouped = {}
    for area, docs in areas.items():
        region = regions.get(area) or nations.get(area, "Elsewhere")
        grouped.setdefault(region, {})[area] = sorted(
            docs, key=lambda x: x["authority"])
    return grouped


def region_page(region, counties, out_dir, blurb="", all_counties=None):
    """Counties within a region.

    Lists every county, not only the researched ones. A region page showing
    two counties when it has four implies coverage that does not exist, and
    the gaps double as the to-do list.
    """
    n_auth = len({d["authority"] for docs in counties.values() for d in docs})
    n_rec = sum(len(d["sites"]) for docs in counties.values() for d in docs)
    todo = [c for c in (all_counties or []) if c not in counties]

    body = [HEAD.format(
        title=f"Staying overnight in the {html.escape(region)} in a van",
        desc=f"Overnight parking and sleeping rules across the {html.escape(region)}, "
             "county by county, from councils, national parks and landowners.",
        css=asset("site.css"), root="../", mapassets="")]

    total = len(counties) + len(todo)
    body.append('<div class="state">')
    body.append(f"<span><b>{len(counties)}</b> of {total} counties covered</span>")
    body.append(f"<span><b>{n_auth}</b> bodies</span>")
    body.append(f"<span><b>{n_rec}</b> records</span>")
    body.append("</div>")

    body.append(f'<div class="authority-head"><h2>{esc(region)}</h2></div>')
    if blurb:
        body.append(f'<p class="summary">{esc(blurb)}</p>')

    body.append('<ul class="roll">')
    for county in sorted(counties):
        docs = counties[county]
        recs = sum(len(d["sites"]) for d in docs)
        prov = sum(1 for d in docs for s in d["sites"] if s.get("kind") == "provision")
        body.append(
            f'<li><a href="../area/{slug(county)}.html">{esc(county)}'
            f'<span class="rollsub">'
            + ", ".join(esc(d["authority"]) for d in docs[:3])
            + (f" and {len(docs) - 3} more" if len(docs) > 3 else "")
            + "</span></a>"
            f'<span class="tally">{prov} of {recs} permitted</span></li>')
    body.append("</ul>")

    if todo:
        body.append('<h3 class="nation">Not looked at yet</h3>')
        body.append('<p class="summary">These counties have not been researched. '
                    'That is a gap in this site, not a sign there are no rules '
                    'there &mdash; assume there are.</p>')
        body.append('<ul class="todo">')
        for c in todo:
            body.append(f'<li><a href="../area/{slug(c)}.html">{esc(c)}</a></li>')
        body.append("</ul>")

    body.append('<a class="back" href="../index.html">&larr; All regions</a>')
    body.append(FOOT.format(when=date.today().isoformat()))

    path = os.path.join(out_dir, "region", f"{slug(region)}.html")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    open(path, "w", encoding="utf-8").write("\n".join(body))
    return path


def empty_area_page(area, out_dir, region=None):
    """A county nobody has researched yet.

    Generated for every county so the URL exists from the start and the
    gap is visible rather than implied. It says plainly that silence here
    means nobody has looked, not that there are no rules.
    """
    body = [HEAD.format(
        title=f"Staying overnight in {html.escape(area)} in a van",
        desc=f"Overnight parking and sleeping rules in {html.escape(area)}. "
             "Not yet researched.",
        css=asset("site.css"), root="../", mapassets="")]

    body.append('<div class="state">')
    body.append('<span class="warn"><b>0</b> records</span>')
    body.append("<span>not researched yet</span>")
    body.append("</div>")

    body.append(f'<div class="authority-head"><h2>{esc(area)}</h2>'
                f'<p class="meta">nothing recorded</p></div>')

    body.append('<div class="awaiting"><h4>Nobody has looked here yet</h4>'
                "<p>There is no information about " + esc(area) + " on this site. "
                "That is a gap in the research, not a finding &mdash; assume there "
                "are rules and check with the authority before you rely on "
                "anything.</p>"
                "<p>Somewhere like this will usually have a council setting rules "
                "for its own car parks, possibly a national park authority with its "
                "own, and landowners such as water companies, Forestry England or "
                "the National Trust, each with a different position. They rarely "
                "agree.</p></div>")

    if region:
        body.append(f'<a class="back" href="../region/{slug(region)}.html">'
                    f'&larr; {esc(region)}</a>')
    body.append(FOOT.format(when=date.today().isoformat()))

    path = os.path.join(out_dir, "area", f"{slug(area)}.html")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    open(path, "w", encoding="utf-8").write("\n".join(body))
    return path


def area_page(area, docs, out_dir, region=None):
    """Everything that governs one place, whoever owns it.

    The most useful page on the site: a council, a national park, a water
    company and a forestry body all set rules in Northumberland, and no
    one publishes them together.
    """
    sites = []
    for d in docs:
        for s in d["sites"]:
            sites.append((d, s))
    prov = sum(1 for _d, s in sites if s.get("kind") == "provision")
    gj, awaiting = site_geojson(docs)
    mapping, has_map = map_block(gj, awaiting)

    body = [HEAD.format(
        title=f"Staying overnight in {html.escape(area)} in a van",
        desc=f"Overnight parking and sleeping rules across {html.escape(area)} - "
             "councils, national parks, water companies and landowners in one place.",
        css=asset("site.css"), root="../", mapassets=MAP_ASSETS if has_map else "")]

    body.append('<div class="state">')
    body.append(f"<span><b>{len(docs)}</b> bodies set rules here</span>")
    body.append(f"<span><b>{len(sites)}</b> records</span>")
    body.append(f"<span><b>{prov}</b> where you can stay</span>")
    body.append("</div>")

    body.append(f'<div class="authority-head"><h2>{esc(area)}</h2>'
                f'<p class="meta">{len(docs)} authorities and landowners</p></div>')
    body.append('<p class="vstrip" id="vstrip" data-home="../index.html"></p>')
    body.append(mapping)

    body.append("<p class=\"summary\">Different bodies own different land here, and "
                "they do not follow the same rules. A council car park, a national park "
                "car park and a reservoir car park a mile apart can each have a "
                "different answer.</p>")

    body.append('<ul class="roll">')
    for d in docs:
        p = sum(1 for s in d["sites"] if s.get("kind") == "provision")
        r = len(d["sites"]) - p
        kind = d.get("authority_type", "")
        body.append(
            f'<li><a href="../authority/{slug(d["authority"])}.html">'
            f'{esc(d["authority"])}'
            f'<span class="rollsub">{esc(kind)}</span></a>'
            f'<span class="tally">{p} permitted &middot; {r} restricted</span></li>')
    body.append("</ul>")

    body.append("<script>" + asset("vehicle.js") + "</script>")
    if region:
        body.append(f'<a class="back" href="../region/{slug(region)}.html">'
                    f'&larr; {esc(region)}</a>')
    else:
        body.append('<a class="back" href="../index.html">&larr; All regions</a>')
    body.append(FOOT.format(when=date.today().isoformat()))

    path = os.path.join(out_dir, "area", f"{slug(area)}.html")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    open(path, "w", encoding="utf-8").write("\n".join(body))
    return path


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


def authority_geojson(records):
    """One marker per authority, not per site.

    Site-level pins do not scale - 428 authorities with a handful of
    records each would be thousands of overlapping markers. At authority
    level the map answers a different and more useful question: where is
    provision, and where is there only restriction.
    """
    feats, unplaced = [], []
    for d in records:
        pts = [(s["lat"], s["lon"]) for s in d["sites"] if s.get("lat") is not None]
        if not pts:
            unplaced.append(d["authority"])
            continue
        lat = sum(p[0] for p in pts) / len(pts)
        lon = sum(p[1] for p in pts) / len(pts)
        prov = sum(1 for s in d["sites"] if s.get("kind") == "provision")
        rest = len(d["sites"]) - prov
        posture = "provides" if prov else "restricts"
        feats.append({
            "type": "Feature",
            "geometry": {"type": "Point", "coordinates": [lon, lat]},
            "properties": {
                "kind": "provision" if prov else "restriction",
                "posture": posture,
                "count": len(d["sites"]),
                "popup": (f"<b>{esc(d['authority'])}</b><br>"
                          f"{prov} where you can stay<br>"
                          f"{rest} restricted<br>"
                          f"<a href='authority/{slug(d['authority'])}.html'>see the records</a>"),
            },
        })
    return {"type": "FeatureCollection", "features": feats}, unplaced


def map_block(gj, awaiting):
    """A map when there is something to map, an honest to-do list when not."""
    if gj["features"]:
        n = len(gj["features"])
        centre = gj["features"][0]["geometry"]["coordinates"] if n == 1 else [-3.2, 54.6]
        zoom = 12 if n == 1 else 5
        n = len(gj["features"])
        authority_level = "posture" in (gj["features"][0]["properties"])
        out = ['<div class="map-wrap"><div id="map"></div>',
               '<p class="map-key">']
        if authority_level:
            out += ['<span><span class="dot p"></span>provides somewhere to stay</span>',
                    '<span><span class="dot r"></span>restricts only</span>',
                    '<span>marker size shows how many records</span>']
        else:
            out += ['<span><span class="dot p"></span>you can stay</span>',
                    '<span><span class="dot r"></span>you cannot stay</span>']
        if awaiting:
            label = ("authorities with no located records" if authority_level
                     else "more not yet located")
            out.append(f'<span class="gap">{len(awaiting)} {label}</span>')
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

    rule = {"kind": kind}
    if s.get("requires_self_contained"):
        rule["self_contained"] = True
    if s.get("applies_to"):
        rule["applies_to"] = s["applies_to"]
    if s.get("restricts"):
        rule["restricts"] = s["restricts"]
    ex = [str(x).lower() for x in (s.get("excludes_vehicle_types") or [])]
    ex += [str(x).lower() for x in (s.get("prohibits") or [])]
    if any("caravan" in x for x in ex):
        rule["excludes_caravans"] = True
    if s.get("max_length_m"):
        rule["max_length"] = s["max_length_m"]
    for src in ("max_height_m", "osm_maxheight"):
        if s.get(src):
            try:
                rule["max_height"] = float(str(s[src]).replace("m", "").strip())
            except ValueError:
                pass
    attr = html.escape(json.dumps(rule), quote=True)

    out = [f'<article class="notice {cls}" data-rec="{attr}">',
           f'<span class="kind">{label}</span>',
           f'<h3>{esc(s.get("name"))}</h3>']

    rows = term_rows(s)
    if rows:
        out.append('<ul class="terms">')
        for k, v in rows:
            out.append(f'<li><span class="k">{esc(k)}</span><span class="v">{esc(v)}</span></li>')
        out.append("</ul>")

    inst = s.get("instrument", "unknown")
    if inst in INSTRUMENT_PLAIN and inst != "unknown":
        _p, why = INSTRUMENT_PLAIN[inst]
        if why:
            out.append(f'<p class="explain">{esc(why)}</p>')

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
    bits.append(esc(CONFIDENCE_PLAIN.get(conf, f"confidence {conf}")))
    st = s.get("status", "unknown")
    bits.append("status " + esc(st.replace("_", " ")))
    inst = s.get("instrument", "unknown")
    plain, _why = INSTRUMENT_PLAIN.get(inst, (inst.replace("_", " "), ""))
    bits.append(f"under {esc(plain)}")
    if s.get("lat") is None:
        bits.append('<span class="gap">location not yet recorded</span>')
    elif s.get("geocode_checked") is False:
        band = s.get("geocode_band", "unknown")
        wording = {
            "precise": "location auto-matched, not yet checked",
            "nearby": "location approximate, near not at",
            "road": "location is a point on the road, not the car park",
            "area": "location is an area centroid - likely wrong",
        }.get(band, "location auto-matched, not yet checked")
        bits.append(f'<span class="gap">{wording}</span>')
    srcs = parent.get("sources") or []
    if srcs:
        host = srcs[0].split("/")[2] if "//" in srcs[0] else srcs[0]
        bits.append(f'<a href="{esc(srcs[0])}">{esc(host)}</a>')
    else:
        bits.append('<span class="gap">no source recorded</span>')
    out.append('<p class="provenance">' + " &middot; ".join(bits) + "</p>")
    out.append('<div class="yours"></div>')
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
        css=asset("site.css"), root=root, mapassets=MAP_ASSETS if has_map else "")]

    body.append('<div class="state">')
    body.append(f"<span><b>{len(sites)}</b> records</span>")
    body.append(f"<span><b>{prov}</b> permitted &middot; <b>{rest}</b> restricted</span>")
    cls = "" if mappable == len(sites) else ' class="warn"'
    body.append(f"<span{cls}><b>{mappable}</b> of {len(sites)} mapped</span>")
    body.append("</div>")

    body.append('<p class="vstrip" id="vstrip" data-home="../index.html"></p>')
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
    body.append("<script>" + asset("vehicle.js") + "</script>")
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

    gj, unplaced = authority_geojson(records)
    _sgj, awaiting = site_geojson(records)
    mapping, has_map = map_block(gj, unplaced)

    body = [HEAD.format(
        title="Overnight - where you can stay in a van in the UK",
        desc="Published overnight parking and sleeping rules for UK councils, "
             "national parks and landowners. Every record shows its source and date.",
        css=asset("site.css"), root="", mapassets=MAP_ASSETS if has_map else "")]

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

    body.append(vehicle_picker())
    body.append(mapping)
    body.append(HOWTO)
    cfg = json.load(open(os.path.join(ASSETS, "areas.json"), encoding="utf-8"))
    order = cfg.get("region_order", [])
    blurbs = cfg.get("region_blurb", {})
    grouped = by_area(records)

    body.append('<h3 class="nation">Where are you going?</h3>')
    body.append('<ul class="roll">')
    all_counties = cfg.get("counties", {})
    seen = [r for r in order if r in grouped or r in all_counties] + \
           [r for r in sorted(grouped) if r not in order]
    for region in seen:
        counties = grouped.get(region, {})
        known = all_counties.get(region, [])
        recs = sum(len(d["sites"]) for docs in counties.values() for d in docs)
        prov = sum(1 for docs in counties.values() for d in docs
                   for s in d["sites"] if s.get("kind") == "provision")
        sub = blurbs.get(region) or ", ".join(sorted(counties)[:4])
        total = len(known) or len(counties)
        tally = (f"{len(counties)} of {total} "
                 + ("county" if total == 1 else "counties")
                 + (f" &middot; {prov} of {recs} permitted" if recs else ""))
        cls = "" if counties else ' class="dim"'
        body.append(
            f'<li{cls}><a href="region/{slug(region)}.html">{esc(region)}'
            f'<span class="rollsub">{esc(sub)}</span></a>'
            f'<span class="tally">{tally}</span></li>')
    body.append("</ul>")
    body.append("<script>" + asset("vehicle.js") + "</script>")
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

    shutil.copy(os.path.join(ASSETS, "favicon.svg"),
                os.path.join(args.out, "favicon.svg"))

    src = os.path.join(os.path.dirname(ASSETS), "..", "site-assets", "vehicles")
    src = os.path.normpath(src)
    if os.path.isdir(src):
        dst = os.path.join(args.out, "vehicles")
        shutil.copytree(src, dst)
        n = len([f for f in os.listdir(dst) if not f.startswith(".")])
        print(f"copied {n} vehicle image(s) into {dst}")

    cfg = json.load(open(os.path.join(ASSETS, "areas.json"), encoding="utf-8"))
    blurbs = cfg.get("region_blurb", {})
    grouped = by_area(records)
    areas = regions = 0
    all_counties = cfg.get("counties", {})
    for region in set(list(grouped) + list(all_counties)):
        counties = grouped.get(region, {})
        region_page(region, counties, args.out, blurbs.get(region, ""),
                    all_counties.get(region, []))
        regions += 1
        for area, docs in counties.items():
            area_page(area, docs, args.out, region)
            areas += 1
        for area in all_counties.get(region, []):
            if area not in counties:
                empty_area_page(area, args.out, region)
                areas += 1

    for d in records:
        authority_page(d, args.out)
    index_page(records, args.out)

    n = sum(len(d["sites"]) for d in records)
    mapped = sum(1 for d in records for s in d["sites"] if s.get("lat") is not None)
    print(f"built {len(records) + areas + regions + 1} pages in {args.out}/ "
          f"({regions} regions, {areas} counties, {len(records)} authorities)")
    print(f"  {len(records)} authorities, {n} records, {mapped} with coordinates")
    if mapped < n:
        print(f"  {n - mapped} records cannot be mapped until coordinates are added")


if __name__ == "__main__":
    main()
