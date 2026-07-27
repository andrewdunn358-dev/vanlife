#!/usr/bin/env bash
#
# Update the code from GitHub without touching your data.
#
# The obvious `curl | tar xz --strip-components=1` overwrites everything,
# including data/sites/*.json - so any coordinates you have corrected get
# replaced by whatever is in the repo. This copies scripts and docs, and
# leaves data alone unless a file is genuinely new.
#
#     ./scripts/update.sh
#
# If you have changed a script locally, that gets overwritten. Data never
# does.

set -euo pipefail

REPO="https://github.com/andrewdunn358-dev/vanlife/archive/refs/heads/main.tar.gz"
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

echo "fetching..."
curl -sSL "$REPO" | tar xz -C "$TMP" --strip-components=1

# Code and source assets: always refresh. site-assets holds the vehicle
# images, which are source rather than build output - site/ is wiped on
# every rebuild, so they cannot live there.
for dir in scripts docs site-assets; do
    if [ -d "$TMP/$dir" ]; then
        mkdir -p "$ROOT/$dir"
        cp -r "$TMP/$dir/." "$ROOT/$dir/"
        echo "  updated $dir/"
    fi
done

# compose.yaml is overwritten like any other tracked file, so local edits
# to it are lost on every update. Keep a copy of the old one when it
# actually differs, rather than letting a hand-added service disappear
# silently - that is exactly how the site stopped being served once.
for f in README.md compose.yaml .gitignore .env.example; do
    [ -f "$TMP/$f" ] || continue
    if [ "$f" = "compose.yaml" ] && [ -f "$ROOT/$f" ] \
       && ! cmp -s "$TMP/$f" "$ROOT/$f"; then
        cp "$ROOT/$f" "$ROOT/$f.local-backup"
        echo "  your compose.yaml differed - kept it as compose.yaml.local-backup"
    fi
    cp "$TMP/$f" "$ROOT/$f"
done
echo "  updated top-level files"

# Data: only add what is missing. Never overwrite.
added=0 kept=0
if [ -d "$TMP/data" ]; then
    while IFS= read -r -d '' src; do
        rel="${src#$TMP/}"
        dst="$ROOT/$rel"
        if [ -f "$dst" ]; then
            kept=$((kept + 1))
        else
            mkdir -p "$(dirname "$dst")"
            cp "$src" "$dst"
            echo "  new: $rel"
            added=$((added + 1))
        fi
    done < <(find "$TMP/data" -type f -print0)
fi

echo
echo "data: $added new file(s), $kept left alone"
echo
echo "Your data was not touched. If you want the repo's version of a data"
echo "file, delete your local copy and run this again."

chmod +x "$ROOT"/scripts/*.sh 2>/dev/null || true
