# Vanlife App — Scoping & Architecture

**Status:** concept / pre-build
**Date:** July 2026
**Working name:** TBD
**Repo:** https://github.com/andrewdunn358-dev/vanlife

**Repo description:** Computed map layers for UK vanlife — overnight legality, measured mobile signal, and solar yield forecasting. Offline-first, with a public API.

---

## 1. Proposition

A campervan and vanlife app for the UK that answers three questions no existing app answers well:

1. **Can I legally stay here overnight?** — sourced from actual traffic orders and PSPOs, not anecdote.
2. **Will I have signal here?** — from real measured drive-test data, not operator marketing maps.
3. **Will my solar keep up?** — yield forecast for a specific spot and a specific electrical system.

Everything else (POIs, campsites, services, reviews) is table stakes and exists purely to make the app worth opening daily.

## 2. Positioning

The incumbents — Park4Night, Searchforsites, Campercontact, iOverlander — own crowd-sourced POI density. That fight is unwinnable from zero.

**The wedge is computed layers, not crowd-sourced pins.** Every differentiator above is derived from public data or physics. It ships complete on day one with no user base, and it cannot be copied by a competitor without equivalent data engineering effort.

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
| Mobile signal | Ofcom drive-test open data | Free bulk CSV | ~14GB 4G, ~50GB 5G. Measured along roads. Ideal geometry for a van app. |
| Mobile coverage | Ofcom Connected Nations Mobile API | Free, registration required | Per-operator fields. Postcode granularity — too coarse to replace drive-test, useful as online supplement. |
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

**Phase 1 — Signal layer**
Ofcom bulk download → GeoJSON → Tippecanoe → PMTiles → map. No database, no permissions, no scraping, no partners. Fastest path to something demonstrably unique.

*Open question this phase answers:* is the drive-test data dense enough off the A-roads to be useful in the rural places vans actually go? Nothing else in this document matters until that's known.

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
- Whether the legality layer covers PSPOs only or all instrument types (see section 4)
- Solo build or bring in help for the app layer
- Whether to court landowners early (Britstops-style) or stay pure discovery
- API pricing — free tier, or paid from the start
- **Who this is for.** Full-timers, weekenders, or Euro-tourers. The signal layer implies remote workers, which is a small, high-willingness-to-pay niche and a different product from a weekender discovery app. Naming this resolves half of the above.

## 8. Risks

**Legal.** Publishing "you can legally stay here" is a liability surface. Data will be incomplete and will go stale. Needs careful UI framing — informational, never advisory — and a solicitor's review of disclaimer wording before launch, not after.

Framing that reduces this: never render a verdict. Show *"no restriction found in the 3 sources checked, last verified [date]"* with links, rather than a green tick. Reframes from advisory to provenance, which is both cheaper legally and more honest about the data.

**API extends the liability chain.** If VanOS or a third party tells a user "you can stay here" using this data and it's wrong, this project sits in that chain. Terms of use in place before the first third-party key is issued, not after. Provenance and last-verified dates in every API response, not just in the app UI.

**Data staleness.** D-TRO coverage is incomplete and PSPOs change — they run for up to three years and are then extended or dropped. Every record needs a visible "last verified" date and provenance link.

**Cold start on POIs.** The computed layers carry v1, but POI density has to come from somewhere eventually. Consider OSM import as a seed.

**Scope.** Six phases is a lot for a side project alongside an MSP. Phase 1 alone is a shippable product — treat everything after as optional.

**Phase ordering vs user pull.** The build order optimises for tractability: Phase 1 is easiest to build and least likely to make anyone download an app. The feature that actually sells is Phase 3, and it is the hardest. Ship Phase 1 to prove the data, but do not assume it is the launch.
