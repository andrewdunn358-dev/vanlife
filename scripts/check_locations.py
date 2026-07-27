#!/usr/bin/env python3
"""
Find pins that are probably in the wrong place.

Every coordinate in this dataset was researched by hand or by a geocoder,
and both go wrong quietly. A pin 40km from where it should be looks
exactly like a pin in the right place until someone opens the map and
recognises the area - which does not scale past the counties you happen
to know.

The checks are ordered by how much they mean. Nothing here proves a pin
is right; it flags the ones worth looking at, loudest first.

    python3 scripts/check_locations.py              # everything
    python3 scripts/check_locations.py --offline    # skip the network checks
    python3 scripts/check_locations.py --authority "Forestry England"
    python3 scripts/check_locations.py --fail-on high   # non-zero exit for CI

Network checks use postcodes.io - free, no key, generous limits - and
cache to data/reference/geocache.json, so a second run is instant and
works offline. Delete the cache to re-check from scratch.
"""
import argparse
import csv
import glob
import json
import math
import os
import sys
import time
import urllib.error
import urllib.request

SITES = "data/sites"
REGISTER = "data/research-register.csv"
AREAS = "scripts/assets/areas.json"
CACHE = "data/reference/geocache.json"

# Great Britain and Northern Ireland, generously. Anything outside is not
# a judgement call, it is a typo - a swapped sign or transposed pair.
UK = {"lat": (49.8, 60.9), "lon": (-8.7, 1.9)}

# How far a pin may sit from the body's centre before it is worth a look.
# Derived from the body's own area where the reference table has it - one
# fixed number cannot serve both Torbay and Highland, which are three
# orders of magnitude apart. Falls back to type when area is unknown.
CENTROID_KM = {
    "district": 40, "lower tier": 40, "unitary": 70, "upper tier": 90,
    "county": 90, "national park": 70, "landowner": 400, "permission": 400,
}
DEFAULT_CENTROID_KM = 120

SEVERITY = ["high", "medium", "low"]


def haversine(a_lat, a_lon, b_lat, b_lon):
    """Kilometres between two points."""
    r = 6371.0
    p1, p2 = math.radians(a_lat), math.radians(b_lat)
    dp = math.radians(b_lat - a_lat)
    dl = math.radians(b_lon - a_lon)
    h = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(h))


def load_cache():
    if os.path.exists(CACHE):
        try:
            return json.load(open(CACHE, encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            pass
    return {"reverse": {}, "postcode": {}}


def save_cache(cache):
    os.makedirs(os.path.dirname(CACHE), exist_ok=True)
    json.dump(cache, open(CACHE, "w", encoding="utf-8"), indent=1, sort_keys=True)


def get_json(url, timeout=12):
    req = urllib.request.Request(url, headers={"User-Agent": "vanlife-check"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.load(r)


def reverse(lat, lon, cache, online):
    """Nearest postcode to a point, and the district it sits in.

    2km radius: below that, every remote moorland car park in the dataset
    comes back empty and the check is useless where it matters most.
    """
    key = f"{lat:.5f},{lon:.5f}"
    if key in cache["reverse"]:
        return cache["reverse"][key]
    if not online:
        return None
    url = (f"https://api.postcodes.io/postcodes?lat={lat}&lon={lon}"
           f"&limit=1&radius=2000&wideSearch=false")
    try:
        res = (get_json(url) or {}).get("result")
    except (urllib.error.URLError, OSError, json.JSONDecodeError, TimeoutError):
        return None
    hit = None
    if res:
        r = res[0]
        hit = {"postcode": r.get("postcode"),
               "district": r.get("admin_district"),
               "county": r.get("admin_county"),
               "country": r.get("country"),
               "lat": r.get("latitude"), "lon": r.get("longitude")}
    cache["reverse"][key] = hit
    time.sleep(0.12)
    return hit


def lookup_postcode(pc, cache, online):
    key = pc.upper().replace(" ", "")
    if key in cache["postcode"]:
        return cache["postcode"][key]
    if not online:
        return None
    hit = None
    for path in ("postcodes", "terminated_postcodes"):
        try:
            r = (get_json(f"https://api.postcodes.io/{path}/"
                          f"{urllib.parse.quote(pc)}") or {}).get("result")
        except (urllib.error.URLError, OSError, json.JSONDecodeError, TimeoutError):
            return None
        if r:
            hit = {"lat": r.get("latitude"), "lon": r.get("longitude"),
                   "district": r.get("admin_district"),
                   "terminated": path != "postcodes"}
            break
    cache["postcode"][key] = hit
    time.sleep(0.12)
    return hit


def areas_by_gss():
    """Square kilometres per authority, from the reference table."""
    out = {}
    path = "data/reference/uk_la_current.csv"
    if not os.path.exists(path):
        return out
    for r in csv.DictReader(open(path, encoding="utf-8")):
        try:
            out[r["gss-code"]] = float(r["area"])
        except (TypeError, ValueError, KeyError):
            continue
    return out


def register_centroids():
    """Authority name -> (lat, lon, type, limit_km).

    The register's lat/long are not reliable centroids - several sit
    offshore, Devon's is in the Bristol Channel and Norfolk's is in the
    Wash - so this is a coarse filter only, and the caller treats a body
    whose pins are ALL far from it as a bad centroid rather than a
    hundred bad pins.
    """
    out = {}
    if not os.path.exists(REGISTER):
        return out
    sqkm = areas_by_gss()
    for r in csv.DictReader(open(REGISTER, encoding="utf-8")):
        try:
            lat, lon = float(r["lat"]), float(r["long"])
        except (TypeError, ValueError):
            continue
        kind = (r.get("powers") or r.get("type") or "").lower()
        area = sqkm.get((r.get("gss_code") or "").strip())
        if area:
            # Radius of a circle of the same area, times a slack factor for
            # long thin counties and for a centroid that may be off.
            limit = max(35.0, 2.5 * math.sqrt(area / math.pi))
        else:
            limit = next((km for word, km in CENTROID_KM.items() if word in kind),
                         DEFAULT_CENTROID_KM)
        out[r["authority"]] = (lat, lon, kind, limit)
    return out


def median(values):
    v = sorted(values)
    n = len(v)
    return v[n // 2] if n % 2 else (v[n // 2 - 1] + v[n // 2]) / 2


def check(records, online=True, only=None):
    cache = load_cache()
    cents = register_centroids()
    findings = []

    def flag(sev, doc, site, what, detail):
        findings.append({"severity": sev, "authority": doc["authority"],
                         "site": site.get("name", "?"), "check": what,
                         "detail": detail,
                         "lat": site.get("lat"), "lon": site.get("lon")})

    seen = {}
    for doc in records:
        if only and doc["authority"] != only:
            continue
        located = [s for s in doc["sites"] if s.get("lat") is not None]
        lats = [s["lat"] for s in located]
        lons = [s["lon"] for s in located]
        mid = (median(lats), median(lons)) if len(located) >= 3 else None

        # Decide up front whether to trust this body's centroid at all. If
        # every pin is beyond the limit, the odd one out is the centroid,
        # and flagging each pin would bury the real finding under noise.
        cent = cents.get(doc["authority"])
        trust_centroid = False
        if cent and located:
            far = [s for s in located
                   if haversine(s["lat"], s["lon"], cent[0], cent[1]) > cent[3]]
            if len(located) >= 2 and len(far) == len(located):
                flag("medium", doc, {"name": "(all pins)", "lat": cent[0],
                                     "lon": cent[1]},
                     "the register's centroid looks wrong",
                     f"all {len(located)} pins are more than {cent[3]:.0f}km "
                     f"from the centroid the register gives for this body, so "
                     "the centroid is the likelier error - the pins were not "
                     "flagged individually")
            else:
                trust_centroid = True

        for s in located:
            lat, lon = s["lat"], s["lon"]

            # 1. Outside the UK is never a judgement call.
            if not (UK["lat"][0] <= lat <= UK["lat"][1]
                    and UK["lon"][0] <= lon <= UK["lon"][1]):
                flag("high", doc, s, "outside UK",
                     f"{lat}, {lon} is not in the UK - check for a swapped "
                     "sign or a transposed pair")
                continue

            # 2. A geocoder that admitted it failed. legality-research.md
            #    section 6c is about exactly this: Nominatim returning the
            #    middle of a reservoir for a car park beside it.
            if s.get("geocoded_by") == "nominatim":
                flag("high", doc, s, "geocoder pin",
                     "placed by Nominatim"
                     + (f", precision recorded as {s['geocode_precision']!r}"
                        if s.get("geocode_precision") else "")
                     + " - re-place from OSM or a source that names the car park")
            elif s.get("geocode_band") == "area":
                flag("medium", doc, s, "area-level pin",
                     "band is 'area', so this is a neighbourhood not a car park")

            # 3. Two records on one point. Either a duplicate record or a
            #    shared postcode centroid standing in for two car parks.
            key = (round(lat, 5), round(lon, 5))
            if key in seen:
                other = seen[key]
                flag("medium", doc, s, "same point as another record",
                     f"identical to {other[0]} - {other[1]}")
            else:
                seen[key] = (doc["authority"], s.get("name", "?"))

            # 4. Miles from the body it belongs to - only where the
            #    centroid earned trust above.
            if trust_centroid:
                km = haversine(lat, lon, cent[0], cent[1])
                if km > cent[3]:
                    flag("high" if km > cent[3] * 2 else "medium", doc, s,
                         "far from the authority",
                         f"{km:.0f}km from the centre of {doc['authority']}, "
                         f"which is a {cent[3]:.0f}km body - and its other "
                         "pins are not out here")

            # 5. Miles from its own siblings. Catches the case where the
            #    centroid is missing or itself unhelpful. Scaled by the
            #    body's size, or Highland's Inverness car park reads as an
            #    outlier from its own Caithness ones.
            if mid and len(located) >= 3:
                km = haversine(lat, lon, mid[0], mid[1])
                others = [haversine(o["lat"], o["lon"], mid[0], mid[1])
                          for o in located if o is not s]
                typical = median(others) if others else 0
                spread = cent[3] * 1.2 if cent else 60.0
                if km > max(spread, typical * 6) and km > 25:
                    flag("medium", doc, s, "outlier among its siblings",
                         f"{km:.0f}km from the middle of this body's other "
                         f"pins, which sit within about {typical:.0f}km")

            # 6. Does the pin agree with the postcode the record states?
            if s.get("postcode"):
                pc = lookup_postcode(s["postcode"], cache, online)
                if pc and pc.get("lat") is not None:
                    km = haversine(lat, lon, pc["lat"], pc["lon"])
                    if km > 5:
                        flag("high", doc, s, "pin disagrees with its postcode",
                             f"{km:.1f}km from {s['postcode']} - one of the two "
                             "is wrong")
                    elif km > 1.5:
                        flag("low", doc, s, "pin drifts from its postcode",
                             f"{km:.1f}km from {s['postcode']}")

            # 7. What is actually there, according to the postcode map.
            rev = reverse(lat, lon, cache, online)
            if rev is None and online:
                flag("low", doc, s, "nothing within 2km",
                     "no postcode within 2km - plausible on open moor, "
                     "suspicious anywhere else")
            elif rev and s.get("postcode"):
                want = s["postcode"].upper().replace(" ", "")[:3]
                got = (rev.get("postcode") or "").upper().replace(" ", "")[:3]
                if want and got and want[:2] != got[:2]:
                    flag("medium", doc, s, "wrong postcode area",
                         f"record says {s['postcode']}, the nearest postcode "
                         f"to the pin is {rev['postcode']}")

    save_cache(cache)
    return findings


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", default=SITES)
    ap.add_argument("--offline", action="store_true",
                    help="skip postcodes.io; use only what is cached")
    ap.add_argument("--authority", help="check one body")
    ap.add_argument("--fail-on", choices=SEVERITY,
                    help="exit non-zero if anything at this level or worse")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    files = sorted(glob.glob(os.path.join(args.dir, "*.json")))
    records = [json.load(open(f, encoding="utf-8")) for f in files]
    total = sum(1 for d in records for s in d["sites"] if s.get("lat") is not None)

    findings = check(records, online=not args.offline, only=args.authority)

    if args.json:
        print(json.dumps(findings, indent=1))
    else:
        order = {s: i for i, s in enumerate(SEVERITY)}
        findings.sort(key=lambda f: (order[f["severity"]], f["authority"]))
        last = None
        for f in findings:
            if f["severity"] != last:
                last = f["severity"]
                print(f"\n{last.upper()}")
            print(f"  {f['authority']} - {f['site']}")
            print(f"      {f['check']}: {f['detail']}")
            if f["lat"] is not None:
                print(f"      https://www.openstreetmap.org/"
                      f"?mlat={f['lat']}&mlon={f['lon']}#map=17/"
                      f"{f['lat']}/{f['lon']}")
        counts = {s: sum(1 for f in findings if f["severity"] == s)
                  for s in SEVERITY}
        print(f"\n{'='*62}")
        print(f"{total} located records checked - "
              + ", ".join(f"{counts[s]} {s}" for s in SEVERITY))
        if args.offline:
            print("offline: postcode and reverse-lookup checks used cache only")

    if args.fail_on:
        cut = SEVERITY.index(args.fail_on)
        if any(SEVERITY.index(f["severity"]) <= cut for f in findings):
            sys.exit(1)


if __name__ == "__main__":
    import urllib.parse  # noqa: E402  (only needed by lookup_postcode)
    main()
