#!/usr/bin/env python3
"""
Convert Ofcom's wide-format drive-test CSV to line-delimited GeoJSON.

Ofcom publishes one row per location with columns shaped
{parameter}_top{1..4}_{operator} - roughly 160 of them, mostly empty.
Only top1 matters here: it is the strongest cell each operator had at
that spot, which is what "will I have signal" actually means.

Output is one Point per location carrying one RSRP value per operator,
so the map can switch operator without rebuilding tiles.

    python3 scripts/ofcom_to_geojsonl.py \
        data/raw/4g-lte-2025-mobile-signal-measurement-data.csv \
        data/interim/4g-2025.geojsonl

Add --sinr to carry signal-to-noise as well (larger tiles, but RSRP
alone overstates usable speed where there is interference).
"""
import argparse
import csv
import json
import re
import sys

# Ofcom's operator suffixes, mapped to something displayable.
OPERATORS = {
    "ee": "ee",
    "o2": "o2",
    "vf": "vodafone",
    "3uk": "three",
}

LAT_HINTS = ("lat", "latitude", "y", "northing")
LON_HINTS = ("lon", "long", "lng", "longitude", "x", "easting")

UK_BOUNDS = (-9.0, 49.0, 2.5, 61.5)  # west, south, east, north


def find_coords(fieldnames):
    lat = lon = None
    for name in fieldnames:
        low = name.strip().lower()
        if lat is None and low in LAT_HINTS:
            lat = name
        if lon is None and low in LON_HINTS:
            lon = name
    if lat and lon:
        return lat, lon
    for name in fieldnames:
        low = name.strip().lower()
        if lat is None and ("lat" in low or "northing" in low):
            lat = name
        if lon is None and ("lon" in low or "lng" in low or "easting" in low):
            lon = name
    return lat, lon


def find_operators(fieldnames):
    """Detect which operators are present from the rsrp_top1_* columns."""
    found = {}
    pattern = re.compile(r"^rsrp_top1_(.+)$", re.IGNORECASE)
    for name in fieldnames:
        m = pattern.match(name.strip())
        if m:
            suffix = m.group(1).lower()
            found[suffix] = name
    return found


def to_int(val):
    if val is None or val == "":
        return None
    try:
        return int(round(float(val)))
    except (TypeError, ValueError):
        return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("csv_path")
    ap.add_argument("out_path")
    ap.add_argument("--sinr", action="store_true", help="carry SINR too")
    ap.add_argument("--progress", type=int, default=500_000)
    ap.add_argument(
        "--drop-notspots",
        action="store_true",
        help="skip locations where no operator had a reading. Off by "
        "default: a total notspot is the most useful fact a van app can "
        "tell you. Note the ambiguity though - an absent reading may mean "
        "genuine no-service or simply that Ofcom did not upload it, since "
        "they publish a targeted subset rather than everything captured.",
    )
    args = ap.parse_args()

    written = no_coords = no_signal = out_of_bounds = 0
    west, south, east, north = UK_BOUNDS

    with open(
        args.csv_path, newline="", encoding="utf-8-sig", errors="replace"
    ) as src, open(args.out_path, "w", encoding="utf-8") as dst:
        reader = csv.DictReader(src)
        if not reader.fieldnames:
            sys.exit("No header row found.")

        lat_col, lon_col = find_coords(reader.fieldnames)
        if not lat_col or not lon_col:
            sys.exit(
                "Could not find coordinate columns.\n"
                f"Available: {reader.fieldnames[:20]}"
            )

        ops = find_operators(reader.fieldnames)
        if not ops:
            sys.exit("No rsrp_top1_* columns found - is this the right file?")

        sinr_cols = {}
        if args.sinr:
            for suffix in ops:
                for name in reader.fieldnames:
                    if name.strip().lower() == f"sinr_top1_{suffix}":
                        sinr_cols[suffix] = name

        print(f"coords:    {lat_col} / {lon_col}", file=sys.stderr)
        print(
            "operators: "
            + ", ".join(f"{OPERATORS.get(s, s)}" for s in sorted(ops)),
            file=sys.stderr,
        )
        if args.sinr:
            print(f"sinr:      {len(sinr_cols)} columns", file=sys.stderr)
        print(file=sys.stderr)

        for row in reader:
            try:
                lat = float(row[lat_col])
                lon = float(row[lon_col])
            except (TypeError, ValueError):
                no_coords += 1
                continue

            if not (west <= lon <= east and south <= lat <= north):
                out_of_bounds += 1
                continue

            props = {}
            best_val = None
            best_op = None

            for suffix, col in ops.items():
                label = OPERATORS.get(suffix, suffix)
                val = to_int(row.get(col))
                if val is None:
                    continue
                props[label] = val
                if best_val is None or val > best_val:
                    best_val = val
                    best_op = label
                if suffix in sinr_cols:
                    s = to_int(row.get(sinr_cols[suffix]))
                    if s is not None:
                        props[f"{label}_sinr"] = s

            if not props:
                no_signal += 1
                if args.drop_notspots:
                    continue

            props["n_ops"] = len(
                [1 for s in ops.values() if to_int(row.get(s)) is not None]
            )
            if best_val is not None:
                props["best"] = best_val
                props["best_op"] = best_op

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
                print(f"  {written:,}", file=sys.stderr)

    print(f"\nwrote            {written:,} locations", file=sys.stderr)
    print(f"no coordinates   {no_coords:,}", file=sys.stderr)
    print(f"outside UK       {out_of_bounds:,}", file=sys.stderr)
    print(f"total notspots   {no_signal:,}  (kept, n_ops=0)", file=sys.stderr)

    total = written + no_coords + out_of_bounds + no_signal
    if total and out_of_bounds / total > 0.1:
        print(
            "\nWARNING: over 10% outside UK bounds. Check whether the "
            "coordinates are OS grid (EPSG:27700) rather than WGS84.",
            file=sys.stderr,
        )


if __name__ == "__main__":
    main()
