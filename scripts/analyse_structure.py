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
    args = ap.parse_args()

    con = sqlite3.connect(args.sqlite_path)

    total = con.execute(
        "SELECT COUNT(*) FROM measurement WHERE tech=?", (args.tech,)
    ).fetchone()[0]
    if not total:
        sys.exit(f"No rows for tech='{args.tech}'")

    print(f"\nrows                 {total:,}")

    print("counting distinct locations (a minute or two)…", file=sys.stderr)
    distinct = con.execute(
        "SELECT COUNT(*) FROM (SELECT 1 FROM measurement WHERE tech=? "
        "GROUP BY lat, lon)",
        (args.tech,),
    ).fetchone()[0]

    print(f"distinct locations   {distinct:,}")
    print(f"rows per location    {total/distinct:.2f} average")

    if total / distinct > 1.2:
        print("\n  -> Rows ARE duplicated per location. Any median computed")
        print("     across rows is weighted by measurement frequency, which")
        print("     favours busy roads. Aggregate per location first.")
    else:
        print("\n  -> Essentially one row per location.")

    # How many rows at the busiest single location?
    top = con.execute(
        "SELECT lat, lon, COUNT(*) c FROM measurement WHERE tech=? "
        "GROUP BY lat, lon ORDER BY c DESC LIMIT 5",
        (args.tech,),
    ).fetchall()
    print("\nbusiest locations:")
    for lat, lon, c in top:
        print(f"  {lat:.6f}, {lon:.6f}   {c:,} rows")

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
        "SELECT COUNT(*) FROM (SELECT lat, lon FROM measurement WHERE tech=? "
        "GROUP BY lat, lon HAVING MAX(n_ops)=0)",
        (args.tech,),
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
