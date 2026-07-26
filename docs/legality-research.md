# Legality layer — research method and schema

**Status:** method defined, research not started
**Priority list:** [`../data/authorities-priority.csv`](../data/authorities-priority.csv) — 67 authorities, tiered

---

## 1. What the July 2026 desk research established

Five authorities were checked for how overnight restrictions are actually
imposed. They used five different mechanisms:

| Authority | Instrument |
|---|---|
| Cornwall | Off-Street Parking Order 2026 (car parks) + separate on-street TROs (residential streets) |
| North Yorkshire | Experimental TRO **and** a PSPO in parallel, different penalties |
| Gwynedd | "specific orders" covering lay-bys |
| Eryri National Park | **Changed car park opening hours.** No order at all — the car park is simply shut |
| Highland (Sutherland) | Area committee motion |

**A PSPO scraper would have caught almost none of this.** The original
scoping assumed PSPOs were the primary instrument; they are one of at
least five, and not the most common.

Eryri is the important case. Restricting parking between 10pm and 3am by
shortening opening hours is not a prohibition on sleeping — it is a
closure. Legally different, differently enforced, and invisible to any
search for "orders".

## 2. The volatility problem

Eryri restricted 11 car parks from 1 April 2026. By June the ban was set
to be scrapped, with a proposal to instead close two car parks between
1am and 3am only — a two-hour window designed purely to prevent overnight
stays while preserving dawn access.

**Ten weeks from introduction to reversal.** Any per-spot prohibition
dataset will be stale. This is not a reason to abandon the layer, but it
is a reason not to lead with it.

Enforcement is increasingly ANPR (Eryri trialled it at Llyn Tegid), so
being wrong has a price for the user.

## 3. Decision: map provision, not prohibition

Every authority that restricts also publishes what it *provides*, and
publishes it willingly.

| | Prohibition | Provision |
|---|---|---|
| Instruments to track | 5+, varying per authority | Authority publicises it themselves |
| Volatility | Reversed within 10 weeks | Capital investment; it persists |
| Legal exposure | Asserting "you may sleep here" | Reporting "the authority designated this" |
| Scale | Thousands of sites, 5 legal sources | Low hundreds, ~1 page per authority |
| Failure mode | Miss one → user is fined | Miss one → user misses a nice spot |

Known examples already found:
- **Gwynedd** — 4 Arosfan sites (Llanberis, Caernarfon, Criccieth, Pwllheli), £16.50/night, 4pm–10am
- **Cornwall** — 10 designated car parks for fully self-contained vehicles (own toilet, sealed waste containers)
- **South Ayrshire** — 20 bays each at Girvan and Ayr, £5/night, leave next day, no return for 24h

Prohibition data still gets collected where it is cheap and clear, but as
a secondary layer with visible provenance — never as the headline.

## 4. Schema

Restrictions are richer than "polygon + banned yes/no". The research
found at least these dimensions:

### Site (provision or restriction)
- `geometry` — point or polygon. **Key on geometry, not authority.**
- `authority_name`, `authority_type` — mutable attributes, see §5
- `kind` — `provision` | `restriction`
- `instrument` — `off_street_parking_order` | `on_street_tro` | `etro` | `pspo` | `byelaw` | `opening_hours` | `policy_only` | `unknown`
- `instrument_ref` — order name and date
- `source_url`, `source_format` — `html` | `pdf_text` | `pdf_scan` | `map` | `none`
- `status` — `in_force` | `draft` | `consultation` | `experimental` | `revoked`
- `date_made`, `date_expires` — PSPOs run 3 years and need renewing
- `last_verified` — mandatory, surfaced in UI and API

### Restriction detail
- `restricts` — `parking` | `sleeping` | `both`. **These are different
  offences.** Gwynedd permits parking but bans sleeping; Cornwall bans
  presence outright. A Cornwall resident was fined £70 for *leaving* a
  motorhome overnight without sleeping in it.
- `time_from`, `time_to` — e.g. 23:00–08:00, or Eryri's 22:00–03:00
- `vehicle_definition` — verbatim. Cornwall's draft order defines a
  motorhome as any vehicle *adapted for sleeping*, even if also used for
  other purposes. A part-converted Transit may or may not be caught.
- `penalty_type` — `pcn` | `fpn` | `court`; `penalty_amount`
- `enforcement` — `anpr` | `patrol` | `signage_only` | `unknown`

### Provision detail
- `price_per_night`, `arrival_from`, `departure_by`
- `max_nights`, `return_gap_hours` — South Ayrshire: 1 night, 24h gap
- `requires_self_contained` — boolean; Cornwall requires onboard toilet
  and sealed waste containers
- `facilities` — water, Elsan, waste, electric
- `height_barrier_m` — Gwynedd flags car parks larger vans cannot enter

### Vehicle-dependent answers

Whether a site is usable depends on the *vehicle*, not just the place.
Implemented in [`../scripts/vehicle_match.py`](../scripts/vehicle_match.py).

**Definitions disagree, and that is the whole problem.** Cornwall's draft
order catches any vehicle *adapted for sleeping* even if also used for
other purposes - a Transit with a mattress. Other orders target *motor
caravans*, a DVLA body type on the V5C, which many self-builds are not.
The same van is caught by one and not the other, so the profile must
carry both what the V5C says and what the vehicle actually is.

`self_contained` is not a boolean either. Cornwall's test is an onboard
toilet plus sealed containers for wastewater and sewage. That is a set of
capabilities, and in the UK it is self-declared - there is no
certification scheme.

**The matcher never returns a bare yes or no.** It returns findings with
reasons and a severity of blocks / caution / info, so the UI shows the
reasoning rather than a verdict. That is the same provenance-not-verdict
principle as section 9 of the scoping doc, and it is what keeps this
informational rather than advisory.

### Provision your vehicle cannot use is not provision

Running the matcher surfaced this and the desk research had missed it.

A self-build Transit is blocked from Cornwall's ordinary car parks
(adapted for sleeping) **and** from the ten designated alternatives (not
self-contained). Cornwall's regime therefore excludes self-builds
entirely, while appearing generous on paper.

**Consequence: the hostility index must be scored per vehicle, not per
authority.** "Cornwall provides 10 sites" is true and useless to half the
market. Personalising it also makes it a feature no competitor can copy
without the same schema.

## 5. Never key on authority identity

On 16 July 2026 the government confirmed reorganisation decisions
replacing **134 English councils with 38 unitary authorities**, first
elections May 2027, full powers 1 April 2028. East and West Surrey
already replaced a county and eleven districts.

A dataset keyed on council names loses a third of its keys in 2028.
Geometry is stable; authorities are not. Store the authority as an
attribute with valid-from and valid-to dates.

## 6. Two-tier areas need both tiers

England still has 20 county councils over 153 districts. In those areas:
- **District** usually owns and regulates the car parks → off-street orders
- **County** is the highways authority → on-street TROs and lay-bys

So Cornwall is one research job and Devon is nine. The priority list
records `two_tier_partner` for this reason.

Also not councils, and all own car parks or land vans use:
National Park Authorities (15 UK-wide), Forestry England, Forestry and
Land Scotland, Natural Resources Wales, National Trust, National Trust
for Scotland, Crown Estate, harbour and trust ports, and some town and
parish councils.

## 6c. Locating sites at scale

Hand-entering coordinates does not scale past one county, and the app
cannot ask users to do it either. The first attempt used a geocoder,
which was the wrong tool: Nominatim guesses what a name means and
returned village centres, road segments, and for Fontburn Reservoir, the
middle of the water.

**Feature extraction, not geocoding.** OpenStreetMap tags car parks as
`amenity=parking` with good UK coverage. Overpass returns every one in an
area with real geometry; records are then matched against that list by
name and proximity.

Tested on the Northumberland records: Fontburn went from the middle of
the reservoir to Fontburn Reservoir Car Park 415m away at 0.98
confidence. Kielder matched at 1.00. Ambiguous cases are reported rather
than written — Bamburgh scored 0.59 with Bamburgh Castle Car Park a close
second, and Llanberis scored 0.50 because OSM names it *Maes Parcio*.

    python3 scripts/fetch_carparks.py --area Northumberland --operator
    python3 scripts/match_carparks.py
    python3 scripts/match_carparks.py --write

One Overpass query per county, then confirmation of the weak matches.
That scales; typing coordinates does not.

### It also solves the blanket restrictions

"All other Northumberland County Council car parks" cannot be mapped
today because it is not a place. With the full car park list for the
county — and OSM's `operator` tag to identify council-run ones — it
becomes every parking area minus the three permitted bays. That converts
the largest unmappable category in the dataset into ordinary geometry.

OSM also carries `maxheight`, `capacity`, `fee` and `access` tags, which
feed straight into the vehicle matcher. The height barriers Gwynedd
mentions but does not list are partly already in OSM.

Licence: OSM data is ODbL. Attribution is required on anything derived
from it.

## 7. Per-authority research checklist

For each authority, capture:

1. **Provision** — does it run designated overnight sites? Names, prices,
   hours, rules, self-containment requirement. Usually one page, often
   titled motorhomes, aires, Arosfan or similar.
2. **Prohibition** — which instrument, covering what, what hours, what
   penalty. Note whether it restricts parking, sleeping, or both.
3. **Source format** — HTML, text PDF, scanned PDF, map, or nothing
   published. **This determines whether Phase 2 is a scraper or manual
   transcription, and it is the single most important field to collect
   early.**
4. **D-TRO presence** — does anything appear in the DfT service for this
   authority yet? Tests whether the free national source is useful in
   practice or only in principle.
5. **Direction of travel** — expanding provision or tightening
   restriction? This feeds the hostility index.

## 8. Hostility index

Derivable from the above, and nobody publishes it:

- count of restricted sites
- count of provided sites
- ratio of provision to restriction
- penalty severity
- whether a PSPO is stacked on top of a parking order
- whether provision is growing or shrinking

Early read from the desk research: Conwy has some non-provisioned bays
but otherwise bans overnight parking, while Gwynedd, Anglesey and
Denbighshire are all trialling or expanding provision. So North Wales
splits sharply, and "hostile" is not binary — Cornwall is restrictive
*with* provision, which is a different thing from restrictive without.

## 9. Full authority list

The 67 in the priority CSV are the ones that matter for vans. For a
canonical full list of all ~372 UK authorities, use the ONS Open
Geography Portal or the Register of Geographic Codes rather than
hand-maintaining one — and re-fetch it after April 2028.
