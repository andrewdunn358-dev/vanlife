# Research protocol — one authority, one JSON file

The operational instructions for researching a single authority. Section 7 of
[legality-research.md](legality-research.md) says *what* to capture and why;
this says how to do it and what the output must look like, tightly enough that
two people a month apart produce comparable files.

Kept in the repo rather than in a chat, because the method is the asset. The
428-body register is a decade of work at the wrong pace and only pays off if
every file is built the same way.

## Before you start
1. Read [`../data/sites/south-ayrshire.json`](../data/sites/south-ayrshire.json)
   — the gold standard for format, tone and depth. Match it.
2. Read [legality-research.md](legality-research.md) sections 4 and 7 for the
   schema rationale.

## What to find (checklist from the method doc)
1. PROVISION — does the authority run/designate overnight motorhome sites or
   aires? Names, prices, hours, max nights, self-containment rules, facilities.
   Usually one page titled motorhomes / aires / overnight parking.
2. PROVISION THE PARKING PAGES DO NOT MENTION. **Check this separately or you
   will miss it.** Campsites, caravan sites and touring pitches the authority
   itself owns or runs live in a different department and a different part of
   the site — under /parks/, countryside, leisure or tourism, never /parking/.
   Northumberland's own campsite at Druridge Bay was missed this way: nothing
   on its motorhome parking page links to it, and nothing on the campsite page
   links back. Look at:
   - country parks, and any camping or caravanning within them
   - council-owned caravan or holiday parks, including ones now let to an
     operator on a lease — record who runs it and note the lease
   - council marinas and harbours offering overnight vehicle stays
   - former district-council caravan sites inherited at reorganisation, which
     are the messiest category and are invisible from parking pages
   Record these as `kind: provision`, `instrument: landowner_policy` (a
   commercial offer is not an order), with price, season and pitch counts.
   Check ownership before recording: most coastal campsites are Haven,
   Parkdean or the clubs. Name those in notes as private supply so nobody
   re-researches them, but do not record them under this authority.
3. PROHIBITION — which legal instrument(s), covering what, what hours, what
   penalty. Distinguish restricting PARKING vs SLEEPING vs both.
4. SOURCE FORMAT — html | pdf_text | pdf_scan | map | none.
5. DIRECTION OF TRAVEL — expanding provision or tightening restriction (goes in
   notes/policy_summary).

Useful search shapes: "<name> motorhome overnight parking car parks",
"<name> campervan overnight sleeping policy", "<short> motorhome parking order
overnight". Council URL paths often live under /parking/.

## Output file
Write JSON to data/sites/<slug>.json (slug given in your task). Top-level keys:
authority (EXACT name given in your task — must match the register),
authority_type, nation, researched_on ("2026-07-27"), researched_by (short
description of source basis), source_format, sources (list of URLs actually
used), policy_summary, notes, open_questions, sites.

Each entry in sites[]:
- REQUIRED: name, kind (provision|restriction), instrument
  (off_street_parking_order|on_street_tro|etro|pspo|byelaw|opening_hours|
  policy_only|landowner_policy|unknown), status
  (in_force|draft|consultation|experimental|revoked|unknown), last_verified
  ("2026-07-27"), confidence (high|medium|low|very_low).
- restrictions additionally REQUIRE applies_to (adapted_for_sleeping|
  dvla_motor_caravan|all_vehicles|over_length|unknown) and SHOULD have
  restricts (parking|sleeping|both).
- lat/lon: real researched coordinates for named single places, with
  geocoded_by: "web_research", geocode_precision (what the pin is on),
  geocode_band (precise|approximate|area), geocode_checked: false,
  geocode_source (URL that corroborates the location), postcode if known,
  search_hint. Corroborate coordinates from a second source (park4night,
  searchforsites, ukcampsite, OSM, council map) where possible.
  NEVER INVENT COORDINATES. If you cannot locate a named place, set lat/lon
  null and say so in notes. Zone/blanket/street restrictions get lat/lon null.
  An estate-wide record may be named "All <authority> car parks" / "All other
  <authority> car parks".
- Optional fields as in the gold standard: bays, price_per_night, currency,
  max_nights, return_gap_hours, payment_methods, requires_self_contained,
  facilities, prohibits, excludes_vehicle_types, enforcement
  (anpr|patrol|fpn|pcn|signage_only|unknown), time_from, time_to, notes.

## Quality bar
- policy_summary: analytic prose in the voice of the existing files — what the
  regime actually is, what changed recently, what a van user needs to know.
  Not marketing copy, not hedge-everything mush.
- notes: the judgment/insight worth keeping (trajectory, contradictions,
  enforcement reality).
- open_questions: what you could not resolve.
- sources: only URLs you actually read and used.
- If the honest finding is "no published policy": source_format "none",
  sites: [], policy_summary states what you searched and that nothing is
  published. That is a valid, useful result. DO NOT pad.
- Paywalled commercial networks (Britstops, CAMC etc.): describe the network,
  membership model, scale, from public pages only. DO NOT scrape member-only
  site lists. sites: [] with policy_only records at network level if useful.

## Before you finish
Run: python3 scripts/validate_sites.py 2>&1 | grep -A3 "<slug>"
Your file must contribute ZERO errors (warnings about missing geometry on
zone records are fine). Fix anything it flags.

## Return value (your final message)
A compact report, NOT the JSON: slug written, 1-line regime summary, number of
sites (provision/restriction), number with coordinates, anything ambiguous a
human should check tomorrow.
