#!/usr/bin/env python3
"""
Match a vehicle against a site's requirements.

This is the core of the legality answer, and it deliberately never
returns a bare yes or no. Two reasons:

1. Orders reach for different definitions of "campervan". Cornwall's
   draft order catches any vehicle *adapted for sleeping*, even if also
   used for other purposes - a Transit with a mattress. Other orders
   target *motor caravans*, a DVLA body-type on the V5C, which many
   self-builds are not. The same van is caught by one and not the other.

2. Publishing "you may sleep here" is a liability surface (scoping doc
   section 9). Reporting which requirement fails, and on whose
   definition, is not.

So the output is a set of findings with reasons, and the UI shows the
reasoning rather than a verdict.

    python3 -m scripts.vehicle_match --demo
"""
from __future__ import annotations

import argparse
import json
from dataclasses import dataclass, field, asdict
from typing import Literal, Optional

# DVLA body types that commonly matter here. 'motor_caravan' is the only
# one that reliably satisfies orders written against that classification.
BodyType = Literal[
    "motor_caravan", "panel_van", "light_goods", "car", "minibus", "other"
]

ToiletType = Literal["none", "portable", "fixed_cassette", "fixed_tank"]

# How an order defines the vehicles it applies to.
Definition = Literal[
    "adapted_for_sleeping",  # Cornwall style - catches self-builds
    "dvla_motor_caravan",    # only V5C-classified motor caravans
    "all_vehicles",          # Eryri style - car park simply shuts
    "over_length",           # some orders bite on size alone
    "unknown",
]


@dataclass
class Vehicle:
    """The user's van. Stays on the device - no reason to send it anywhere."""

    name: str = "My van"
    height_m: Optional[float] = None
    length_m: Optional[float] = None
    width_m: Optional[float] = None
    weight_kg: Optional[int] = None

    body_type: BodyType = "motor_caravan"
    adapted_for_sleeping: bool = True

    toilet: ToiletType = "none"
    grey_water_sealed: bool = False
    black_water_sealed: bool = False

    def is_self_contained(self) -> tuple[bool, list[str]]:
        """Cornwall's test: onboard toilet plus sealed waste containers.

        Returns the verdict and what is missing. No UK certification
        scheme exists, so this is self-declared either way.
        """
        missing = []
        if self.toilet in ("none", "portable"):
            missing.append(
                "no fixed onboard toilet"
                if self.toilet == "none"
                else "portable toilet may not satisfy 'onboard toilet'"
            )
        if not self.grey_water_sealed:
            missing.append("no sealed wastewater container")
        if not self.black_water_sealed:
            missing.append("no sealed sewage container")
        return (not missing), missing


@dataclass
class Site:
    """A place, and what it requires. Geometry lives elsewhere."""

    name: str
    kind: Literal["provision", "restriction"]

    # Physical limits
    max_height_m: Optional[float] = None
    max_length_m: Optional[float] = None
    max_width_m: Optional[float] = None
    max_weight_kg: Optional[int] = None

    # Who a restriction applies to
    applies_to: Definition = "unknown"

    # Provision requirements
    requires_self_contained: bool = False

    # Provenance - mandatory in practice
    instrument: str = "unknown"
    source_url: str = ""
    last_verified: str = ""
    status: str = "unknown"


@dataclass
class Finding:
    code: str
    severity: Literal["blocks", "caution", "info"]
    message: str


@dataclass
class Result:
    site: str
    findings: list[Finding] = field(default_factory=list)

    @property
    def blocked(self) -> bool:
        return any(f.severity == "blocks" for f in self.findings)

    @property
    def uncertain(self) -> bool:
        return any(f.severity == "caution" for f in self.findings)


def _dimension_findings(v: Vehicle, s: Site) -> list[Finding]:
    out = []
    checks = (
        ("height", v.height_m, s.max_height_m, "m"),
        ("length", v.length_m, s.max_length_m, "m"),
        ("width", v.width_m, s.max_width_m, "m"),
    )
    for label, have, limit, unit in checks:
        if limit is None:
            continue
        if have is None:
            out.append(
                Finding(
                    f"{label}_unknown",
                    "caution",
                    f"Site has a {label} limit of {limit}{unit} but your "
                    f"{label} is not set.",
                )
            )
        elif have > limit:
            out.append(
                Finding(
                    f"{label}_exceeded",
                    "blocks",
                    f"Your {label} {have}{unit} exceeds the {limit}{unit} limit.",
                )
            )
    if s.max_weight_kg is not None:
        if v.weight_kg is None:
            out.append(
                Finding(
                    "weight_unknown",
                    "caution",
                    f"Site limit {s.max_weight_kg}kg but your weight is not set.",
                )
            )
        elif v.weight_kg > s.max_weight_kg:
            out.append(
                Finding(
                    "weight_exceeded",
                    "blocks",
                    f"Your {v.weight_kg}kg exceeds the {s.max_weight_kg}kg limit.",
                )
            )
    return out


def match(vehicle: Vehicle, site: Site) -> Result:
    res = Result(site=site.name)
    res.findings.extend(_dimension_findings(vehicle, site))

    if site.kind == "provision":
        if site.requires_self_contained:
            ok, missing = vehicle.is_self_contained()
            if ok:
                res.findings.append(
                    Finding(
                        "self_contained_ok",
                        "info",
                        "Meets the self-contained requirement as you have "
                        "described the van. Not independently certified - "
                        "the UK has no such scheme.",
                    )
                )
            else:
                res.findings.append(
                    Finding(
                        "self_contained_fail",
                        "blocks",
                        "Site requires a self-contained vehicle: "
                        + "; ".join(missing)
                        + ".",
                    )
                )
        return res

    # --- restriction ---
    if site.applies_to == "all_vehicles":
        res.findings.append(
            Finding(
                "applies_all",
                "blocks",
                "Applies to all vehicles regardless of type.",
            )
        )
    elif site.applies_to == "adapted_for_sleeping":
        if vehicle.adapted_for_sleeping:
            res.findings.append(
                Finding(
                    "applies_adapted",
                    "blocks",
                    "Applies to vehicles adapted for sleeping. Your van is, "
                    "so this likely applies even though it is registered as "
                    f"a {vehicle.body_type.replace('_', ' ')}.",
                )
            )
        else:
            res.findings.append(
                Finding(
                    "not_adapted",
                    "info",
                    "Applies to vehicles adapted for sleeping; yours is not.",
                )
            )
    elif site.applies_to == "dvla_motor_caravan":
        if vehicle.body_type == "motor_caravan":
            res.findings.append(
                Finding(
                    "applies_dvla",
                    "blocks",
                    "Applies to vehicles classified as motor caravans, which "
                    "yours is on the V5C.",
                )
            )
        elif vehicle.adapted_for_sleeping:
            res.findings.append(
                Finding(
                    "definition_gap",
                    "caution",
                    "Written against the DVLA 'motor caravan' classification, "
                    f"and your V5C says {vehicle.body_type.replace('_', ' ')}. "
                    "The van is adapted for sleeping though, so an enforcement "
                    "officer may take a different view from the paperwork.",
                )
            )
        else:
            res.findings.append(
                Finding(
                    "not_motor_caravan",
                    "info",
                    "Applies to motor caravans; yours is not classified as one.",
                )
            )
    else:
        res.findings.append(
            Finding(
                "definition_unknown",
                "caution",
                "The recorded order does not make clear which vehicles it "
                "covers. Treat as applying until verified.",
            )
        )

    if not site.last_verified:
        res.findings.append(
            Finding(
                "unverified",
                "caution",
                "No verification date recorded for this restriction.",
            )
        )
    return res


# --------------------------------------------------------------------------

DEMO_VEHICLES = {
    "Self-build Transit": Vehicle(
        name="Self-build Transit",
        height_m=2.6, length_m=5.98, width_m=2.0, weight_kg=3200,
        body_type="panel_van", adapted_for_sleeping=True,
        toilet="portable", grey_water_sealed=False, black_water_sealed=False,
    ),
    "Coachbuilt motorhome": Vehicle(
        name="Coachbuilt motorhome",
        height_m=3.1, length_m=7.2, width_m=2.3, weight_kg=3500,
        body_type="motor_caravan", adapted_for_sleeping=True,
        toilet="fixed_cassette", grey_water_sealed=True, black_water_sealed=True,
    ),
    "Estate car": Vehicle(
        name="Estate car",
        height_m=1.5, length_m=4.8, width_m=1.85, weight_kg=1600,
        body_type="car", adapted_for_sleeping=False,
    ),
}

DEMO_SITES = [
    Site(
        name="Cornwall designated self-contained car park",
        kind="provision", requires_self_contained=True,
        instrument="off_street_parking_order",
        last_verified="2026-07-26", status="draft",
    ),
    Site(
        name="Cornwall coastal car park (11pm-8am ban)",
        kind="restriction", applies_to="adapted_for_sleeping",
        instrument="off_street_parking_order",
        last_verified="2026-07-26", status="draft",
    ),
    Site(
        name="Eryri car park (closed 10pm-3am)",
        kind="restriction", applies_to="all_vehicles",
        instrument="opening_hours",
        last_verified="2026-07-26", status="in_force",
    ),
    Site(
        name="Gwynedd Arosfan, Criccieth",
        kind="provision", max_height_m=3.0,
        instrument="policy_only",
        last_verified="2026-07-26", status="in_force",
    ),
    Site(
        name="Hypothetical motor-caravan-only ban",
        kind="restriction", applies_to="dvla_motor_caravan",
        instrument="pspo", last_verified="",
    ),
]


def demo():
    for vname, v in DEMO_VEHICLES.items():
        print("=" * 70)
        sc, missing = v.is_self_contained()
        print(f"{vname}  ({v.body_type}, {v.height_m}m tall)")
        print(f"  self-contained: {'yes' if sc else 'no'}"
              + (f" - {'; '.join(missing)}" if missing else ""))
        print()
        for s in DEMO_SITES:
            r = match(v, s)
            flag = "BLOCKED" if r.blocked else ("CHECK" if r.uncertain else "ok")
            print(f"  [{flag:>7}] {s.name}")
            for f in r.findings:
                print(f"            - {f.message}")
        print()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--demo", action="store_true")
    ap.add_argument("--schema", action="store_true", help="dump JSON schema")
    args = ap.parse_args()
    if args.schema:
        print(json.dumps(
            {"vehicle": asdict(Vehicle()), "site": asdict(Site(name="", kind="provision"))},
            indent=2))
    else:
        demo()


if __name__ == "__main__":
    main()
