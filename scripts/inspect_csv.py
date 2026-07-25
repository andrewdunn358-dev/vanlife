#!/usr/bin/env python3
"""
Look at an Ofcom drive-test CSV without opening 14GB in a text editor.

Prints the columns, a few sample rows, and guesses which columns hold
coordinates. Reads only the first N rows, so it returns instantly
regardless of file size.

    python3 scripts/inspect_csv.py data/raw/ofcom_4g.csv
"""
import argparse
import csv
import sys

LAT_HINTS = ("lat", "latitude", "y", "northing")
LON_HINTS = ("lon", "long", "lng", "longitude", "x", "easting")


def guess_coord_columns(fieldnames):
    lat = lon = None
    for name in fieldnames:
        low = name.strip().lower()
        if lat is None and low in LAT_HINTS:
            lat = name
        if lon is None and low in LON_HINTS:
            lon = name
    if lat is None or lon is None:
        for name in fieldnames:
            low = name.strip().lower()
            if lat is None and any(h in low for h in ("lat", "northing")):
                lat = name
            if lon is None and any(h in low for h in ("lon", "lng", "easting")):
                lon = name
    return lat, lon


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("csv_path")
    ap.add_argument("--rows", type=int, default=5, help="sample rows to print")
    args = ap.parse_args()

    with open(args.csv_path, newline="", encoding="utf-8-sig", errors="replace") as fh:
        reader = csv.DictReader(fh)
        if not reader.fieldnames:
            sys.exit("No header row found.")

        print(f"{len(reader.fieldnames)} columns:\n")
        for i, name in enumerate(reader.fieldnames):
            print(f"  [{i:>2}] {name}")

        lat, lon = guess_coord_columns(reader.fieldnames)
        print("\nCoordinate guess:")
        print(f"  lat -> {lat or 'NOT FOUND'}")
        print(f"  lon -> {lon or 'NOT FOUND'}")
        if lat and lon and any(
            h in (lat + lon).lower() for h in ("easting", "northing")
        ):
            print("  NOTE: looks like OS grid (EPSG:27700), not WGS84.")
            print("        Reproject before tiling.")

        print(f"\nFirst {args.rows} rows:\n")
        for n, row in enumerate(reader):
            if n >= args.rows:
                break
            for k, v in row.items():
                print(f"  {k}: {v}")
            print("  ---")


if __name__ == "__main__":
    main()
