#!/usr/bin/env python3
"""
Pull every car park in an area from OpenStreetMap.

This is the scalable half of locating sites. A geocoder guesses what a
name means and returns village centres; Overpass returns the actual
parking features with their real geometry, and then names get matched
against them.

    python3 scripts/fetch_carparks.py --area Northumberland
    python3 scripts/fetch_carparks.py --bbox 55.0,-2.2,55.8,-1.4
    python3 scripts/fetch_carparks.py --area Gwynedd --operator

Output goes to data/reference/carparks-<area>.json and is reused, since
Overpass is a shared free service and re-querying the same area is rude.

The --operator flag also captures operator and access tags, which is how
you tell a council car park from a supermarket one - and that is what
makes blanket restrictions like "all other council car parks" mappable
at all.
"""
import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

# Global-coverage instances only. Several public Overpass servers hold
# just their own country - overpass.osm.ch will cheerfully report zero
# car parks in Northumberland because Switzerland is all it has.
ENDPOINTS = [
    "https://overpass.kumi.systems/api/interpreter",
    "https://overpass-api.de/api/interpreter",
    "https://overpass.private.coffee/api/interpreter",
]
UA = "vanlife-dev/0.1 (github.com/andrewdunn358-dev/vanlife)"

# Relations are a tiny fraction of car parks and much the most expensive
# part of the query, so they are off unless asked for. Resolving an
# administrative area is also costly - a bounding box is far cheaper and
# is what to reach for when Overpass is busy.
AREA_QUERY = """
[out:json][timeout:%d];
area["name"="%s"]["boundary"="administrative"]->.a;
(
  node["amenity"="parking"](area.a);
  way["amenity"="parking"](area.a);%s
);
out tags center;
"""

BBOX_QUERY = """
[out:json][timeout:%d];
(
  node["amenity"="parking"](%s);
  way["amenity"="parking"](%s);%s
);
out tags center;
"""

RELATION_AREA = '\n  relation["amenity"="parking"](area.a);'
RELATION_BBOX = '\n  relation["amenity"="parking"](%s);'


def run_query(q, attempts=2):
    """Every mirror, twice, with a pause between rounds.

    Overpass is a free shared service. 504 and 429 mean it is busy, not
    that the query is wrong - so back off rather than hammering it.
    """
    body = urllib.parse.urlencode({"data": q}).encode()
    last = None
    for attempt in range(attempts):
        for url in ENDPOINTS:
            host = url.split("/")[2]
            try:
                req = urllib.request.Request(
                    url, data=body, headers={"User-Agent": UA})
                with urllib.request.urlopen(req, timeout=240) as r:
                    print(f"  {host} answered", file=sys.stderr)
                    return json.loads(r.read().decode())
            except urllib.error.HTTPError as exc:
                last = exc
                note = {504: "busy", 429: "rate limited",
                        400: "query rejected"}.get(exc.code, "")
                print(f"  {host}: HTTP {exc.code} {note}", file=sys.stderr)
                if exc.code == 400:
                    raise SystemExit(
                        "Overpass rejected the query itself - retrying will "
                        "not help. Check the area name.")
            except Exception as exc:  # noqa: BLE001
                last = exc
                print(f"  {host}: {exc}", file=sys.stderr)
            time.sleep(1.5)
        if attempt + 1 < attempts:
            print("  all mirrors busy, waiting 20s...", file=sys.stderr)
            time.sleep(20)

    raise SystemExit(
        f"\nEvery Overpass mirror is busy. Last error: {last}\n\n"
        "Options, cheapest first:\n"
        "  1. Wait a few minutes and try again - load varies a lot.\n"
        "  2. Use a bounding box instead of an area. Resolving an\n"
        "     administrative boundary is the expensive part.\n"
        "       --bbox 55.2,-1.8,55.7,-1.4\n"
        "  3. Split a large county into two or three boxes.\n\n"
        "If this becomes routine, download a Geofabrik regional extract\n"
        "once and query it locally instead of asking a free shared\n"
        "service for a whole county every time.")


def tidy(elements, keep_operator):
    """One flat record per car park, centre point only."""
    out = []
    for el in elements:
        tags = el.get("tags", {})
        if el["type"] == "node":
            lat, lon = el.get("lat"), el.get("lon")
        else:
            c = el.get("center") or {}
            lat, lon = c.get("lat"), c.get("lon")
        if lat is None or lon is None:
            continue

        rec = {
            "osm_id": f"{el['type']}/{el['id']}",
            "name": tags.get("name"),
            "lat": round(lat, 6),
            "lon": round(lon, 6),
        }
        if keep_operator:
            for t in ("operator", "access", "fee", "parking", "capacity",
                      "maxstay", "opening_hours", "maxheight"):
                if tags.get(t):
                    rec[t] = tags[t]
        out.append(rec)
    return out


def main():
    ap = argparse.ArgumentParser()
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--area", help="administrative area name, e.g. Northumberland")
    g.add_argument("--bbox", help="south,west,north,east")
    ap.add_argument("--operator", action="store_true",
                    help="also capture operator, access, fee, height limit")
    ap.add_argument("--out-dir", default="data/reference")
    ap.add_argument("--force", action="store_true", help="re-query even if cached")
    ap.add_argument("--relations", action="store_true",
                    help="include parking relations - rare, and much slower")
    ap.add_argument("--timeout", type=int, default=120)
    args = ap.parse_args()

    label = args.area or args.bbox.replace(",", "_")
    slug = "".join(c.lower() if c.isalnum() else "-" for c in label).strip("-")
    path = os.path.join(args.out_dir, f"carparks-{slug}.json")

    if os.path.exists(path) and not args.force:
        d = json.load(open(path, encoding="utf-8"))
        print(f"already have {len(d['carparks']):,} car parks in {path}")
        print("use --force to re-query")
        return

    if args.area:
        rel = RELATION_AREA if args.relations else ""
        q = AREA_QUERY % (args.timeout, args.area, rel)
    else:
        b = args.bbox
        rel = (RELATION_BBOX % b) if args.relations else ""
        q = BBOX_QUERY % (args.timeout, b, b, rel)

    print(f"querying Overpass for {label}...", file=sys.stderr)
    t0 = time.time()
    data = run_query(q)
    els = data.get("elements", [])
    parks = tidy(els, args.operator)

    if not parks:
        raise SystemExit(
            "\nZero car parks returned, which for any populated part of the UK\n"
            "means something is wrong rather than that there are none.\n\n"
            "  - Check the bounding box order: south,west,north,east.\n"
            "    Northumberland coast is roughly 55.2,-1.8,55.7,-1.4\n"
            "  - Check the area name matches an OSM administrative boundary.\n"
            "  - The mirror that answered may hold only its own country.\n\n"
            "Nothing was cached, so just fix and re-run.")

    named = sum(1 for p in parks if p.get("name"))
    os.makedirs(args.out_dir, exist_ok=True)
    json.dump({
        "area": label,
        "fetched": time.strftime("%Y-%m-%d"),
        "source": "OpenStreetMap via Overpass, ODbL",
        "count": len(parks),
        "carparks": parks,
    }, open(path, "w", encoding="utf-8"), indent=1)

    print(f"\n{len(parks):,} car parks in {time.time()-t0:.0f}s")
    print(f"{named:,} have a name ({100.0*named/max(len(parks),1):.0f}%)")
    if args.operator:
        ops = sum(1 for p in parks if p.get("operator"))
        print(f"{ops:,} have an operator tag")
    print(f"\nwritten to {path}")
    print("\nOSM data is ODbL - attribution required if you publish anything derived from it.")


if __name__ == "__main__":
    main()
