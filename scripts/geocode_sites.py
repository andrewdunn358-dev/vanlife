#!/usr/bin/env python3
"""
Look up coordinates for site records that do not have any yet.

Two free sources, in order of reliability:
  postcodes.io  - ONS-derived, exact, unlimited, no key. Used when a
                  record has a postcode.
  Nominatim     - OpenStreetMap. Used otherwise. Rate limited to one
                  request per second per their usage policy, and it
                  needs a real User-Agent.

Neither is Google. Google's geocoding API wants a billing account and
would do no better on UK car parks than the ONS postcode centroids.

Nothing is written without you seeing it first. Run it, read what it
found, then re-run with --write.

    python3 scripts/geocode_sites.py
    python3 scripts/geocode_sites.py --write

A postcode centroid is not a car park. It will usually put you within a
couple of hundred metres, which is fine for a map pin and not fine for
navigation. Records geocoded this way are marked so you know which ones
still want checking against satellite imagery.
"""
import argparse
import glob
import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

UA = "vanlife-dev/0.1 (github.com/andrewdunn358-dev/vanlife)"
NOMINATIM_DELAY = 1.1  # their usage policy: max 1 request/second


def get_json(url):
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=20) as r:
        return json.loads(r.read().decode())


def by_postcode(pc):
    try:
        d = get_json(
            "https://api.postcodes.io/postcodes/"
            + urllib.parse.quote(pc.replace(" ", ""))
        )
        r = d["result"]
        return r["latitude"], r["longitude"], "postcodes.io", "postcode_centroid"
    except Exception:
        return None


def by_name(query):
    try:
        arr = get_json(
            "https://nominatim.openstreetmap.org/search?format=json&limit=1"
            "&countrycodes=gb&q=" + urllib.parse.quote(query)
        )
        if not arr:
            return None
        a = arr[0]
        return (
            float(a["lat"]), float(a["lon"]), "nominatim",
            a.get("type", "match"),
        )
    except Exception:
        return None


BLANKET = ("all other", "various", "county-wide", "elsewhere")

# What Nominatim says it matched tells you how much to trust the pin.
# A car park is a small thing; most OSM features are not.
PRECISION = {
    "parking": ("precise", "a car park"),
    "car_park": ("precise", "a car park"),
    "parking_space": ("precise", "a parking space"),
    "castle": ("nearby", "the castle itself"),
    "attraction": ("nearby", "the attraction"),
    "building": ("nearby", "a building"),
    "picnic_site": ("nearby", "a picnic site"),
    "secondary": ("road", "a point on the road"),
    "tertiary": ("road", "a point on the road"),
    "residential": ("road", "a point on the road"),
    "unclassified": ("road", "a point on the road"),
    "service": ("road", "a service road"),
    "track": ("road", "a track"),
    "water": ("area", "the middle of the water"),
    "reservoir": ("area", "the middle of the reservoir"),
    "administrative": ("area", "a boundary centroid"),
    "town": ("area", "the town centre"),
    "village": ("area", "the village centre"),
    "hamlet": ("area", "the hamlet centre"),
    "suburb": ("area", "the suburb centre"),
    "proposed": ("area", "something marked proposed in OSM"),
    "postcode_centroid": ("nearby", "the postcode centroid"),
}


def grade(osm_type):
    return PRECISION.get(osm_type, ("unknown", f"OSM type {osm_type}"))

# Words that make an authority name useless as geographic context.
ORG_WORDS = re.compile(
    r"\b(county|borough|city|district|council|authority|national park|"
    r"water|forestry|england|scotland|wales|trust|comhairle|cyngor|nan)\b",
    re.I)


def queries(site, d):
    """Progressively looser searches, best first.

    The authority is only useful as context when it is named after a place -
    'Gwynedd' helps, 'Northumbrian Water' does not. A landowner's name tells
    Nominatim nothing, so fall back to the region instead.
    """
    name = (site.get("name") or "").strip()
    base = re.sub(r"\s*\([^)]*\)", "", name).strip()
    region = d.get("region") or d.get("nation") or "UK"
    out = []

    if site.get("search_hint"):
        out.append((site["search_hint"], "hint"))

    place = ORG_WORDS.sub("", d["authority"]).strip(" ,-")
    if len(place) > 3:
        out.append((f"{base}, {place}", "named"))

    out.append((f"{base}, {region}", "named"))
    out.append((base, "named"))

    # "Links Road Car Park, Bamburgh" -> try the settlement with the feature,
    # then the settlement alone. The latter is a village centre, not a car
    # park, so it is marked as such.
    if "," in base:
        head, tail = base.rsplit(",", 1)
        head, tail = head.strip(), tail.strip()
        out.append((f"{head}, {tail}, {region}", "named"))
        out.append((tail, "settlement_only"))

    seen, uniq = set(), []
    for q, prec in out:
        k = q.lower()
        if k not in seen and len(q) > 3:
            seen.add(k)
            uniq.append((q, prec))
    return uniq


def searchable(site):
    """Blanket restrictions have no single location and must not get a pin."""
    name = (site.get("name") or "").lower()
    return not any(p in name for p in BLANKET)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", default="data/sites")
    ap.add_argument("--write", action="store_true")
    args = ap.parse_args()

    files = sorted(glob.glob(os.path.join(args.dir, "*.json")))
    if not files:
        sys.exit(f"No records in {args.dir}")

    total = found = skipped = 0

    for path in files:
        d = json.load(open(path, encoding="utf-8"))
        changed = False

        for s in d["sites"]:
            if s.get("lat") is not None:
                continue
            total += 1

            if not searchable(s):
                print(f"  --  {s['name'][:52]:<54} blanket - no single location")
                skipped += 1
                continue

            hit = None
            if s.get("postcode"):
                hit = by_postcode(s["postcode"])
                if hit:
                    hit = (hit[0], hit[1], hit[2], "postcode_centroid", "nearby")
                    print(f"  ~   {s['name'][:52]:<54} {hit[0]:.5f},{hit[1]:.5f}"
                          f"  nearby - postcode {s['postcode']} centroid")

            if not hit:
                for q, prec in queries(s, d):
                    r = by_name(q)
                    time.sleep(NOMINATIM_DELAY)
                    if r:
                        osm_type = r[3]
                        band, what = grade(osm_type)
                        hit = (r[0], r[1], "nominatim", osm_type, band)
                        flag = {"precise": "OK", "nearby": "~ ",
                                "road": "~ ", "area": "!!"}.get(band, "??")
                        print(f"  {flag}  {s['name'][:52]:<54} "
                              f"{hit[0]:.5f},{hit[1]:.5f}  {band} - {what}")
                        break

            if not hit:
                print(f"  --  {s['name'][:52]:<54} not found")
                continue

            found += 1
            if args.write:
                s["lat"] = round(hit[0], 6)
                s["lon"] = round(hit[1], 6)
                s["geocoded_by"] = hit[2]
                s["geocode_precision"] = hit[3]
                s["geocode_band"] = hit[4]
                s["geocode_checked"] = False
                changed = True

        if changed:
            json.dump(d, open(path, "w", encoding="utf-8"), indent=2, ensure_ascii=False)

    print(f"\n{total} without coordinates: {found} found, "
          f"{skipped} blanket, {total - found - skipped} not found")

    if found and not args.write:
        print("\nNothing written. Re-run with --write to save these.")
    elif found:
        print("\nWritten, all marked geocode_checked: false.")
        print("\nKey:  OK precise   ~ close but not the car park   !! wrong kind of thing")
        print("\nNothing here is a car park entrance. Open each on satellite imagery,")
        print("drag the pin to the actual entrance, and set geocode_checked to true.")
        print("The !! ones are worst - a reservoir centroid is in the middle of the water.")


if __name__ == "__main__":
    main()
