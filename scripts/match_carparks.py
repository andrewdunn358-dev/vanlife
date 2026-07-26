#!/usr/bin/env python3
"""
Match site records against real car park features from OpenStreetMap.

The point of this project is that the app finds these places, not that
someone types coordinates in by hand. A geocoder cannot do it - it
guesses from a name and returns village centres. Matching a name against
a list of actual car parks can.

    python3 scripts/match_carparks.py
    python3 scripts/match_carparks.py --write --min-score 0.55

Scoring combines how well the names agree with how close the candidate
is to any location already on the record. Anything below the threshold is
reported, never written, because a confident wrong pin is worse than no
pin.
"""
import argparse
import glob
import json
import math
import os
import re
import sys
from difflib import SequenceMatcher

# Words that appear in almost every car park name and so carry no signal.
NOISE = {
    "car", "park", "carpark", "parking", "the", "overflow", "long", "short",
    "stay", "north", "south", "east", "west", "upper", "lower", "main",
    "public", "council", "beach", "road", "street", "lane", "centre", "center",
}


def norm(s):
    s = (s or "").lower()
    s = re.sub(r"[^a-z0-9\s]", " ", s)
    return [w for w in s.split() if w and w not in NOISE]


def name_score(a, b):
    """Agreement between two names, ignoring the boilerplate words."""
    ta, tb = set(norm(a)), set(norm(b))
    if not ta or not tb:
        return 0.0
    overlap = len(ta & tb) / len(ta | tb)
    seq = SequenceMatcher(None, " ".join(sorted(ta)), " ".join(sorted(tb))).ratio()
    return 0.65 * overlap + 0.35 * seq


def km(lat1, lon1, lat2, lon2):
    r = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = p2 - p1, math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def load_carparks(ref_dir):
    parks = []
    for p in sorted(glob.glob(os.path.join(ref_dir, "carparks-*.json"))):
        d = json.load(open(p, encoding="utf-8"))
        for c in d["carparks"]:
            c["_area"] = d["area"]
            parks.append(c)
    return parks


def best_match(site, parks, radius_km):
    """Highest-scoring car park, given the name and any rough location."""
    have = site.get("lat") is not None
    ranked = []
    for c in parks:
        if not c.get("name"):
            continue
        ns = name_score(site.get("name"), c["name"])
        if ns < 0.2:
            continue
        d = km(site["lat"], site["lon"], c["lat"], c["lon"]) if have else None
        if d is not None and d > radius_km:
            continue
        # A rough pin from geocoding is weak evidence, but real evidence.
        prox = 0.0 if d is None else max(0.0, 1.0 - d / radius_km)
        score = ns if d is None else 0.72 * ns + 0.28 * prox
        ranked.append((score, ns, d, c))
    ranked.sort(key=lambda x: -x[0])
    return ranked


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", default="data/sites")
    ap.add_argument("--ref", default="data/reference")
    ap.add_argument("--radius", type=float, default=6.0,
                    help="km around an existing rough pin to search")
    ap.add_argument("--min-score", type=float, default=0.55)
    ap.add_argument("--write", action="store_true")
    args = ap.parse_args()

    parks = load_carparks(args.ref)
    if not parks:
        sys.exit("No car park data. Run fetch_carparks.py --area <name> first.")
    named = [p for p in parks if p.get("name")]
    print(f"{len(parks):,} car parks loaded, {len(named):,} named\n")

    files = sorted(glob.glob(os.path.join(args.dir, "*.json")))
    matched = weak = none = 0

    for path in files:
        d = json.load(open(path, encoding="utf-8"))
        changed = False
        for s in d["sites"]:
            nm = (s.get("name") or "").lower()
            if any(p in nm for p in ("all other", "various", "county-wide")):
                continue
            if s.get("geocode_checked") is True:
                continue

            ranked = best_match(s, parks, args.radius)
            if not ranked:
                print(f"  --   {s['name'][:46]:<48} no candidate")
                none += 1
                continue

            score, ns, dist, c = ranked[0]
            dtxt = f"{dist*1000:.0f}m away" if dist is not None else "no prior pin"
            tag = "OK  " if score >= args.min_score else "weak"
            print(f"  {tag} {s['name'][:46]:<48} {score:.2f}  {c['name'][:34]:<36} {dtxt}")

            if len(ranked) > 1 and ranked[1][0] > score - 0.08:
                print(f"       {'':<48} close second: {ranked[1][3]['name'][:40]}")

            if score >= args.min_score:
                matched += 1
                if args.write:
                    s["lat"], s["lon"] = c["lat"], c["lon"]
                    s["osm_id"] = c["osm_id"]
                    s["geocoded_by"] = "osm_carpark_match"
                    s["geocode_precision"] = "carpark"
                    s["geocode_band"] = "precise"
                    s["geocode_checked"] = False
                    s["match_score"] = round(score, 2)
                    for t in ("maxheight", "capacity", "fee", "access", "operator"):
                        if c.get(t):
                            s.setdefault("osm_" + t, c[t])
                    changed = True
            else:
                weak += 1

        if changed:
            json.dump(d, open(path, "w", encoding="utf-8"), indent=2, ensure_ascii=False)

    print(f"\n{matched} matched at or above {args.min_score}, "
          f"{weak} too weak, {none} with no candidate")
    if matched and not args.write:
        print("\nNothing written. Re-run with --write to accept the matches.")
    elif matched:
        print("\nWritten. These are real car park geometries, not name guesses,")
        print("but still worth a glance on satellite view before trusting them.")
        print("Any maxheight tags from OSM came across too - useful for the")
        print("vehicle matcher.")


if __name__ == "__main__":
    main()
