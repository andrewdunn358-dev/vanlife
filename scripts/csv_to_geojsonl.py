#!/usr/bin/env python3
"""
Stream a huge CSV into line-delimited GeoJSON for Tippecanoe.

Never holds more than one row in memory, so a 14GB input runs fine on an
8GB box. Output is one GeoJSON Feature per line, which is exactly what
Tippecanoe wants.

    python3 scripts/csv_to_geojsonl.py \
        data/raw/ofcom_4g.csv \
        data/interim/ofcom_4g.geojsonl \
        --lat Latitude --lon Longitude \
        --keep RSRP,RSRQ,Operator

Omit --lat/--lon to auto-detect. Omit --keep to carry every column
through (bigger tiles; usually you want a short list).
"""
import argparse
import csv
import json
import sys

sys.path.insert(0, __import__("os").path.dirname(__file__))
from inspect_csv import guess_coord_columns  # noqa: E402


def parse_args():
    ap = argparse.ArgumentParser()
    ap.add_argument("csv_path")
    ap.add_argument("out_path")
    ap.add_argument("--lat", help="latitude column name")
    ap.add_argument("--lon", help="longitude column name")
    ap.add_argument("--keep", help="comma-separated columns to carry through")
    ap.add_argument(
        "--numeric",
        help="comma-separated columns to write as numbers rather than strings",
    )
    ap.add_argument(
        "--progress",
        type=int,
        default=1_000_000,
        help="log every N rows (0 to disable)",
    )
    return ap.parse_args()


def main():
    args = parse_args()
    keep = [c.strip() for c in args.keep.split(",")] if args.keep else None
    numeric = (
        {c.strip() for c in args.numeric.split(",")} if args.numeric else set()
    )

    written = skipped = 0

    with open(
        args.csv_path, newline="", encoding="utf-8-sig", errors="replace"
    ) as src, open(args.out_path, "w", encoding="utf-8") as dst:
        reader = csv.DictReader(src)
        if not reader.fieldnames:
            sys.exit("No header row found.")

        lat_col = args.lat or guess_coord_columns(reader.fieldnames)[0]
        lon_col = args.lon or guess_coord_columns(reader.fieldnames)[1]
        if not lat_col or not lon_col:
            sys.exit(
                "Could not identify coordinate columns. "
                "Run inspect_csv.py and pass --lat/--lon explicitly."
            )

        if keep:
            missing = [c for c in keep if c not in reader.fieldnames]
            if missing:
                sys.exit(f"--keep names columns not in file: {missing}")
        else:
            keep = [c for c in reader.fieldnames if c not in (lat_col, lon_col)]

        print(f"lat={lat_col}  lon={lon_col}", file=sys.stderr)
        print(f"carrying {len(keep)} attributes", file=sys.stderr)

        for row in reader:
            try:
                lat = float(row[lat_col])
                lon = float(row[lon_col])
            except (TypeError, ValueError):
                skipped += 1
                continue

            # Sanity-check against UK bounds. Catches OS grid values and
            # transposed lat/lon before they become 40GB of bad tiles.
            if not (-9.0 <= lon <= 2.5 and 49.0 <= lat <= 61.5):
                skipped += 1
                continue

            props = {}
            for col in keep:
                val = row.get(col)
                if val is None or val == "":
                    continue
                if col in numeric:
                    try:
                        val = float(val)
                    except ValueError:
                        pass
                props[col] = val

            dst.write(
                json.dumps(
                    {
                        "type": "Feature",
                        "geometry": {
                            "type": "Point",
                            "coordinates": [round(lon, 6), round(lat, 6)],
                        },
                        "properties": props,
                    },
                    separators=(",", ":"),
                )
            )
            dst.write("\n")
            written += 1

            if args.progress and written % args.progress == 0:
                print(f"  {written:,} features", file=sys.stderr)

    print(f"\nwrote {written:,} features", file=sys.stderr)
    print(f"skipped {skipped:,} rows (bad or out-of-bounds coords)", file=sys.stderr)
    if written and skipped / (written + skipped) > 0.1:
        print(
            "WARNING: over 10% skipped. Check your coordinate columns "
            "and whether the file is in OS grid rather than WGS84.",
            file=sys.stderr,
        )


if __name__ == "__main__":
    main()
