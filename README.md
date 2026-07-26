# vanlife

Computed map layers for UK vanlife — overnight legality, measured mobile
signal, and solar yield forecasting. Offline-first, with a public API.

See [`docs/scoping.md`](docs/scoping.md) for the full design.

**Status:** Phase 1. Nothing here is a product yet.

---

## What Phase 1 is

Turn Ofcom's drive-test measurements into a map, and find out whether the
data is dense enough off the A-roads to be worth building on. That single
question decides whether the rest of the project has legs.

No database, no API, no server. A CSV goes in, a `.pmtiles` file comes
out, and a web page draws it.

```
Ofcom CSV  →  GeoJSONL  →  Tippecanoe  →  PMTiles  →  MapLibre
  zipped/yr      stream        overnight      ~1-3GB      viewer
```

## Getting the data

Ofcom publishes this **annually, around early March**, split by year and
technology, as ZIP archives. There is no single 14GB file — that figure
is the whole archive back to 2020.

Source page: [mobile signal strength measurement data](https://www.ofcom.org.uk/phones-and-broadband/coverage-and-speeds/mobile-signal-strength-measurement-data)

Take the most recent 4G year to begin with. Note the archive expands to
several times its download size.

```bash
cd data/raw
nohup wget -c '<url from the page>' -O ofcom_4g_2025.zip > wget.log 2>&1 &
# then, once complete:
unzip -o ofcom_4g_2025.zip -d .
ls -lh
```

Do **not** take the "yellow trains" dataset from the same site. That is
signal measured along the railway network from Network Rail engineering
trains — interesting, but the wrong geometry for a van.

### Combining years

The converter emits line-delimited GeoJSON, so merging years needs no
extra code:

```bash
cat data/interim/*.geojsonl > data/interim/all.geojsonl
```

Be clear which question you are answering. "Has a vehicle ever driven
this road" wants every year. "What signal will I get today" wants the
latest only — masts change, and the 3G switch-off shifted things during
2025.

## Coverage lookup by postcode

Two sources, kept deliberately separate because they mean different things:

| | Source | Coverage | Nature |
|---|---|---|---|
| **Measured** | Your drive-test SQLite | ~13% of UK land, effectively less | Real readings |
| **Predicted** | Ofcom Mobile Coverage API | Whole UK, 50m grid | A model |

Never merge them into a single number. Absence of measured data means
*nobody drove there* — not that there is no signal.

```bash
# One-off: index the measurements for proximity queries
python3 scripts/build_sqlite.py \
    data/interim/4g-2025.geojsonl \
    data/out/signal.sqlite --tech 4g

# Then look anything up
python3 scripts/coverage_lookup.py "BS1 4DJ"
python3 scripts/coverage_lookup.py "Applecross" --radius 5
python3 scripts/coverage_lookup.py 57.4321 -5.8012
```

Spatial indexing is a plain integer grid, not SQLite's R*Tree. R*Tree is
a compile-time module and DSM's Python is built without it, so avoiding
it means this works on any SQLite anywhere — including whatever ships on
a phone. For radius queries a grid is just as fast: 12M rows index in
about two minutes into roughly 0.7GB, and lookups return in under a
tenth of a second.

For predicted coverage, register free at
[api.ofcom.org.uk](https://api.ofcom.org.uk) and request the Mobile
product (100 calls/min, 50,000/month), then:

```bash
export OFCOM_MOBILE_KEY=your_key_here
```

Ofcom's scale is numeric: 4 likely, 3 limited, 0 none (1 and 2 are
retired), reported per operator for voice and data, indoor and outdoor.
Carrier codes rather than brands: `EE`, `H3` = Three, `TF` = Telefonica
= O2, `VO` = Vodafone.

**The API is keyed on postcodes and UPRNs, not coordinates.** That is a
real limitation for this app: lay-bys, forest tracks and mountain passes
have neither. Given a coordinate, the lookup reverse-geocodes to the
nearest postcode via postcodes.io and reports how far away it is - which
in the Highlands may be kilometres, and is shown rather than hidden.

**Read the indoor column, not the outdoor one.** A van is a metal box, so
Ofcom's indoor prediction is the better guide to what you will get sitting
inside it. Outdoor is what you get standing next to it.

### Agreement is the product

When both sources have data for a location, the lookup compares them and
flags MODEL OPTIMISTIC or MODEL PESSIMISTIC. Every coverage checker in
existence shows you the prediction and stops. Being able to say "the model
claims likely coverage here and 1,200 real measurements nearby disagree"
requires both datasets, which is why nobody else has it.

## The Ofcom schema

Ofcom publishes **wide**: one row per location, with columns shaped
`{parameter}_top{1..4}_{operator}` across four operators (`ee`, `o2`,
`vf`, `3uk`). Roughly 160 columns, most empty on any given row.

Only `top1` matters here — the strongest cell each operator had at that
spot, which is what "will I have signal" means. Top 2-4 are weaker cells
the receiver could also see: useful for network planning, noise for this.

`ofcom_to_geojsonl.py` pivots that into one Point per location carrying
one RSRP value per operator, so the map switches operator without
rebuilding tiles.

### Notspots are kept deliberately

Locations where no operator had a reading get `n_ops: 0` and no `best`
value. They are not dropped, because a total notspot is the most useful
single fact this app can tell someone.

Carry the ambiguity into the UI though: an absent reading may mean
genuine no-service, or simply that Ofcom did not upload that measurement
— they publish a targeted subset rather than everything captured. Same
provenance-not-verdict principle as the legality layer.

## Updating

```bash
./scripts/update.sh
```

Refreshes scripts and docs, and **leaves `data/` alone**. Only genuinely
new data files are added.

Do not use `curl ... | tar xz --strip-components=1` once you have started
correcting data — it overwrites everything, including coordinates you have
verified by hand.

## Running it

Everything runs in one container so the host is disposable. Currently a
ProLiant ML110 Gen9 (2 cores, 8GB) under DSM; nothing here depends on
that.

```bash
cp .env.example .env        # set DATA_DIR to a real shared folder
docker compose build        # builds Tippecanoe from source, takes a while
docker compose run --rm etl
```

Then inside the container:

```bash
# 1. See what you have got. Reads the head only, returns instantly.
python3 scripts/inspect_csv.py data/raw/4g-lte-2025-mobile-signal-measurement-data.csv

# 2. Convert. Streams, so 7GB is fine on 8GB of RAM.
python3 scripts/ofcom_to_geojsonl.py \
    data/raw/4g-lte-2025-mobile-signal-measurement-data.csv \
    data/interim/4g-2025.geojsonl --sinr

# 3. Build tiles. Hours on two cores — run it overnight.
./scripts/build_tiles.sh data/interim/4g-2025.geojsonl data/out/signal-4g.pmtiles
```

Then copy `signal-4g.pmtiles` next to `viewer/index.html`, serve the
directory with `python3 -m http.server 8000`, and look at it.

Adjust `SIGNAL_FIELD` in the viewer to whatever step 1 showed you.

## Before you start

- **Take the 4G file, not the 5G.** 14GB against 50GB, and if 4G looks
  poor the 5G will not rescue it.
- **Check free space.** You need room for the raw CSV, the GeoJSONL
  (larger than the CSV), Tippecanoe's scratch space, and the output —
  all at once. Budget 3× the input size.
- **Watch for OS grid coordinates.** If `inspect_csv.py` reports eastings
  and northings rather than lat/lon, the data is EPSG:27700 and needs
  reprojecting before any of this works.

## What you are looking for

Not "does it render". It will render. The question is whether there are
measurements in the places vans actually go — single-track roads in
Snowdonia, the west coast of Scotland, the Yorkshire Dales — or whether
coverage collapses to motorways and towns.

If it is motorways only, the signal layer is not the wedge and the
scoping needs revisiting before anything else is built.

## Rules

**Data never goes in git.** Not the CSVs, not the tiles. Not via LFS
either. `.gitignore` enforces this.

**Tiles are served from R2, never from home.** Zero egress fees, edge
cached, about 30p a month. Serving gigabytes of tiles over domestic
broadband is slow for users and a good way to annoy your ISP.

**Nothing hand-configured.** If it is not in `compose.yaml`, a script, or
`.env.example`, it does not exist. The host has changed several times
during scoping and will change again.

## Not yet built

| Phase | Needs |
|---|---|
| 2 — D-TRO | PostGIS enters here |
| 3 — PSPO scrapers | Resolve instrument scope first |
| 4 — Solar | Open-Meteo + LIDAR DSM |
| 5 — POIs, community | First phase needing a running backend |
| 6 — Public API | VanOS is the reference consumer |

## Licence

TBD. Note that Ofcom, OS and OSM data each carry their own attribution
requirements — resolve before anything ships publicly.
