#!/usr/bin/env bash
#
# Build PMTiles from line-delimited GeoJSON.
#
#   ./scripts/build_tiles.sh data/interim/ofcom_4g.geojsonl data/out/signal-4g.pmtiles
#
# Expect this to take hours on two cores. Run it overnight. Tippecanoe
# spills to disk rather than holding everything in RAM, so 8GB is fine,
# but it wants plenty of free space in TMPDIR.

set -euo pipefail

IN="${1:?usage: build_tiles.sh <input.geojsonl> <output.pmtiles>}"
OUT="${2:?usage: build_tiles.sh <input.geojsonl> <output.pmtiles>}"
LAYER="${LAYER:-signal}"
MIN_ZOOM="${MIN_ZOOM:-4}"
MAX_ZOOM="${MAX_ZOOM:-12}"

export TMPDIR="${TMPDIR:-$(dirname "$OUT")/tmp}"
mkdir -p "$TMPDIR" "$(dirname "$OUT")"

echo "in:      $IN"
echo "out:     $OUT"
echo "zooms:   $MIN_ZOOM-$MAX_ZOOM"
echo "tmpdir:  $TMPDIR ($(df -h "$TMPDIR" | awk 'NR==2 {print $4}') free)"
echo

# --drop-densest-as-needed keeps tiles under the size limit by thinning
#   points where they are thickest, rather than failing.
# --cluster-densest-as-needed merges nearby points into one with a count,
#   which is what you want for millions of overlapping measurements.
# -z12 is deliberate: drive-test readings are metres apart along roads,
#   so zooming past 12 shows noise rather than detail. Raise it later if
#   the data turns out to justify it.
time tippecanoe \
    --output="$OUT" \
    --force \
    --layer="$LAYER" \
    --minimum-zoom="$MIN_ZOOM" \
    --maximum-zoom="$MAX_ZOOM" \
    --drop-densest-as-needed \
    --cluster-densest-as-needed \
    --cluster-distance=4 \
    --extend-zooms-if-still-dropping \
    --read-parallel \
    "$IN"

echo
echo "done: $(du -h "$OUT" | cut -f1)"
