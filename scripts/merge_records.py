#!/usr/bin/env python3
"""
Take the repo's research records, keep the better coordinates.

update.sh never overwrites data/sites/*.json, which is what protects
coordinates you have checked by hand. The cost is that records added or
corrected in the repo cannot reach an install that already has the file.

This resolves that: repo content wins for the research, and geometry is
decided per record by which pin is better evidenced. Sites are matched on
name.

    python3 scripts/merge_records.py
    python3 scripts/merge_records.py --write

Nothing is written without --write, and it reports every record it would
add, every coordinate it would take from either side, and anything it
cannot match.

Note on the rule change: this used to keep the local pin unconditionally,
which was right when local coordinates were hand-checked and the repo had
none. Once the repo carried 200-odd researched pins that rule started
overwriting good coordinates with the geocoder guesses it had replaced -
an install could sit on a pin in the middle of a reservoir forever, and
running this again would reapply it. A pin you have checked yourself
still always wins.
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

# The geometry block. These move together or not at all - carrying a lat
# from one side and the provenance from the other would make the record
# lie about where its pin came from.
GEOMETRY = ("lat", "lon", "geocoded_by", "geocode_precision", "geocode_band",
            "geocode_checked", "geocode_source", "osm_id", "match_score",
            "postcode")

BAND_RANK = {"precise": 3, "nearby": 2, "approximate": 2, "area": 1}


def coord_rank(site):
    """How much a pin is worth believing.

    Checked by a human beats everything. After that it is who placed it:
    a car park found by name in a source beats a geocoder that was handed
    a place name and returned whatever it matched - a reservoir, a
    village centre, an administrative boundary.
    """
    if site is None or site.get("lat") is None:
        return (0, 0, 0)
    checked = 2 if site.get("geocode_checked") else 0
    by = (site.get("geocoded_by") or "").lower()
    source = 2 if by and by != "nominatim" else 1 if by else 0
    band = BAND_RANK.get(site.get("geocode_band"), 0)
    return (checked, source, band)


def placeholder_pin(site):
    """A whole number in both axes is a stand-in somebody meant to revisit.

    Same test as check_locations.py. Worth repeating here because this is
    where a stale local record gets carried forward for another year.
    """
    lat, lon = site.get("lat"), site.get("lon")
    if lat is None or lon is None:
        return False
    return round(lat, 3) == round(lat) and round(lon, 3) == round(lon)


def describe(site):
    if site is None or site.get("lat") is None:
        return "no pin"
    bits = [f"{site['lat']:.5f},{site['lon']:.5f}"]
    if site.get("geocode_checked"):
        bits.append("checked")
    if site.get("geocoded_by"):
        bits.append(str(site["geocoded_by"]))
    if site.get("geocode_band"):
        bits.append(str(site["geocode_band"]))
    return " ".join(bits)


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

    kept = added = upgraded = 0
    for s in repo["sites"]:
        mine = have.get(s.get("name"))
        if mine is None:
            added += 1
            continue
        if coord_rank(mine) >= coord_rank(s):
            # Local pin is as good or better - take the whole block.
            for f in GEOMETRY:
                if f in mine and mine[f] is not None:
                    s[f] = mine[f]
                elif f in s and f not in mine:
                    s.pop(f, None)
            if mine.get("lat") is not None:
                kept += 1
        else:
            upgraded += 1
            notes.append(f"better pin from repo: {s.get('name')}"
                         f"\n      yours: {describe(mine)}"
                         f"\n       repo: {describe(s)}")

    orphans = [n for n in have if n not in {s.get("name") for s in repo["sites"]}]
    for n in orphans:
        o = have[n]
        if o.get("lat") is not None or o.get("geocode_checked"):
            # local-only record with real work in it - do not discard
            repo["sites"].append(o)
            if placeholder_pin(o):
                notes.append(
                    f"STALE? local-only record on a placeholder pin: {n}"
                    f"\n      {describe(o)} - whole numbers are a stand-in, "
                    "not a location."
                    "\n      Kept, because this tool never deletes your data. "
                    "If the repo has since"
                    "\n      split this into properly located records, delete "
                    "it from the local file.")
            else:
                notes.append(f"kept local-only record with geometry: {n}")
        else:
            notes.append(f"dropped local-only record: {n}")

    if added:
        notes.append(f"{added} record(s) new from repo")
    if kept:
        notes.append(f"{kept} coordinate(s) kept from this install")
    if upgraded:
        notes.append(f"{upgraded} coordinate(s) taken from the repo")
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
