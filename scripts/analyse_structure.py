#!/usr/bin/env python3
"""
How is this dataset actually structured?

Two questions the Bristol lookup raised:

  1. Are rows duplicated per location? The nearest-neighbour list showed
     identical readings at identical distances, which suggests one row
     per location per time bin rather than one row per location.
  2. Are coordinates snapped to a grid? Several readings sat at exactly
     the same distance, which raw GPS would not produce.

Both matter. Duplication biases any median toward frequently-driven
roads, and snapping sets the real resolution limit regardless of how
many decimal places the file carries.

    python3 scripts/analyse_structure.py data/out/signal.sqlite
"""
import argparse
import sqlite3
import sys
from collections import Counter


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("sqlite_path")
    ap.add_argument("--tech", default="4g")
    ap.add_argument(
        "--snap",
        type=int,
        default=4,
        help="decimal places to round coordinates to when counting "
        "distinct locations. 6dp is raw GPS and treats centimetre jitter "
        "from a parked vehicle as separate places; 4dp is ~11m and "
        "reflects physical locations (default 4).",
    )
    args = ap.parse_args()

    con = sqlite3.connect(args.sqlite_path)

    total = con.execute(
        "SELECT COUNT(*) FROM measurement WHERE tech=?", (args.tech,)
    ).fetchone()[0]
    if not total:
        sys.exit(f"No rows for tech='{args.tech}'")

    print(f"\nrows                 {total:,}")

    print("counting distinct locations (a minute or two)…", file=sys.stderr)
    raw = con.execute(
        "SELECT COUNT(*) FROM (SELECT 1 FROM measurement WHERE tech=? "
        "GROUP BY lat, lon)",
        (args.tech,),
    ).fetchone()[0]
    distinct = con.execute(
        "SELECT COUNT(*) FROM (SELECT 1 FROM measurement WHERE tech=? "
        "GROUP BY ROUND(lat,?), ROUND(lon,?))",
        (args.tech, args.snap, args.snap),
    ).fetchone()[0]

    step_m = 111000 * 10 ** -args.snap
    print(f"distinct at 6dp      {raw:,}   (raw GPS, ~0.1m)")
    print(f"distinct at {args.snap}dp      {distinct:,}   (~{step_m:.0f}m)")
    print(f"rows per location    {total/distinct:.2f} average at {args.snap}dp")
    if raw > distinct * 1.3:
        print(
            f"\n  -> {raw-distinct:,} of the 6dp 'locations' collapse at "
            f"{args.snap}dp.\n     That is GPS jitter from stationary "
            "vehicles, not distinct places."
        )

    if total / distinct > 1.2:
        print("\n  -> Rows ARE duplicated per location. Any median computed")
        print("     across rows is weighted by measurement frequency, which")
        print("     favours busy roads. Aggregate per location first.")
    else:
        print("\n  -> Essentially one row per location.")

    # How many rows at the busiest single location?
    top = con.execute(
        "SELECT ROUND(lat,?) la, ROUND(lon,?) lo, COUNT(*) c "
        "FROM measurement WHERE tech=? GROUP BY la, lo "
        "ORDER BY c DESC LIMIT 8",
        (args.snap, args.snap, args.tech),
    ).fetchall()
    print(f"\nbusiest locations (rounded to {args.snap}dp):")
    for lat, lon, c in top:
        print(f"  {lat:.4f}, {lon:.4f}   {c:,} rows   {100.0*c/total:.2f}% of file")
    hog = sum(c for _a, _b, c in top)
    print(f"  top 8 alone account for {100.0*hog/total:.2f}% of all rows")
    print("  -> almost certainly parked vehicles, not survey coverage")

    # ---- coordinate snapping ----
    print("\ncoordinate precision:")
    sample = con.execute(
        "SELECT lat, lon FROM measurement WHERE tech=? LIMIT 200000",
        (args.tech,),
    ).fetchall()

    for name, idx in (("lat", 0), ("lon", 1)):
        decimals = Counter()
        for row in sample:
            txt = f"{row[idx]:.10f}".rstrip("0")
            decimals[len(txt.split(".")[1]) if "." in txt else 0] += 1
        common = decimals.most_common(4)
        shown = ", ".join(f"{d}dp:{c:,}" for d, c in common)
        print(f"  {name}  {shown}")

    # Spacing between adjacent distinct values tells us the grid step.
    vals = sorted({round(r[0], 8) for r in sample})
    diffs = Counter()
    for a, b in zip(vals, vals[1:]):
        d = round(b - a, 8)
        if d > 0:
            diffs[d] += 1
    print("\nmost common gap between distinct latitudes:")
    for d, c in diffs.most_common(5):
        print(f"  {d:.8f} deg  (~{d*111000:.0f} m)   x{c:,}")

    # Is the notspot rate a function of duplication?
    print("\nnotspot rate by row vs by location:")
    ns_rows = con.execute(
        "SELECT COUNT(*) FROM measurement WHERE tech=? AND n_ops=0",
        (args.tech,),
    ).fetchone()[0]
    ns_locs = con.execute(
        "SELECT COUNT(*) FROM (SELECT 1 FROM measurement WHERE tech=? "
        "GROUP BY ROUND(lat,?), ROUND(lon,?) HAVING MAX(n_ops)=0)",
        (args.tech, args.snap, args.snap),
    ).fetchone()[0]
    print(f"  by row       {ns_rows:,} / {total:,}  ({100.0*ns_rows/total:.1f}%)")
    print(
        f"  by location  {ns_locs:,} / {distinct:,}  "
        f"({100.0*ns_locs/distinct:.1f}%)"
    )
    print("  (by location = no operator ever recorded there, in any time bin)")

    if ns_rows / total > 0.15 and ns_locs / distinct < ns_rows / total * 0.5:
        print("\n  -> Confirms the artefact. Most blank rows are time bins")
        print("     with no measurement at a location that WAS measured")
        print("     at other times. Blank rows are missing data, full stop.")

    con.close()
    print()


if __name__ == "__main__":
    main()
