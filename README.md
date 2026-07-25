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
   14GB        stream        overnight      ~1-3GB      viewer
```

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
python3 scripts/inspect_csv.py data/raw/ofcom_4g.csv

# 2. Convert. Streams, so 14GB is fine on 8GB of RAM.
python3 scripts/csv_to_geojsonl.py \
    data/raw/ofcom_4g.csv \
    data/interim/4g.geojsonl \
    --keep Operator,RSRP,RSRQ \
    --numeric RSRP,RSRQ

# 3. Build tiles. Hours on two cores — run it overnight.
./scripts/build_tiles.sh data/interim/4g.geojsonl data/out/signal-4g.pmtiles
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
