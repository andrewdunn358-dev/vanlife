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
import urllib.parse
import urllib.request

POSTCODE_RE = re.compile(r"^[A-Z]{1,2}\d[A-Z\d]?\s*\d[A-Z]{2}$", re.I)
UA = "vanlife-dev/0.1 (github.com/andrewdunn358-dev/vanlife)"

# Ofcom's numeric coverage scale.
OFCOM_SCALE = {4: "likely", 3: "limited", 0: "none"}

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

    # Degrees of padding for the R*Tree box, then filter precisely.
    dlat = radius_km / 110.574
    dlon = radius_km / (111.320 * max(math.cos(math.radians(lat)), 0.01))

    rows = con.execute(
        """
        SELECT m.* FROM measurement m
        JOIN measurement_idx i ON i.id = m.id
        WHERE i.min_lat >= ? AND i.max_lat <= ?
          AND i.min_lon >= ? AND i.max_lon <= ?
          AND m.tech = ?
        """,
        (lat - dlat, lat + dlat, lon - dlon, lon + dlon, tech),
    ).fetchall()
    con.close()

    hits = []
    for r in rows:
        d = haversine_km(lat, lon, r["lat"], r["lon"])
        if d <= radius_km:
            hits.append((d, r))
    hits.sort(key=lambda x: x[0])
    return hits


def median(vals):
    vals = sorted(v for v in vals if v is not None)
    if not vals:
        return None
    n = len(vals)
    return vals[n // 2] if n % 2 else (vals[n // 2 - 1] + vals[n // 2]) // 2


def predicted(postcode, key):
    url = (
        "https://api-proxy.ofcom.org.uk/mobile/coverage/"
        + urllib.parse.quote(postcode.replace(" ", ""))
    )
    return get_json(url, {"Ocp-Apim-Subscription-Key": key})


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
    hits = measured(args.db, lat, lon, args.radius, args.tech)
    if hits is None:
        print(f"  no database at {args.db} - run build_sqlite.py first")
    elif not hits:
        print("  NO MEASUREMENTS within radius.")
        print("  This means nobody drove here, NOT that there is no signal.")
    else:
        n_notspot = sum(1 for _d, r in hits if r["n_ops"] == 0)
        print(f"  {len(hits):,} readings, nearest {hits[0][0]*1000:.0f} m away")
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
    print("\nPREDICTED  (Ofcom model, 50m grid, whole UK)")
    if not key:
        print("  OFCOM_MOBILE_KEY not set - skipping.")
        print("  Register free at api.ofcom.org.uk for the Mobile product.")
    elif not postcode:
        print("  Needs a postcode. Re-run with one for predicted coverage.")
    else:
        try:
            data = predicted(postcode, key)
            entries = data if isinstance(data, list) else data.get("Availability", [])
            if not entries:
                print("  no data returned")
            else:
                e = entries[0]
                print(f"  {len(entries)} address(es) in postcode; showing first")
                for k, v in sorted(e.items()):
                    if not isinstance(v, (int, str)):
                        continue
                    if isinstance(v, int) and v in OFCOM_SCALE:
                        print(f"    {k:<34} {OFCOM_SCALE[v]}")
                    elif "Address" in k or "Post" in k:
                        print(f"    {k:<34} {v}")
        except Exception as exc:  # noqa: BLE001
            print(f"  API call failed: {exc}")
            print("  Check the key, and that the Mobile product is enabled.")

    print()


if __name__ == "__main__":
    main()
