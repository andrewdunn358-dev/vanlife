#!/usr/bin/env python3
"""
Build the master research register of UK authorities to check.

Source: mysociety/uk_local_authority_names_and_codes, which is maintained
specifically to track authorities as they merge and dissolve - which
matters here, because 134 English councils become 38 unitaries by April
2028.

Merges in the hand-assigned priority tiers from authorities-priority.csv
and emits a register with empty research columns to fill in.

    python3 scripts/build_register.py
    python3 scripts/build_register.py --refresh   # re-download source
"""
import argparse
import csv
import os
import subprocess
import sys

SRC = "data/reference/uk_la_current.csv"
FUTURE = "data/reference/uk_la_future.csv"
PRIORITY = "data/authorities-priority.csv"
OUT = "data/research-register.csv"

BASE = (
    "https://raw.githubusercontent.com/mysociety/"
    "uk_local_authority_names_and_codes/main/docs/data"
)

# Authority types that do not run car parks or highways, so cannot impose
# the restrictions this project tracks.
SKIP_TYPES = {"Combined authority", "Strategic Regional Authority", "City corporation"}

# Urban types kept in the register but never prioritised - vans do not
# park overnight in Tower Hamlets or Sandwell.
URBAN_TYPES = {"London borough", "Metropolitan district"}

NATIONAL_PARKS = [
    ("Dartmoor National Park Authority", "England", 50.5714, -3.9214),
    ("Exmoor National Park Authority", "England", 51.1400, -3.6500),
    ("Lake District National Park Authority", "England", 54.4609, -3.0886),
    ("New Forest National Park Authority", "England", 50.8700, -1.6000),
    ("North York Moors National Park Authority", "England", 54.3700, -0.8900),
    ("Northumberland National Park Authority", "England", 55.3000, -2.2000),
    ("Peak District National Park Authority", "England", 53.3400, -1.7800),
    ("South Downs National Park Authority", "England", 50.9200, -0.7500),
    ("Yorkshire Dales National Park Authority", "England", 54.2300, -2.1600),
    ("The Broads Authority", "England", 52.6300, 1.5000),
    ("Eryri National Park Authority", "Wales", 52.9000, -3.9000),
    ("Pembrokeshire Coast National Park Authority", "Wales", 51.8000, -5.0000),
    ("Bannau Brycheiniog National Park Authority", "Wales", 51.8800, -3.4300),
    ("Cairngorms National Park Authority", "Scotland", 57.0800, -3.6700),
    ("Loch Lomond and The Trossachs National Park Authority", "Scotland", 56.2400, -4.6000),
]

RESEARCH_COLUMNS = [
    "priority",
    "pressure_reason",
    "source_format",       # html | pdf_text | pdf_scan | map | none | unknown
    "provision_url",
    "restriction_url",
    "has_provision",       # yes | no | unknown
    "instrument_seen",
    "researched_on",
    "researched_notes",
]


def refresh():
    os.makedirs("data/reference", exist_ok=True)
    for name, path in (
        ("uk_la_past_current/latest/uk_local_authorities_current.csv", SRC),
        ("uk_la_future/latest/uk_local_authorities_future.csv", FUTURE),
    ):
        url = f"{BASE}/{name}"
        print(f"fetching {url}", file=sys.stderr)
        subprocess.run(
            ["curl", "-sS", "--max-time", "60", "-o", path, url], check=True
        )


def load_priority():
    """Map authority name -> (tier, reason), tolerant of naming differences."""
    if not os.path.exists(PRIORITY):
        return {}
    out = {}
    for r in csv.DictReader(open(PRIORITY, encoding="utf-8-sig")):
        out[normalise(r["authority"])] = (r["priority"], r["pressure_reason"])
    return out


ALIASES = {
    "bcp": "bournemouth christchurch and poole",
    "na h-eileanan siar": "eilean siar",
    "western isles": "eilean siar",
}


def normalise(name):
    n = name.lower().replace(",", " ").replace("&", "and")
    for junk in (
        " county borough council", " county borough", " borough council",
        " city council", " county council", " district council", " council",
        " national park authority", " national park", " authority",
        "cyngor ", "the ", " islands", " np", " comhairle",
    ):
        n = n.replace(junk, " ")
    n = " ".join(n.split())
    return ALIASES.get(n, n)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--refresh", action="store_true")
    args = ap.parse_args()

    if args.refresh or not os.path.exists(SRC):
        refresh()

    rows = list(csv.DictReader(open(SRC, encoding="utf-8-sig")))
    current = [
        r for r in rows
        if (r.get("current-authority") or "").strip().lower() in ("true", "yes", "1")
    ]
    priority = load_priority()

    register, matched = [], set()
    for r in current:
        t = r["local-authority-type-name"]
        if t in SKIP_TYPES:
            continue

        key = normalise(r["nice-name"] or r["official-name"])
        tier, reason = priority.get(key, ("", ""))
        if tier:
            matched.add(key)
        elif t in URBAN_TYPES:
            tier = "4"
            reason = "urban - not a vanlife destination"
        else:
            tier = "4"

        register.append({
            "authority": r["official-name"],
            "short_name": r["nice-name"],
            "gss_code": r["gss-code"],
            "nation": r["nation"],
            "region": r["region"],
            "type": t,
            "powers": r["powers"],
            "parent_county": r.get("county-la", ""),
            "lat": r.get("lat", ""),
            "long": r.get("long", ""),
            "population": r.get("pop-2020", ""),
            "gov_uk_slug": r.get("gov-uk-slug", ""),
            "wdtk_id": r.get("wdtk-id", ""),
            "priority": tier,
            "pressure_reason": reason,
            "source_format": "",
            "provision_url": "",
            "restriction_url": "",
            "has_provision": "",
            "instrument_seen": "",
            "researched_on": "",
            "researched_notes": "",
        })

    # National Park Authorities are not local authorities, so they are
    # absent from the mySociety dataset - but they own car parks and set
    # their own rules. Eryri restricted 11 of them in April 2026. They
    # have to be in the register.
    for name, nation, lat, lon in NATIONAL_PARKS:
        key = normalise(name)
        tier, reason = priority.get(key, ("2", "national park - owns car parks"))
        if key in priority:
            matched.add(key)
        register.append({
            "authority": name, "short_name": name.replace(" National Park Authority", ""),
            "gss_code": "", "nation": nation, "region": nation,
            "type": "National Park Authority", "powers": "national park",
            "parent_county": "", "lat": lat, "long": lon, "population": "",
            "gov_uk_slug": "", "wdtk_id": "",
            "priority": tier, "pressure_reason": reason,
            "source_format": "", "provision_url": "", "restriction_url": "",
            "has_provision": "", "instrument_seen": "",
            "researched_on": "", "researched_notes": "",
        })

    register.sort(key=lambda r: (r["priority"], r["nation"], r["authority"]))

    cols = list(register[0].keys())
    with open(OUT, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=cols)
        w.writeheader()
        w.writerows(register)

    from collections import Counter
    print(f"\nwrote {OUT}  -  {len(register)} authorities")
    print(f"\nby priority: {dict(sorted(Counter(r['priority'] for r in register).items()))}")
    print(f"by nation:   {dict(Counter(r['nation'] for r in register).items() if False else Counter(r['nation'] for r in register))}")
    print(f"by powers:   {dict(Counter(r['powers'] for r in register))}")

    unmatched = set(priority) - matched
    if unmatched:
        print(f"\n{len(unmatched)} hand-listed names did not match the register:")
        for u in sorted(unmatched):
            print(f"   {u}")
        print("\n(National Park Authorities are expected here - they are not")
        print(" local authorities and are not in the mySociety dataset.)")


if __name__ == "__main__":
    main()
