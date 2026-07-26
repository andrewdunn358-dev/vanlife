#!/usr/bin/env python3
"""
Is a high notspot rate a real finding or a data artefact?

A notspot is a location where no operator had a reading. That is either
genuine no-service, or Ofcom simply did not upload a measurement for
that row - they publish a targeted subset, not everything captured.

The two look identical in the data and mean opposite things. This tells
them apart by geography: genuine notspots concentrate in remote areas,
artefacts are spread uniformly. If dense city centres show a notspot
rate anywhere near the national average, do not trust the field.

    python3 scripts/sanity_check.py data/interim/4g-2025.geojsonl
    python3 scripts/sanity_check.py data/interim/4g-2025.geojsonl --sample 20
"""
import argparse
import json
import sys

# west, south, east, north
REGIONS = [
    ("Central London",    -0.16, 51.48, -0.05, 51.54, "urban"),
    ("Birmingham",        -1.95, 52.44, -1.85, 52.50, "urban"),
    ("Manchester",        -2.29, 53.44, -2.19, 53.50, "urban"),
    ("Glasgow",           -4.30, 55.83, -4.20, 55.89, "urban"),
    ("Bristol",           -2.63, 51.43, -2.53, 51.49, "urban"),
    ("NW Highlands",      -5.60, 57.00, -4.60, 58.00, "remote"),
    ("Cambrian Mtns",     -3.90, 52.20, -3.40, 52.60, "remote"),
    ("Rannoch Moor",      -4.90, 56.50, -4.40, 56.80, "remote"),
    ("Upper Teesdale",    -2.40, 54.55, -1.95, 54.75, "remote"),
    ("Kielder",           -2.70, 55.10, -2.30, 55.30, "remote"),
]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("geojsonl")
    ap.add_argument(
        "--sample",
        type=int,
        default=1,
        help="read every Nth line (default 1 = all). Use 20 for a fast pass.",
    )
    args = ap.parse_args()

    total = notspots = 0
    stats = {r[0]: [0, 0] for r in REGIONS}  # name -> [seen, notspots]
    ops_seen = {}

    with open(args.geojsonl, encoding="utf-8") as fh:
        for i, line in enumerate(fh):
            if args.sample > 1 and i % args.sample:
                continue
            try:
                feat = json.loads(line)
            except json.JSONDecodeError:
                continue

            lon, lat = feat["geometry"]["coordinates"]
            props = feat["properties"]
            is_notspot = props.get("n_ops", 0) == 0

            total += 1
            if is_notspot:
                notspots += 1
            else:
                for k in props:
                    if k in ("n_ops", "best", "best_op") or k.endswith("_sinr"):
                        continue
                    ops_seen[k] = ops_seen.get(k, 0) + 1

            for name, w, s, e, n, _kind in REGIONS:
                if w <= lon <= e and s <= lat <= n:
                    stats[name][0] += 1
                    if is_notspot:
                        stats[name][1] += 1

    if not total:
        sys.exit("No features read.")

    pct = 100.0 * notspots / total
    print(f"\nsampled       {total:,} locations")
    if args.sample > 1:
        print(f"              (every {args.sample}th line)")
    print(f"notspots      {notspots:,}  ({pct:.1f}%)")

    print("\nper-operator reading counts:")
    for op, c in sorted(ops_seen.items(), key=lambda x: -x[1]):
        print(f"  {op:<12} {c:>12,}  ({100.0*c/total:5.1f}% of locations)")

    print(f"\n{'region':<18}{'kind':<8}{'seen':>10}{'notspot':>10}{'rate':>8}")
    print("-" * 54)
    urban_rates, remote_rates = [], []
    for name, _w, _s, _e, _n, kind in REGIONS:
        seen, ns = stats[name]
        if not seen:
            print(f"{name:<18}{kind:<8}{'0':>10}{'-':>10}{'no data':>8}")
            continue
        rate = 100.0 * ns / seen
        (urban_rates if kind == "urban" else remote_rates).append(rate)
        print(f"{name:<18}{kind:<8}{seen:>10,}{ns:>10,}{rate:>7.1f}%")

    print()
    if urban_rates and remote_rates:
        u = sum(urban_rates) / len(urban_rates)
        r = sum(remote_rates) / len(remote_rates)
        print(f"mean urban notspot rate:  {u:.1f}%")
        print(f"mean remote notspot rate: {r:.1f}%")
        print()
        if u > pct * 0.6:
            print("VERDICT: suspicious. City centres are nearly as blank as")
            print("the national average, which real coverage cannot explain.")
            print("Treat absent readings as 'not measured', NOT 'no signal'.")
        elif r > u * 2:
            print("VERDICT: looks genuine. Notspots concentrate in remote")
            print("areas and are rare in cities, which is what real coverage")
            print("looks like. The layer is trustworthy - still label it as")
            print("'no reading recorded' rather than 'no signal'.")
        else:
            print("VERDICT: inconclusive. Little geographic separation.")
            print("Inspect on the map before relying on this field.")


if __name__ == "__main__":
    main()
