#!/usr/bin/env python3
"""
Check that every located record sits in the county the site puts it in.

Cornwall showed two pins in Northumberland and neither the validator nor
the build noticed. Coordinates and county assignment were being checked
separately, so a record could be internally consistent and still 600km
from where the page said it was.

This asks postcodes.io what county each coordinate is actually in and
compares that with the county the site files it under. No API key, no
limit, ONS-derived.

    python3 scripts/check_geography.py

Reports records whose coordinates fall outside their assigned county,
records outside the UK entirely, and duplicate coordinates - repeated
identical positions usually mean test values that leaked in.
"""
import argparse
import glob
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from collections import Counter

UA = "vanlife-dev/0.1 (github.com/andrewdunn358-dev/vanlife)"

# postcodes.io names do not always match the county names used here.
ALIASES = {
    "Northumberland": {"Northumberland"},
    "County Durham": {"County Durham", "Durham", "Darlington", "Hartlepool",
                      "Stockton-on-Tees"},
    "North Yorkshire": {"North Yorkshire", "Redcar and Cleveland", "Middlesbrough",
                        "Scarborough", "Ryedale"},
    "Tees Valley": {"Darlington", "Hartlepool", "Middlesbrough",
                    "Redcar and Cleveland", "Stockton-on-Tees"},
    "Tyne and Wear": {"Newcastle upon Tyne", "Gateshead", "North Tyneside",
                      "South Tyneside", "Sunderland"},
    "Gwynedd": {"Gwynedd"},
    "Conwy": {"Conwy"},
    "Denbighshire": {"Denbighshire"},
    "Pembrokeshire": {"Pembrokeshire"},
    "Highland": {"Highland"},
    "South Ayrshire": {"South Ayrshire"},
    "Cornwall": {"Cornwall", "Isles of Scilly"},
    "Lincolnshire": {"Lincolnshire", "North East Lincolnshire",
                     "North Lincolnshire", "East Lindsey"},
    "Lancashire": {"Lancashire", "Blackpool", "Blackburn with Darwen"},
    "Kent": {"Kent", "Medway"},
    "Suffolk": {"Suffolk", "East Suffolk", "West Suffolk"},
    "Buckinghamshire": {"Buckinghamshire", "Milton Keynes"},
}


def lookup(lat, lon):
    """Which admin district is this point in? None if postcodes.io has no idea."""
    url = f"https://api.postcodes.io/postcodes?lon={lon}&lat={lat}&limit=1&radius=20000"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": UA})
        with urllib.request.urlopen(req, timeout=20) as r:
            d = json.loads(r.read().decode())
    except Exception:
        return None
    res = d.get("result")
    if not res:
        return None
    p = res[0]
    return {
        "district": p.get("admin_district"),
        "county": p.get("admin_county"),
        "country": p.get("country"),
        "postcode": p.get("postcode"),
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", default="data/sites")
    ap.add_argument("--assets", default="scripts/assets")
    args = ap.parse_args()

    cfg = json.load(open(os.path.join(args.assets, "areas.json"), encoding="utf-8"))
    auth_areas = cfg.get("authorities", {})
    site_areas = cfg.get("site_areas", {})

    located = []
    for f in sorted(glob.glob(os.path.join(args.dir, "*.json"))):
        d = json.load(open(f, encoding="utf-8"))
        covers = auth_areas.get(d["authority"]) or d.get("areas") or []
        for s in d["sites"]:
            if s.get("lat") is None:
                continue
            placed = site_areas.get(d["authority"], {}).get(s.get("name"))
            expected = [placed] if placed else covers
            located.append((d["authority"], s, expected))

    if not located:
        sys.exit("No located records to check.")
    print(f"checking {len(located)} located record(s)\n")

    # duplicates first - no network needed, and they are usually leaked test values
    coords = Counter((round(s["lat"], 6), round(s["lon"], 6)) for _a, s, _e in located)
    dupes = {c: n for c, n in coords.items() if n > 1}
    if dupes:
        print("REPEATED COORDINATES - usually test values that leaked in:")
        for c, n in dupes.items():
            print(f"  {c[0]:.5f}, {c[1]:.5f}  used by {n} records:")
            for a, s, _e in located:
                if (round(s["lat"], 6), round(s["lon"], 6)) == c:
                    print(f"      {a} / {s['name']}")
        print()

    problems = 0
    for authority, s, expected in located:
        got = lookup(s["lat"], s["lon"])
        time.sleep(0.15)
        name = s["name"][:42]
        if got is None:
            print(f"  ??  {name:<44} {s['lat']:.4f},{s['lon']:.4f}  "
                  "nothing within 20km - is this in the UK?")
            problems += 1
            continue

        actual = {got["district"], got["county"]} - {None}
        ok = any(actual & ALIASES.get(e, {e}) for e in expected)
        if ok:
            print(f"  OK  {name:<44} {got['district']}")
        else:
            print(f"  NO  {name:<44} filed under {'/'.join(expected)}, "
                  f"actually in {got['district']}")
            print(f"      {authority} - nearest postcode {got['postcode']}")
            problems += 1

    print(f"\n{problems} problem(s) of {len(located)} checked")
    if problems:
        print("\nA record in the wrong county is worse than one with no location:")
        print("it looks authoritative and points somewhere else entirely.")
    sys.exit(1 if problems else 0)


if __name__ == "__main__":
    main()
