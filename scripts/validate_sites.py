#!/usr/bin/env python3
"""
Validate site research files and report progress against the priority list.

Run this after every research session. It catches the mistakes that
matter - missing provenance, missing verification dates, sites published
without geometry - and shows how much of the priority list is done.

    python3 scripts/validate_sites.py
    python3 scripts/validate_sites.py --publishable
"""
import argparse
import csv
import glob
import json
import os
import sys
from datetime import date

REQUIRED_TOP = ("authority", "nation", "researched_on", "source_format", "sites")
REQUIRED_SITE = ("name", "kind", "instrument", "status", "last_verified", "confidence")
VALID_KIND = {"provision", "restriction"}
VALID_INSTRUMENT = {
    "off_street_parking_order", "on_street_tro", "etro", "pspo",
    "byelaw", "opening_hours", "policy_only", "landowner_policy", "unknown",
}
VALID_STATUS = {
    "in_force", "draft", "consultation", "experimental", "revoked", "unknown",
}
VALID_CONFIDENCE = {"high", "medium", "low", "very_low"}
VALID_APPLIES = {
    "adapted_for_sleeping", "dvla_motor_caravan", "all_vehicles",
    "over_length", "unknown",
}


def check_file(path):
    errors, warnings = [], []
    try:
        d = json.load(open(path, encoding="utf-8"))
    except json.JSONDecodeError as e:
        return [f"invalid JSON: {e}"], [], None

    for k in REQUIRED_TOP:
        if k not in d:
            errors.append(f"missing top-level '{k}'")
    if errors:
        return errors, warnings, None

    if not d.get("sources"):
        warnings.append("no source URLs recorded - findings are unattributable")

    for i, s in enumerate(d["sites"]):
        tag = f"site[{i}] {s.get('name', '?')!r}"
        for k in REQUIRED_SITE:
            if k not in s:
                errors.append(f"{tag}: missing '{k}'")
        if s.get("kind") not in VALID_KIND:
            errors.append(f"{tag}: kind {s.get('kind')!r} not in {sorted(VALID_KIND)}")
        if s.get("instrument") not in VALID_INSTRUMENT:
            errors.append(f"{tag}: instrument {s.get('instrument')!r} invalid")
        if s.get("status") not in VALID_STATUS:
            errors.append(f"{tag}: status {s.get('status')!r} invalid")
        if s.get("confidence") not in VALID_CONFIDENCE:
            errors.append(f"{tag}: confidence {s.get('confidence')!r} invalid")
        if s.get("kind") == "restriction":
            if s.get("applies_to") not in VALID_APPLIES:
                errors.append(f"{tag}: restriction needs a valid applies_to")
            if not s.get("restricts"):
                warnings.append(
                    f"{tag}: no 'restricts' - parking and sleeping are "
                    "different offences"
                )
        if s.get("lat") is None or s.get("lon") is None:
            warnings.append(f"{tag}: no geometry - cannot be mapped")
    return errors, warnings, d


def publishable(site, parent):
    """Would it be safe to show this to a user?"""
    reasons = []
    if site.get("lat") is None:
        reasons.append("no geometry")
    if site.get("confidence") in ("low", "very_low"):
        reasons.append(f"confidence {site['confidence']}")
    if site.get("status") == "unknown":
        reasons.append("status unknown")
    if not parent.get("sources"):
        reasons.append("no source URL")
    if parent.get("warning"):
        reasons.append("file carries a warning")
    return (not reasons), reasons


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", default="data/sites")
    ap.add_argument("--priority", default="data/authorities-priority.csv")
    ap.add_argument("--publishable", action="store_true")
    args = ap.parse_args()

    files = sorted(glob.glob(os.path.join(args.dir, "*.json")))
    if not files:
        sys.exit(f"No site files in {args.dir}")

    total_err = total_warn = 0
    done = {}
    all_sites = []

    for path in files:
        errors, warnings, d = check_file(path)
        name = os.path.basename(path)
        if errors or warnings:
            print(f"\n{name}")
            for e in errors:
                print(f"  ERROR   {e}")
            for w in warnings:
                print(f"  warn    {w}")
        total_err += len(errors)
        total_warn += len(warnings)
        if d:
            done[d["authority"]] = d
            for s in d["sites"]:
                all_sites.append((d, s))

    print(f"\n{'='*62}")
    print(f"{len(files)} files, {len(all_sites)} sites, "
          f"{total_err} errors, {total_warn} warnings")

    prov = sum(1 for _d, s in all_sites if s.get("kind") == "provision")
    rest = len(all_sites) - prov
    print(f"provision {prov}   restriction {rest}")

    ok = [1 for d, s in all_sites if publishable(s, d)[0]]
    print(f"publishable right now: {len(ok)} of {len(all_sites)}")

    if args.publishable:
        print("\nwhy sites are not publishable:")
        for d, s in all_sites:
            good, reasons = publishable(s, d)
            if not good:
                print(f"  {s['name'][:44]:<46} {', '.join(reasons)}")

    # progress against the priority list
    if os.path.exists(args.priority):
        rows = list(csv.DictReader(open(args.priority, encoding="utf-8")))
        by_tier = {}
        for r in rows:
            t = r["priority"]
            by_tier.setdefault(t, []).append(r["authority"])
        print("\nprogress against priority list:")
        for t in sorted(by_tier):
            names = by_tier[t]
            hit = sum(1 for n in names if n in done)
            print(f"  tier {t}   {hit:>2} / {len(names):>2} researched")
        missing1 = [n for n in by_tier.get("1", []) if n not in done]
        if missing1:
            print("\n  tier 1 still to do:")
            for n in missing1:
                print(f"    - {n}")

    print()
    sys.exit(1 if total_err else 0)


if __name__ == "__main__":
    main()
