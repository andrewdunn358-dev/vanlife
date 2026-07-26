#!/usr/bin/env python3
"""
Look up 4G/5G coverage for a postcode, address or coordinate.

Two sources, deliberately kept separate because they mean different
things:

  MEASURED   - your Ofcom drive-test points, from the local SQLite.
               Real readings, but only ~13% of UK land area has any.
  PREDICTED  - Ofcom's Mobile Coverage API. Modelled on a 50m grid over
               the whole UK, so it always answers, but it is a model.

Never merge them into one number. Show both, say which is which, and let
the absence of measured data read as "not measured" rather than "no
signal".

    python3 scripts/coverage_lookup.py "SW1A 1AA"
    python3 scripts/coverage_lookup.py "Applecross"
    python3 scripts/coverage_lookup.py 57.4321 -5.8012 --radius 5

Set OFCOM_MOBILE_KEY in the environment to include predicted coverage.
Register free at api.ofcom.org.uk (Mobile product, 50k calls/month).
"""
import argparse
import json
import math
import os
import re
import sqlite3
import sys
import urllib.error
import urllib.parse
import urllib.request

CELL = 0.01  # must match build_sqlite.py

POSTCODE_RE = re.compile(r"^[A-Z]{1,2}\d[A-Z\d]?\s*\d[A-Z]{2}$", re.I)
UA = "vanlife-dev/0.1 (github.com/andrewdunn358-dev/vanlife)"

# Ofcom's numeric coverage scale. 1 and 2 are retired per the API spec.
OFCOM_SCALE = {4: "likely", 3: "limited", 0: "none"}

# Ofcom uses carrier codes, not brand names.
OFCOM_OPS = {"EE": "ee", "TF": "o2", "VO": "vodafone", "H3": "three"}

# RSRP bands, dBm. Rough but defensible for 4G.
def band(rsrp):
    if rsrp is None:
        return "no reading"
    if rsrp >= -80:
        return "strong"
    if rsrp >= -90:
        return "good"
    if rsrp >= -100:
        return "usable"
    if rsrp >= -110:
        return "weak"
    return "very weak"


def get_json(url, headers=None):
    req = urllib.request.Request(url, headers={"User-Agent": UA, **(headers or {})})
    with urllib.request.urlopen(req, timeout=20) as r:
        return json.loads(r.read().decode())


def geocode(term):
    """Return (lat, lon, label). Postcodes via postcodes.io, else Nominatim."""
    if POSTCODE_RE.match(term.strip()):
        d = get_json(
            "https://api.postcodes.io/postcodes/"
            + urllib.parse.quote(term.strip())
        )
        r = d["result"]
        return r["latitude"], r["longitude"], f"{r['postcode']} ({r['admin_district']})"

    arr = get_json(
        "https://nominatim.openstreetmap.org/search?format=json&limit=1"
        "&countrycodes=gb&q=" + urllib.parse.quote(term)
    )
    if not arr:
        raise SystemExit(f"Could not geocode: {term}")
    a = arr[0]
    return (
        float(a["lat"]),
        float(a["lon"]),
        ",".join(a["display_name"].split(",")[:3]),
    )


def haversine_km(lat1, lon1, lat2, lon2):
    r = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = p2 - p1
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def measured(db_path, lat, lon, radius_km, tech):
    if not os.path.exists(db_path):
        return None
    con = sqlite3.connect(db_path)
    con.row_factory = sqlite3.Row

    # Grid-cell prefilter, then exact haversine. Cell size must match
    # build_sqlite.py.
    dlat = radius_km / 110.574
    dlon = radius_km / (111.320 * max(math.cos(math.radians(lat)), 0.01))

    rows = con.execute(
        """
        SELECT * FROM measurement
        WHERE tech = ?
          AND cell_lat BETWEEN ? AND ?
          AND cell_lon BETWEEN ? AND ?
        """,
        (
            tech,
            int(math.floor((lat - dlat) / CELL)),
            int(math.floor((lat + dlat) / CELL)),
            int(math.floor((lon - dlon) / CELL)),
            int(math.floor((lon + dlon) / CELL)),
        ),
    ).fetchall()
    con.close()

    hits = []
    for r in rows:
        d = haversine_km(lat, lon, r["lat"], r["lon"])
        if d <= radius_km:
            hits.append((d, r))
    hits.sort(key=lambda x: x[0])
    return hits


DEDUP_DP = 4  # ~11m; collapses GPS jitter from stationary vehicles


def dedupe(hits):
    """One reading per ~11m cell, nearest kept.

    The raw data logs at 6dp (~0.1m), so a van parked beside a mast for an
    afternoon contributes hundreds of rows from one spot. Left in, those
    drag any median toward wherever the survey vehicles happened to sit
    still. The top 8 such spots account for a measurable share of the
    whole file.
    """
    seen = {}
    for d, r in hits:  # already sorted nearest-first
        key = (round(r["lat"], DEDUP_DP), round(r["lon"], DEDUP_DP))
        if key not in seen:
            seen[key] = (d, r)
    return sorted(seen.values(), key=lambda x: x[0])


def median(vals):
    vals = sorted(v for v in vals if v is not None)
    if not vals:
        return None
    n = len(vals)
    return vals[n // 2] if n % 2 else (vals[n // 2 - 1] + vals[n // 2]) // 2


def nearest_postcode(lat, lon):
    """Reverse-geocode. Returns (postcode, distance_km) or (None, None).

    Needed because the Ofcom API is keyed on postcodes and UPRNs, and the
    places this app cares about - lay-bys, forest tracks, passes - have
    neither. The distance matters: a postcode 3km away in Snowdonia says
    little about where you are parked, so it gets reported, not hidden.
    """
    try:
        d = get_json(
            f"https://api.postcodes.io/postcodes?lon={lon}&lat={lat}&limit=1"
        )
        res = d.get("result")
        if not res:
            return None, None
        pc = res[0]
        return pc["postcode"], haversine_km(
            lat, lon, pc["latitude"], pc["longitude"]
        )
    except Exception:  # noqa: BLE001
        return None, None


def predicted(postcode, key):
    url = (
        "https://api-proxy.ofcom.org.uk/mobile/coverage/"
        + urllib.parse.quote(postcode.replace(" ", ""))
    )
    return get_json(url, {"Ocp-Apim-Subscription-Key": key})


def summarise_prediction(payload):
    """Collapse per-address results into one worst/best view per operator.

    The API returns a MobileProvision per UPRN in the postcode. Addresses
    within one postcode can differ, so report the range rather than
    picking one arbitrarily.
    """
    if isinstance(payload, dict):
        payload = [payload]
    addresses = []
    for entry in payload or []:
        addresses.extend(entry.get("Availability") or [])
    if not addresses:
        return None, 0

    out = {}
    for code, name in OFCOM_OPS.items():
        for service in ("Data", "Voice"):
            for place in ("Outdoor", "Indoor"):
                field = f"{code}{service}{place}"
                vals = [
                    a[field] for a in addresses
                    if isinstance(a.get(field), int)
                ]
                if vals:
                    out.setdefault(name, {})[(service, place)] = (
                        min(vals), max(vals)
                    )
    return out, len(addresses)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("query", nargs="+", help="postcode, place name, or lat lon")
    ap.add_argument("--db", default="data/out/signal.sqlite")
    ap.add_argument("--radius", type=float, default=2.0, help="km")
    ap.add_argument("--tech", default="4g")
    ap.add_argument("--show", type=int, default=5, help="nearest points to list")
    args = ap.parse_args()

    # Coordinates given directly?
    if len(args.query) == 2:
        try:
            lat, lon = float(args.query[0]), float(args.query[1])
            label = f"{lat:.5f}, {lon:.5f}"
            postcode = None
        except ValueError:
            lat = lon = None
    else:
        lat = None

    if lat is None:
        term = " ".join(args.query)
        lat, lon, label = geocode(term)
        postcode = term if POSTCODE_RE.match(term.strip()) else None

    print(f"\n{label}")
    if label != f"{lat:.5f}, {lon:.5f}":
        print(f"{lat:.5f}, {lon:.5f}")
    print("=" * 58)

    # ---- measured ----
    print(f"\nMEASURED  (Ofcom drive-test, within {args.radius:g} km)")
    raw_hits = measured(args.db, lat, lon, args.radius, args.tech)
    hits = dedupe(raw_hits) if raw_hits else raw_hits
    if hits is None:
        print(f"  no database at {args.db} - run build_sqlite.py first")
    elif not hits:
        print("  NO MEASUREMENTS within radius.")
        print("  This means nobody drove here, NOT that there is no signal.")
    else:
        n_notspot = sum(1 for _d, r in hits if r["n_ops"] == 0)
        print(
            f"  {len(hits):,} distinct spots (~{111000*10**-DEDUP_DP:.0f}m "
            f"apart), nearest {hits[0][0]*1000:.0f} m away"
        )
        if len(raw_hits) > len(hits):
            print(
                f"  from {len(raw_hits):,} raw rows - "
                f"{len(raw_hits)-len(hits):,} were repeat logs at the same "
                "spot (parked vehicles) and are excluded from the medians"
            )
        if n_notspot:
            print(
                f"  {n_notspot:,} ({100.0*n_notspot/len(hits):.0f}%) recorded "
                "no operator - treat as unrecorded, not zero signal"
            )
        print()
        for op in ("ee", "o2", "vodafone", "three"):
            vals = [r[op] for _d, r in hits if r[op] is not None]
            if not vals:
                print(f"    {op:<10} no readings")
                continue
            med = median(vals)
            print(
                f"    {op:<10} median {med:>5} dBm  ({band(med)})"
                f"   best {max(vals):>5}   n={len(vals):,}"
            )
        print(f"\n  nearest {min(args.show, len(hits))} readings:")
        for d, r in hits[: args.show]:
            ops = " ".join(
                f"{o}={r[o]}" for o in ("ee", "o2", "vodafone", "three") if r[o]
            )
            print(f"    {d*1000:>6.0f} m  {ops or '(nothing recorded)'}")

    # ---- predicted ----
    key = os.environ.get("OFCOM_MOBILE_KEY")
    print("\nPREDICTED  (Ofcom model, per address)")
    if not key:
        print("  OFCOM_MOBILE_KEY not set - skipping.")
        print("  Register free at api.ofcom.org.uk, request the Mobile product.")
        print()
        return

    if not postcode:
        postcode, pc_dist = nearest_postcode(lat, lon)
        if not postcode:
            print("  No postcode found nearby - cannot query.")
            print()
            return
        print(f"  nearest postcode {postcode}, {pc_dist*1000:.0f} m away")
        if pc_dist > 0.5:
            print("  CAUTION: that is far enough away to mean little here.")

    try:
        data = predicted(postcode, key)
    except urllib.error.HTTPError as exc:
        if exc.code == 404:
            print(f"  {postcode}: not found in Ofcom's data.")
        elif exc.code in (401, 403):
            print("  Auth failed. Check the key and that Mobile is enabled.")
        else:
            print(f"  HTTP {exc.code}: {exc.reason}")
        print()
        return
    except Exception as exc:  # noqa: BLE001
        print(f"  request failed: {exc}")
        print()
        return

    summary, n_addr = summarise_prediction(data)
    if not summary:
        print("  no availability data returned")
        print()
        return

    print(f"  {n_addr} address(es) in {postcode}")
    print()
    W = 17
    print(f"    {'operator':<10}{'data out':<{W}}{'data in':<{W}}"
          f"{'voice out':<{W}}{'voice in':<{W}}")
    print("    " + "-" * (10 + W * 4))
    for name in ("ee", "o2", "vodafone", "three"):
        cells = summary.get(name)
        if not cells:
            continue
        parts = []
        for service, place in (
            ("Data", "Outdoor"), ("Data", "Indoor"),
            ("Voice", "Outdoor"), ("Voice", "Indoor"),
        ):
            rng = cells.get((service, place))
            if rng is None:
                parts.append("-")
            elif rng[0] == rng[1]:
                parts.append(OFCOM_SCALE.get(rng[0], str(rng[0])))
            else:
                parts.append(
                    f"{OFCOM_SCALE.get(rng[0], rng[0])}/"
                    f"{OFCOM_SCALE.get(rng[1], rng[1])}"
                )
        print(f"    {name:<10}" + "".join(f"{p:<{W}}" for p in parts))

    print()
    print("    A van is a metal box, so 'indoor' is the better guide to what")
    print("    you will get sitting inside it. 'Outdoor' is standing beside it.")

    # ---- do the two sources agree? ----
    if hits:
        print("\nAGREEMENT")
        for name in ("ee", "o2", "vodafone", "three"):
            vals = [r[name] for _d, r in hits if r[name] is not None]
            cells = summary.get(name) or {}
            pred = cells.get(("Data", "Outdoor"))
            if not vals or pred is None:
                continue
            med = median(vals)
            pred_txt = OFCOM_SCALE.get(pred[1], str(pred[1]))
            # Rough correspondence: 'likely' should mean better than -100.
            if pred[1] == 4 and med < -105:
                verdict = "MODEL OPTIMISTIC"
            elif pred[1] == 0 and med > -100:
                verdict = "MODEL PESSIMISTIC"
            else:
                verdict = "consistent"
            print(
                f"    {name:<10} model says {pred_txt:<9} "
                f"measured median {med:>5} dBm   -> {verdict}"
            )
        print()
        print("    Disagreement is the interesting case, and the thing no")
        print("    other coverage checker can show you.")

    print()


if __name__ == "__main__":
    main()
