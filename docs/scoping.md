# Vanlife App — Scoping & Architecture

**Status:** Phase 1 complete — signal layer tested and rejected. See section 8.
**Date:** July 2026
**Working name:** TBD
**Repo:** https://github.com/andrewdunn358-dev/vanlife

**Repo description:** Computed map layers for UK vanlife — overnight legality, measured mobile signal, and solar yield forecasting. Offline-first, with a public API.

---

## 1. Proposition

A campervan and vanlife app for the UK that answers three questions no existing app answers well:

1. **Can I legally stay here overnight?** — sourced from actual traffic orders and PSPOs, not anecdote.
2. ~~**Will I have signal here?** — from real measured drive-test data, not operator marketing maps.~~
   **Withdrawn.** Ofcom's drive-test data does not cover the places vans go. See section 8.
   If signal returns, it must come from modelled national coverage, honestly labelled as modelled.
3. **Will my solar keep up?** — yield forecast for a specific spot and a specific electrical system.

Everything else (POIs, campsites, services, reviews) is table stakes and exists purely to make the app worth opening daily.

## 2. Positioning

The incumbents — Park4Night, Searchforsites, Campercontact, iOverlander — own crowd-sourced POI density. That fight is unwinnable from zero.

**The wedge is computed layers, not crowd-sourced pins.** Every differentiator above is derived from public data or physics. It ships complete on day one with no user base, and it cannot be copied by a competitor without equivalent data engineering effort.

**Revised July 2026:** with signal withdrawn, the wedge narrows to *legality*. That is now the single load-bearing differentiator, and the phase plan should reflect that rather than treating it as third in a queue. Solar is a supporting feature, not a wedge — the physics is public and any competitor can compute it.

Secondary differentiator: **offline-first**. Vans live in signal blackspots. Full offline map and POI database is a genuine moat against web-first competitors.

**Third position: data provider, not just app.** With a public API, the computed layers become infrastructure other products build on. Nobody else has UK overnight legality as a queryable dataset. This is plausibly more defensible than the app itself — an app can be cloned, a maintained dataset cannot.

## 3. Scope

- **Geography:** UK. Note the legality layer is *England-first* — D-TRO covers England; Scotland and Wales need separate handling.
- **Platform:** native app (offline maps, background location) + public website for SEO and spot pages.
- **API.** A public read API exposing the computed layers — legality, signal, solar — for third-party and first-party clients. VanOS is the initial consumer, which makes it the reference implementation. Responses carry provenance and last-verified dates; the API states what was found in which sources, never whether staying somewhere is permitted.
- **Out of scope for v1:** Europe, bookings/payments, social feed.

## 4. Data sources

| Layer | Source | Access | Notes |
|---|---|---|---|
| Traffic orders | DfT D-TRO service | Free API, GitHub auth | Public beta since Sept 2025; v4.0.0 production from end May 2026. Coverage patchy — authorities still retro-digitising. England only. |
| Overnight bans | Council PSPOs | Manual scrape, per-council | The real differentiator. Not centralised anywhere. Start with coastal + national park councils. Manifesto Club FOI surveys are a useful seed. |
| Off-street parking orders | Council parking orders (RTRA 1984) | Manual, per-council | **Gap in original scoping.** Many "no overnight sleeping" signs in council car parks are parking place orders, not PSPOs. Resolve instrument scope before Phase 3. |
| Mobile signal | Ofcom drive-test open data | Free bulk CSV | **Tested and rejected as a primary layer — see section 8.** Retained as a validation overlay. 12M rows = 1.38M places = ~4% of UK roads. Published annually per year, not one file: 2025 4G is a 250MB zip expanding to 7.1GB. Covers ~13% of UK land area at best, effectively far less. |
| Mobile coverage | Ofcom Mobile Coverage API | Free, 50k calls/month | **Promoted to primary signal source.** Not merely postcode-level: predictions are modelled on a 50m grid over the entire UK land mass. Per-operator, voice and data, indoor and outdoor. Scale is 4 likely / 3 limited / 0 none. Register at api.ofcom.org.uk. |
| Solar irradiance | Open-Meteo | Free API | Shortwave radiation forecast. |
| Terrain / shading | EA LIDAR composite DSM (1m) | Free, open licence | **Revised from OS Terrain 50.** A 50m DTM cannot see trees, which dominate shading at van-parking scale. DSM includes vegetation and buildings. England coverage good; NRW has 1m for Wales. |
| Base map | OpenStreetMap | Free | Also source for `maxheight` tags. |
| Height restrictions | OSM + Network Rail bridge data | Free | For van-dimension routing. |

## 5. Architecture

**Split the workload — heavy processing at home, thin serving of static files.**

The serving layer is thinner than originally assumed. Every read path can be precomputed: signal, legality and height data ride inside the tiles as feature attributes and are queried on-device by MapLibre. This satisfies the offline-first requirement for free and removes most of the need for a live backend.

### Home — HP ProLiant ML110 Gen9 (Pentium G4400, 8GB)
Running DSM with Docker. Test platform; everything containerised so it moves elsewhere unchanged.

- ETL pipelines: Ofcom CSV ingest, D-TRO nightly sync, PSPO scrapers
- Tile generation: Tippecanoe → PMTiles
- PostGIS — **only from Phase 2.** Phase 1 goes CSV → GeoJSON → Tippecanoe with no database at all.
- Output: upload PMTiles and prebuilt SQLite to object storage

Constraints: two cores, no hyperthreading — tile builds are overnight jobs. 8GB total with DSM taking a share, so never run ETL and serving concurrently, and set per-container memory limits. Upgrade path if needed: ECC **UDIMM** (not RDIMM) to 32GB, ~£40; Xeon E3-1230 v5 for 4c/8t, ~£30-40.

### Serving
- **Cloudflare R2** — PMTiles and offline packs. Zero egress fees, edge-cached. ~£0.30/month. Non-negotiable: never serve tiles from home broadband or shared hosting.
- **Static site** — generated spot pages, one per parking area, for SEO. Cloudflare Pages (free) or 20i.
- **Cloudflare Tunnel** — exposes anything dynamic without port forwarding, static IP or CGNAT problems.
- **Django + DRF** — API layer. Deferred until the API and community features need it.

### Client
- Expo / React Native — one codebase, iOS + Android
- MapLibre GL — renders PMTiles directly, works offline
- Local SQLite mirror for offline POI database

### Why this shape
- No raw bulk data on rented disk
- Tile bandwidth cached at edge, effectively free
- ETL can run for hours without serverless timeouts
- Phases 1–4 need no running server at all
- Everything in Docker, so the host is a config change rather than a rebuild

### Portability rules
The host has changed four times during scoping. These make the next change cheap:
- Everything reproducible from the repo — `compose.yaml`, `.env.example`, bootstrap script. Nothing hand-configured and remembered.
- No secrets or hostnames baked into images. Environment variables only.
- A restore that has actually been tested. A `pg_dump` never restored is not a backup.

## 6. Phases

**Phase 1 — Signal layer — COMPLETE, NEGATIVE RESULT**
Built, ran, answered its question. The drive-test data is not dense enough off the trunk network. See section 8. Pipeline retained: it is the same shape every later layer needs.

**Phase 1b — Legality layer is now the first product phase.**
Formerly phases 2 and 3. This is the only remaining differentiator and should be built next, before solar and before POIs.

**Revised again after desk research, 26 July 2026 — see [legality-research.md](legality-research.md).** Lead with *provision*, not prohibition: designated overnight sites are published willingly by authorities, stable, legally safe to report, and number in the low hundreds rather than thousands. Prohibition becomes a secondary layer. The hostility index falls out of the ratio between them.

Key structural finding: overnight restrictions are imposed through at least five different instruments — off-street parking orders, on-street TROs, experimental TROs, PSPOs, and simply changing car park opening hours. The original PSPO-scraper plan would have caught almost none of them.

**Phase 2 — D-TRO integration**
Register for API access, sync England data. PostGIS enters here. UI must be explicit about coverage gaps rather than implying completeness.

**Phase 3 — PSPO scraper**
Target ~30 councils covering coast and national parks first. That's where enforcement pain actually is, at a fraction of the work of all 300+. Resolve the instrument-scope question first (see section 4).

**Phase 4 — Solar**
Open-Meteo + LIDAR DSM horizon shading. Optional Victron VRM integration for personalised yield. Consider whether horizon shading earns its place in v1 — panel angle, dirt, temperature derating and MPPT behaviour may swamp it.

**Phase 5 — POIs and community**
Services (water, Elsan, LPG with connector type), campsites, reviews. Karma-gated fragile spots. First phase that genuinely requires a running backend.

**Phase 6 — Public API**
Formalise what VanOS already consumes. Keys, rate limits, terms of use, provenance in every response.

## 7. Open questions

- Working name and domain
- Free vs paid split — assumption: POIs free, legality/solar/offline packs paid. Consider inverting: offline packs and routing are the clean paid features, since they carry no accuracy liability.
- Whether PSPO scraping is per-council bespoke or a generalisable pipeline
- ~~Whether the legality layer covers PSPOs only or all instrument types~~ **Answered:** at least five instruments, PSPOs are a minority. See legality-research.md.
- Whether prohibition data is worth collecting at all given ten-week reversal cycles, or whether provision plus hostility index is the whole product
- Solo build or bring in help for the app layer
- Whether to court landowners early (Britstops-style) or stay pure discovery
- API pricing — free tier, or paid from the start
- **Who this is for.** Full-timers, weekenders, or Euro-tourers. The signal layer implies remote workers, which is a small, high-willingness-to-pay niche and a different product from a weekender discovery app. Naming this resolves half of the above.

## 8. Findings

### 2026-07-26 — Ofcom drive-test data rejected as a signal layer

**Ran:** 2025 4G LTE dataset, full pipeline, 12,066,912 locations parsed with zero coordinate failures and zero points outside UK bounds. Clean, well-formed data.

**Finding 1 — the notspot field is not a coverage measurement.**
31.6% of locations had no reading from any operator. That looked like a major discovery until checked geographically:

| Area | Notspot rate |
|---|---|
| National | 31.6% |
| Birmingham | 32.7% |
| Manchester | 32.4% |
| Glasgow | 32.8% |
| Bristol | 32.1% |

City centres cannot match the national blank rate. Confirmed independently by per-operator counts: Three 68.0%, O2 68.0%, Vodafone 68.0%, EE 67.7% — four networks with different mast estates and spectrum do not independently read at the same share of locations. The blanks are unrecorded rows, not notspots.

**Consequence:** absent readings must never render as "no signal" anywhere in the product.

**Finding 2 — the data does not cover where vans go.** This is the decisive one.

Zero measurements across five sampled remote areas: NW Highlands, Cambrian Mountains, Rannoch Moor, Upper Teesdale, Kielder. Manchester alone returned 18,450 points in an identically sized box.

Grid analysis: 427 cells at 0.1° ≈ 12–13% of UK land area. And that overstates it, since one road through a 73km² cell marks the whole cell as covered. Usable coverage at lay-by granularity is a fraction of a percent.

**Cause:** Ofcom collects this as their spectrum assurance vehicles go about routine business — interference investigations and the like. It is not a survey. Coverage follows where their engineers drive: cities and trunk roads.

**Decision:** proposition #2 withdrawn. Options considered:

1. **Lead with legality instead.** Chosen. It was always the feature people would pay for, and the doc's own risk section predicted this.
2. Switch to Ofcom Connected Nations modelled coverage — complete nationally, postcode granularity, but modelled. Contradicts the original "not marketing maps" positioning. Possible later if labelled honestly.
3. Keep drive-test data for trunk-road route planning only. Genuine but minor; not a wedge.

**Cost of finding this out:** one afternoon and £0. This is what Phase 1 was for, and it worked exactly as intended — the plan was right even though the answer was no.

**Retained value:** the ETL pipeline, tile build, viewer and repo discipline all transfer unchanged to the legality layer. Nothing built is wasted.

### 2026-07-26 (later) — structural analysis: 12M rows is 1.38M places

Followed up on odd patterns in a Bristol lookup. Three findings, each of which made the dataset smaller than the last.

**Coordinates are raw GPS, not snapped.** 6dp dominant, gaps down to 0.000001 deg. So distances are genuine.

**Massive stationary-logging bias.** At 6dp there appear to be 8,682,915 distinct locations. Rounded to 4dp (~11m) that collapses to **1,381,229** — 8.74 rows per real place. Centimetre GPS jitter from parked vehicles was reading as distinct places. The eight busiest single locations account for 1.42% of all 12M rows; they are Ofcom depots and offices, not survey coverage.

A Bristol postcode query returned 23,489 raw rows within 2km, of which only 1,816 were distinct spots. 92% were repeat logs.

**The notspot artefact, resolved.** Rate by row is 31.7%. By location at 6dp it is also 31.6% — which initially killed the time-bin hypothesis. But by location at 11m it is **5.2%**. Jitter had been splitting each place into dozens of pseudo-locations, hiding the pattern. Blank rows are indeed missing measurements at places that recorded fine at other times. 5.2% is a plausible genuine figure.

**Revised scale.** 1.38M places at ~11m spacing is on the order of 15,000 km of road, against a UK network of roughly 420,000 km — about **4% of UK roads**. That supersedes the earlier 13%-of-land-area figure, which was generous.

**Where this leaves the data.** Trustworthy where it exists, and where it exists is ~4% of the network, concentrated in cities. Even central Bristol's nearest reading to a city-centre postcode is 386m away.

**Consequences carried forward:**
- Any statistic over these rows must dedupe to ~11m first, or it measures where vans parked. `coverage_lookup.py` does this; the effect on Bristol medians was 1-3 dB.
- Absent readings are missing data. Never render as "no signal".
- Signal, if it ships at all, comes from Ofcom's Mobile Coverage API — modelled, 50m grid, whole UK, free to 50k calls/month. The drive-test data becomes a *validation* overlay: "the model says likely here, and N real measurements nearby agree/disagree". That is a defensible position nobody else occupies, and it needs both datasets.

**Method note.** Three hypotheses died in sequence here (genuine notspots, then time bins, then time bins again at the wrong resolution). Each check cost minutes and each one changed the answer. Worth remembering before trusting a headline number from a new dataset.

## 9. Risks

**Legal.** Publishing "you can legally stay here" is a liability surface. Data will be incomplete and will go stale. Needs careful UI framing — informational, never advisory — and a solicitor's review of disclaimer wording before launch, not after.

Framing that reduces this: never render a verdict. Show *"no restriction found in the 3 sources checked, last verified [date]"* with links, rather than a green tick. Reframes from advisory to provenance, which is both cheaper legally and more honest about the data.

**API extends the liability chain.** If VanOS or a third party tells a user "you can stay here" using this data and it's wrong, this project sits in that chain. Terms of use in place before the first third-party key is issued, not after. Provenance and last-verified dates in every API response, not just in the app UI.

**Data staleness.** D-TRO coverage is incomplete and PSPOs change — they run for up to three years and are then extended or dropped. Every record needs a visible "last verified" date and provenance link.

**Cold start on POIs.** The computed layers carry v1, but POI density has to come from somewhere eventually. Consider OSM import as a seed.

**Scope.** Six phases is a lot for a side project alongside an MSP. Phase 1 alone is a shippable product — treat everything after as optional.

**Phase ordering vs user pull.** The build order optimises for tractability: Phase 1 is easiest to build and least likely to make anyone download an app. The feature that actually sells is Phase 3, and it is the hardest. Ship Phase 1 to prove the data, but do not assume it is the launch.
