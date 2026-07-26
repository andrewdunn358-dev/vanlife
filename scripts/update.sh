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

# Code: always refresh.
for dir in scripts docs; do
    if [ -d "$TMP/$dir" ]; then
        mkdir -p "$ROOT/$dir"
        cp -r "$TMP/$dir/." "$ROOT/$dir/"
        echo "  updated $dir/"
    fi
done

for f in README.md compose.yaml .gitignore .env.example; do
    [ -f "$TMP/$f" ] && cp "$TMP/$f" "$ROOT/$f"
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
