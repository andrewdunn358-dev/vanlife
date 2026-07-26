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

ENDPOINTS = [
    "https://overpass-api.de/api/interpreter",
    "https://overpass.kumi.systems/api/interpreter",
]
UA = "vanlife-dev/0.1 (github.com/andrewdunn358-dev/vanlife)"

AREA_QUERY = """
[out:json][timeout:180];
area["name"="%s"]["boundary"="administrative"]->.a;
(
  node["amenity"="parking"](area.a);
  way["amenity"="parking"](area.a);
  relation["amenity"="parking"](area.a);
);
out tags center;
"""

BBOX_QUERY = """
[out:json][timeout:180];
(
  node["amenity"="parking"](%s);
  way["amenity"="parking"](%s);
  relation["amenity"="parking"](%s);
);
out tags center;
"""


def run_query(q):
    body = urllib.parse.urlencode({"data": q}).encode()
    last = None
    for url in ENDPOINTS:
        try:
            req = urllib.request.Request(url, data=body, headers={"User-Agent": UA})
            with urllib.request.urlopen(req, timeout=200) as r:
                return json.loads(r.read().decode())
        except Exception as exc:  # noqa: BLE001
            last = exc
            print(f"  {url.split('/')[2]} failed: {exc}", file=sys.stderr)
            time.sleep(2)
    raise SystemExit(f"All Overpass endpoints failed. Last error: {last}")


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
        q = AREA_QUERY % args.area
    else:
        b = args.bbox
        q = BBOX_QUERY % (b, b, b)

    print(f"querying Overpass for {label}...", file=sys.stderr)
    t0 = time.time()
    data = run_query(q)
    els = data.get("elements", [])
    parks = tidy(els, args.operator)

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
