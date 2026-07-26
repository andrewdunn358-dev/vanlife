#!/usr/bin/env python3
"""
Build a spatially-indexed SQLite database from the measurement GeoJSONL.

Uses a plain integer grid index rather than SQLite's R*Tree. R*Tree is a
compile-time module and plenty of builds lack it - Synology DSM's Python
being one - so avoiding it means this works on any SQLite anywhere,
including whatever ships on a phone. For radius queries a grid is just
as fast.

Cells are 0.01 degrees, roughly 1.1km north-south and 0.65km east-west
at UK latitudes.

    python3 scripts/build_sqlite.py \
        data/interim/4g-2025.geojsonl \
        data/out/signal.sqlite --tech 4g

Run again with --tech 5g on the 5G file to add it to the same database.
"""
import argparse
import json
import math
import os
import sqlite3
import sys

BATCH = 50_000
OPERATORS = ("ee", "o2", "vodafone", "three")

CELL = 0.01  # degrees; keep in step with coverage_lookup.py

SCHEMA = """
PRAGMA journal_mode = OFF;
PRAGMA synchronous = OFF;
PRAGMA temp_store = MEMORY;

CREATE TABLE IF NOT EXISTS measurement (
    id       INTEGER PRIMARY KEY,
    tech     TEXT NOT NULL,
    lat      REAL NOT NULL,
    lon      REAL NOT NULL,
    cell_lat INTEGER NOT NULL,
    cell_lon INTEGER NOT NULL,
    ee       INTEGER,
    o2       INTEGER,
    vodafone INTEGER,
    three    INTEGER,
    n_ops    INTEGER NOT NULL,
    best     INTEGER,
    best_op  TEXT
);
"""


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("geojsonl")
    ap.add_argument("sqlite_path")
    ap.add_argument("--tech", default="4g", help="label for this dataset")
    ap.add_argument("--progress", type=int, default=1_000_000)
    args = ap.parse_args()

    fresh = not os.path.exists(args.sqlite_path)
    con = sqlite3.connect(args.sqlite_path)
    con.executescript(SCHEMA)

    if not fresh:
        existing = con.execute(
            "SELECT COUNT(*) FROM measurement WHERE tech = ?", (args.tech,)
        ).fetchone()[0]
        if existing:
            print(
                f"{existing:,} rows already present for tech='{args.tech}'. "
                "Delete the file or pick another --tech label.",
                file=sys.stderr,
            )
            sys.exit(1)

    start_id = con.execute(
        "SELECT COALESCE(MAX(id), 0) FROM measurement"
    ).fetchone()[0]

    rows = []
    n = 0
    next_id = start_id + 1

    def flush():
        con.executemany(
            "INSERT INTO measurement "
            "(id, tech, lat, lon, cell_lat, cell_lon, "
            " ee, o2, vodafone, three, n_ops, best, best_op) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
            rows,
        )
        con.commit()
        rows.clear()

    with open(args.geojsonl, encoding="utf-8") as fh:
        for line in fh:
            try:
                feat = json.loads(line)
            except json.JSONDecodeError:
                continue
            lon, lat = feat["geometry"]["coordinates"]
            p = feat["properties"]
            rows.append(
                (
                    next_id,
                    args.tech,
                    lat,
                    lon,
                    int(math.floor(lat / CELL)),
                    int(math.floor(lon / CELL)),
                    p.get("ee"),
                    p.get("o2"),
                    p.get("vodafone"),
                    p.get("three"),
                    p.get("n_ops", 0),
                    p.get("best"),
                    p.get("best_op"),
                )
            )
            next_id += 1
            n += 1

            if len(rows) >= BATCH:
                flush()
            if args.progress and n % args.progress == 0:
                print(f"  {n:,}", file=sys.stderr)

    if rows:
        flush()

    print("\nindexing…", file=sys.stderr)
    con.execute(
        "CREATE INDEX IF NOT EXISTS ix_cell "
        "ON measurement(tech, cell_lat, cell_lon)"
    )
    con.execute("PRAGMA optimize")
    con.commit()

    total = con.execute("SELECT COUNT(*) FROM measurement").fetchone()[0]
    size = os.path.getsize(args.sqlite_path) / 1e9
    print(f"\nadded    {n:,} rows as tech='{args.tech}'", file=sys.stderr)
    print(f"total    {total:,} rows", file=sys.stderr)
    print(f"file     {size:.2f} GB", file=sys.stderr)
    con.close()


if __name__ == "__main__":
    main()
