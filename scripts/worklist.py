#!/usr/bin/env python3
"""
Turn the register into a worklist.

Researching 428 bodies is not one sitting. This produces, for each one, the
search queries that have actually worked and the URL patterns worth trying,
so a session is spent reading rather than working out what to look for.

    python3 scripts/worklist.py --tier 1
    python3 scripts/worklist.py --region "North East" --out worklist.md
    python3 scripts/worklist.py --done          # what is already recorded

Ordered by tier, and skips anything already in data/sites.
"""
import argparse
import csv
import glob
import json
import os
import sys

# Query shapes that produced usable results during the July 2026 research.
# The thematic ones were far more efficient - one search on north Wales
# returned Conwy, Denbighshire, Gwynedd, Pembrokeshire and Highland.
QUERIES = [
    '{name} motorhome overnight parking car parks',
    '{name} campervan overnight sleeping policy',
    '"{short}" motorhome parking order overnight',
]
LANDOWNER_QUERIES = [
    '{name} overnight parking campervan motorhome car parks',
    '{name} overnight stays policy visitors',
]

# Council sites cluster around a handful of paths.
URL_HINTS = [
    "/parking/motorhome-parking",
    "/parking/council-car-parks/motorhome-parking",
    "/parking-roads-and-travel/parking-and-permits",
    "/parking/parking-locations",
    "/transport-and-streets/parking",
]

FIELDS = ["source_format", "provision_url", "restriction_url",
          "has_provision", "instrument_seen"]


def already_done(sites_dir):
    done = set()
    for f in glob.glob(os.path.join(sites_dir, "*.json")):
        try:
            done.add(json.load(open(f, encoding="utf-8"))["authority"])
        except Exception:
            pass
    return done


def short_name(row):
    return row.get("short_name") or row["authority"]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--register", default="data/research-register.csv")
    ap.add_argument("--sites", default="data/sites")
    ap.add_argument("--tier", default="1,2", help="comma-separated, e.g. 1 or 1,2")
    ap.add_argument("--region", help="filter to one region")
    ap.add_argument("--nation", help="filter to one nation")
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--out", help="write markdown here instead of stdout")
    ap.add_argument("--done", action="store_true", help="list what is recorded already")
    args = ap.parse_args()

    if not os.path.exists(args.register):
        sys.exit(f"No register at {args.register}. Run build_register.py first.")

    rows = list(csv.DictReader(open(args.register, encoding="utf-8-sig")))
    done = already_done(args.sites)

    if args.done:
        print(f"{len(done)} bodies recorded:\n")
        for a in sorted(done):
            print(f"  {a}")
        print(f"\n{len(rows) - len(done)} of {len(rows)} still to do")
        return

    tiers = {t.strip() for t in args.tier.split(",")}
    todo = [r for r in rows
            if r["priority"] in tiers
            and r["authority"] not in done
            and (not args.region or r["region"] == args.region)
            and (not args.nation or r["nation"] == args.nation)]
    todo.sort(key=lambda r: (r["priority"], r["nation"], r["authority"]))
    if args.limit:
        todo = todo[: args.limit]

    out = []
    out.append(f"# Research worklist\n")
    out.append(f"{len(todo)} bodies, tier {args.tier}"
               + (f", {args.region}" if args.region else "")
               + f". {len(done)} already recorded.\n")
    out.append("Thematic searches are far more efficient than one body at a time - "
               "a single search on north Wales returned five authorities. Group by "
               "region or by type before searching.\n")

    for r in todo:
        is_land = r["powers"] in ("landowner", "permission", "national park")
        qs = LANDOWNER_QUERIES if is_land else QUERIES
        out.append(f"\n## {r['authority']}")
        bits = [r["type"], r["nation"]]
        if r.get("region"):
            bits.append(r["region"])
        if r.get("parent_county"):
            bits.append(f"districts: {r['parent_county'][:60]}")
        out.append("`" + " · ".join(b for b in bits if b) + "`\n")
        if r.get("pressure_reason"):
            out.append(f"{r['pressure_reason']}\n")

        out.append("**Search**")
        for q in qs:
            out.append(f"- `{q.format(name=r['authority'], short=short_name(r))}`")

        if r.get("gov_uk_slug") and not is_land:
            out.append("\n**Likely pages** (find the domain first, these are the paths)")
            for h in URL_HINTS[:3]:
                out.append(f"- `{h}`")

        if r.get("wdtk_id"):
            out.append(f"\n**FOI** if nothing is published: "
                       f"whatdotheyknow.com/body/" + str(r["wdtk_id"]).replace(".0","") + "")

        out.append("\n**Record**")
        for f in FIELDS:
            out.append(f"- [ ] {f}")
        out.append("- [ ] provision: designated sites, price, hours, self-containment")
        out.append("- [ ] restriction: which instrument, what hours, what penalty")
        out.append("- [ ] does it restrict *parking* or *sleeping*? They differ.")

    text = "\n".join(out)
    if args.out:
        open(args.out, "w", encoding="utf-8").write(text)
        print(f"wrote {args.out} - {len(todo)} bodies")
    else:
        print(text)


if __name__ == "__main__":
    main()
