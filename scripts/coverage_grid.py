#!/usr/bin/env python3
"""
Where does this dataset actually have measurements?

Checking named boxes tells you about the boxes you thought to check.
This bins everything onto a grid and reports what fraction of the UK has
any data at all, which is the question that decides whether a measured
signal layer is viable.

    python3 scripts/coverage_grid.py data/interim/4g-2025.geojsonl
    python3 scripts/coverage_grid.py data/interim/4g-2025.geojsonl \
        --cell 0.05 --geojson data/out/coverage.geojson

The optional GeoJSON output is small enough to drop straight into the
viewer, and shows the shape of the dataset far better than 12 million
individual points.
"""
import argparse
import json
import math
import sys
from collections import defaultdict

# Rough UK land area, km^2, for a coverage denominator.
UK_LAND_KM2 = 242_500


def cell_area_km2(lat, cell):
    """Approximate area of a lat/lon cell at this latitude."""
    lat_km = cell * 110.574
    lon_km = cell * 111.320 * math.cos(math.radians(lat))
    return lat_km * lon_km


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("geojsonl")
    ap.add_argument("--cell", type=float, default=0.1,
                    help="grid cell size in degrees (default 0.1, ~11x7km)")
    ap.add_argument("--sample", type=int, default=1)
    ap.add_argument("--geojson", help="write grid cells here for mapping")
    ap.add_argument("--top", type=int, default=15)
    args = ap.parse_args()

    cells = defaultdict(lambda: [0, 0])  # (ix,iy) -> [points, notspots]
    total = 0

    with open(args.geojsonl, encoding="utf-8") as fh:
        for i, line in enumerate(fh):
            if args.sample > 1 and i % args.sample:
                continue
            try:
                feat = json.loads(line)
            except json.JSONDecodeError:
                continue
            lon, lat = feat["geometry"]["coordinates"]
            key = (int(math.floor(lon / args.cell)),
                   int(math.floor(lat / args.cell)))
            c = cells[key]
            c[0] += 1
            if feat["properties"].get("n_ops", 0) == 0:
                c[1] += 1
            total += 1

    if not total:
        sys.exit("No features read.")

    covered_km2 = 0.0
    for (ix, iy) in cells:
        lat = (iy + 0.5) * args.cell
        covered_km2 += cell_area_km2(lat, args.cell)

    counts = sorted((c[0] for c in cells.values()))
    median = counts[len(counts) // 2]

    print(f"\npoints read        {total:,}")
    if args.sample > 1:
        print(f"                   (every {args.sample}th line)")
    print(f"cell size          {args.cell}deg  (~{args.cell*111:.0f}km N-S)")
    print(f"cells with data    {len(cells):,}")
    print(f"approx area        {covered_km2:,.0f} km2")
    print(f"of UK land         {100.0*covered_km2/UK_LAND_KM2:.1f}%")
    print(f"\npoints per cell    median {median:,}   max {counts[-1]:,}")

    thin = sum(1 for c in counts if c < 10)
    print(f"cells with <10 pts {thin:,}  ({100.0*thin/len(cells):.1f}%)")

    print(f"\ndensest {args.top} cells:")
    print(f"{'lat':>8}{'lon':>9}{'points':>10}{'notspot%':>10}")
    print("-" * 37)
    ranked = sorted(cells.items(), key=lambda kv: -kv[1][0])[: args.top]
    for (ix, iy), (n, ns) in ranked:
        lat = (iy + 0.5) * args.cell
        lon = (ix + 0.5) * args.cell
        print(f"{lat:>8.2f}{lon:>9.2f}{n:>10,}{100.0*ns/n:>9.1f}%")

    if args.geojson:
        feats = []
        for (ix, iy), (n, ns) in cells.items():
            w, s = ix * args.cell, iy * args.cell
            e, nn = w + args.cell, s + args.cell
            feats.append({
                "type": "Feature",
                "geometry": {
                    "type": "Polygon",
                    "coordinates": [[[w, s], [e, s], [e, nn], [w, nn], [w, s]]],
                },
                "properties": {
                    "points": n,
                    "notspot_pct": round(100.0 * ns / n, 1),
                },
            })
        with open(args.geojson, "w", encoding="utf-8") as out:
            json.dump({"type": "FeatureCollection", "features": feats}, out)
        print(f"\nwrote {len(feats):,} cells to {args.geojson}")

    print()
    pct = 100.0 * covered_km2 / UK_LAND_KM2
    if pct < 25:
        print("READ: this is not a national dataset. It covers wherever the")
        print("survey vehicles happened to drive. Usable for validating")
        print("coverage on specific roads; not usable as a map layer that")
        print("answers 'will I have signal here' anywhere a van might park.")
    elif pct < 60:
        print("READ: partial national coverage. Viable as a layer only with")
        print("explicit 'no data here' rendering, so absence never reads as")
        print("a measurement.")
    else:
        print("READ: broad national coverage. Viable as a primary layer.")


if __name__ == "__main__":
    main()
