#!/usr/bin/env python3
"""
Take the repo's research records, keep your locally verified coordinates.

update.sh never overwrites data/sites/*.json, which is what protects
coordinates you have checked by hand. The cost is that records added or
corrected in the repo cannot reach an install that already has the file.

This resolves that: repo content wins for the research, local wins for
geometry. Sites are matched on name.

    python3 scripts/merge_records.py
    python3 scripts/merge_records.py --write

Nothing is written without --write, and it reports every record it would
add, every coordinate it would carry over, and anything it cannot match.
"""
import argparse
import glob
import json
import os
import shutil
import subprocess
import sys
import tempfile

REPO = "https://github.com/andrewdunn358-dev/vanlife/archive/refs/heads/main.tar.gz"

# Fields that belong to this install, not to the repo.
LOCAL_FIELDS = ("lat", "lon", "geocoded_by", "geocode_precision", "geocode_band",
                "geocode_checked", "osm_id", "match_score", "postcode")


def fetch(dest):
    tar = os.path.join(dest, "repo.tar.gz")
    subprocess.run(["curl", "-sSL", "-o", tar, REPO], check=True)
    subprocess.run(["tar", "xzf", tar, "-C", dest, "--strip-components=1"], check=True)
    d = os.path.join(dest, "data", "sites")
    if not os.path.isdir(d):
        sys.exit("No data/sites in the repo archive")
    return d


def merge_file(local_path, repo_path):
    """Repo record content, local geometry. Returns (doc, notes)."""
    repo = json.load(open(repo_path, encoding="utf-8"))
    notes = []

    if not os.path.exists(local_path):
        notes.append(f"new file, {len(repo['sites'])} records")
        return repo, notes

    local = json.load(open(local_path, encoding="utf-8"))
    have = {s.get("name"): s for s in local.get("sites", [])}

    kept = added = 0
    for s in repo["sites"]:
        mine = have.get(s.get("name"))
        if mine is None:
            added += 1
            continue
        for f in LOCAL_FIELDS:
            if f in mine and mine[f] is not None:
                s[f] = mine[f]
        if mine.get("lat") is not None:
            kept += 1

    orphans = [n for n in have if n not in {s.get("name") for s in repo["sites"]}]
    for n in orphans:
        o = have[n]
        if o.get("lat") is not None or o.get("geocode_checked"):
            # local-only record with real work in it - do not discard
            repo["sites"].append(o)
            notes.append(f"kept local-only record with geometry: {n}")
        else:
            notes.append(f"dropped local-only record: {n}")

    if added:
        notes.append(f"{added} record(s) new from repo")
    if kept:
        notes.append(f"{kept} coordinate(s) carried over")
    return repo, notes


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", default="data/sites")
    ap.add_argument("--write", action="store_true")
    args = ap.parse_args()

    tmp = tempfile.mkdtemp()
    try:
        print("fetching repo records...", file=sys.stderr)
        repo_dir = fetch(tmp)

        before = sum(len(json.load(open(f, encoding="utf-8"))["sites"])
                     for f in glob.glob(os.path.join(args.dir, "*.json")))
        after = 0

        for rp in sorted(glob.glob(os.path.join(repo_dir, "*.json"))):
            name = os.path.basename(rp)
            lp = os.path.join(args.dir, name)
            doc, notes = merge_file(lp, rp)
            after += len(doc["sites"])
            if notes:
                print(f"\n{name}")
                for n in notes:
                    print(f"  {n}")
            if args.write:
                os.makedirs(args.dir, exist_ok=True)
                json.dump(doc, open(lp, "w", encoding="utf-8"),
                          indent=2, ensure_ascii=False)

        print(f"\nrecords: {before} local -> {after} merged")
        if not args.write:
            print("\nNothing written. Re-run with --write to apply.")
        else:
            print("\nWritten. Rebuild with: python3 scripts/build_site.py")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    main()
