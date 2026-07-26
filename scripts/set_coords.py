#!/usr/bin/env python3
"""
Set verified coordinates on a site record.

Editing JSON with sed goes wrong quietly. This finds the record by a
fragment of its name, writes the coordinates, marks it as checked by a
human, and clears the machine-geocoding fields that no longer apply.

    python3 scripts/set_coords.py fontburn 55.23751 -1.92448
    python3 scripts/set_coords.py "arosfan llanberis" 53.1201 -4.1279

Paste coordinates straight from Google Maps - right-click the spot, then
click the numbers at the top of the menu to copy them. Both orders work:
if you give them the wrong way round for the UK, it says so rather than
putting your car park in the Indian Ocean.

    python3 scripts/set_coords.py --list        # what still needs doing
"""
import argparse
import glob
import json
import os
import sys

# Generous box around the UK and Ireland.
UK = (-11.0, 49.5, 2.2, 61.2)  # W, S, E, N


def load_all(d):
    return [(p, json.load(open(p, encoding="utf-8")))
            for p in sorted(glob.glob(os.path.join(d, "*.json")))]


def find(records, fragment):
    frag = fragment.lower().strip()
    hits = []
    for path, doc in records:
        for site in doc["sites"]:
            if frag in site.get("name", "").lower():
                hits.append((path, doc, site))
    return hits


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("name", nargs="?", help="part of the site name")
    ap.add_argument("lat", nargs="?", type=float)
    ap.add_argument("lon", nargs="?", type=float)
    ap.add_argument("--dir", default="data/sites")
    ap.add_argument("--list", action="store_true", help="show what needs checking")
    args = ap.parse_args()

    records = load_all(args.dir)

    if args.list or not args.name:
        print("\nNot yet checked by a human:\n")
        for _p, doc in records:
            for s in doc["sites"]:
                if s.get("lat") is None:
                    if "all other" in s["name"].lower() or "various" in s["name"].lower():
                        continue
                    print(f"  {'no location':<22} {s['name']}")
                elif s.get("geocode_checked") is False:
                    band = s.get("geocode_band", "?")
                    print(f"  {band:<22} {s['name']}  "
                          f"({s['lat']:.5f}, {s['lon']:.5f})")
        print("\nTo fix one:  python3 scripts/set_coords.py \"part of name\" LAT LON")
        return

    if args.lat is None or args.lon is None:
        sys.exit("Give a latitude and longitude. See --list for what needs doing.")

    lat, lon = args.lat, args.lon
    w, s_, e, n = UK
    if not (s_ <= lat <= n and w <= lon <= e):
        # Almost always a swap - Google shows lat first, some tools lon first.
        if s_ <= lon <= n and w <= lat <= e:
            sys.exit(f"Those look swapped. Try: {lon} {lat}")
        sys.exit(f"{lat}, {lon} is outside the UK. Check the numbers.")

    hits = find(records, args.name)
    if not hits:
        sys.exit(f"Nothing matches {args.name!r}. Try --list.")
    if len(hits) > 1:
        print(f"{args.name!r} matches more than one record:")
        for _p, _d, s in hits:
            print(f"  {s['name']}")
        sys.exit("Be more specific.")

    path, doc, site = hits[0]
    before = (site.get("lat"), site.get("lon"))
    site["lat"] = round(lat, 6)
    site["lon"] = round(lon, 6)
    site["geocode_checked"] = True
    site["geocoded_by"] = "human"
    for k in ("geocode_band", "geocode_precision"):
        site.pop(k, None)

    json.dump(doc, open(path, "w", encoding="utf-8"), indent=2, ensure_ascii=False)

    print(f"\n{site['name']}")
    print(f"  {doc['authority']}")
    if before[0] is not None:
        moved = ((lat - before[0]) ** 2 + (lon - before[1]) ** 2) ** 0.5 * 111
        print(f"  was  {before[0]:.5f}, {before[1]:.5f}")
        print(f"  now  {lat:.5f}, {lon:.5f}   (moved about {moved:.1f} km)")
    else:
        print(f"  set  {lat:.5f}, {lon:.5f}")
    print("  marked as checked by a human")
    print(f"\n  https://www.google.com/maps/search/?api=1&query={lat},{lon}")
    print("\nRebuild with: python3 scripts/build_site.py")


if __name__ == "__main__":
    main()
