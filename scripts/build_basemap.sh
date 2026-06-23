#!/usr/bin/env bash
# Build Cuiabá .pmtiles basemap from Geofabrik data.
# Idempotent — skips if output already exists (pass --force to rebuild).
#
# RUNS ON VPS (resources: ~300MB download, 4 CPU, 4GB RAM).
# Output: /var/lib/docker/volumes/hermes_hermes_tiles/_data/cuiaba.pmtiles
# Served by hermes-web nginx at /tiles/cuiaba.pmtiles (HTTP 206 range requests).
#
# Usage:
#   bash scripts/build_basemap.sh          # skip if exists
#   bash scripts/build_basemap.sh --force  # rebuild
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(dirname "$SCRIPT_DIR")"

TILES_VOL="/var/lib/docker/volumes/hermes_hermes_tiles/_data"
OUTPUT="$TILES_VOL/cuiaba.pmtiles"
BUILD_DIR="/tmp/hermes_basemap"

CUIABA_BBOX="-56.15,-15.75,-55.85,-15.45"
PBF_URL="https://download.geofabrik.de/south-america/brazil/centro-oeste-latest.osm.pbf"

# ── Idempotency guard ─────────────────────────────────────────────────────────
if [ -f "$OUTPUT" ] && [ "${1:-}" != "--force" ]; then
  SIZE=$(du -h "$OUTPUT" | cut -f1)
  echo "✅ cuiaba.pmtiles already exists ($SIZE). Use --force to rebuild."
  exit 0
fi

mkdir -p "$BUILD_DIR" "$TILES_VOL"
echo "=== Hermes basemap build ==="
echo "  Output: $OUTPUT"
echo "  Bbox:   $CUIABA_BBOX"

# ── Step 1: osmium-tool ───────────────────────────────────────────────────────
if ! command -v osmium &>/dev/null; then
  echo "[1/5] Installing osmium-tool..."
  apt-get update -qq && apt-get install -y -qq osmium-tool
fi
echo "[1/5] osmium $(osmium --version 2>&1 | head -1) ✓"

# ── Step 2: tilemaker binary ──────────────────────────────────────────────────
TILEMAKER="$BUILD_DIR/tilemaker"
if [ ! -f "$TILEMAKER" ]; then
  echo "[2/5] Downloading tilemaker v3.0.0..."
  curl -fsSL -L \
    "https://github.com/systemed/tilemaker/releases/download/v3.0.0/tilemaker-ubuntu-22.04.zip" \
    -o "$BUILD_DIR/tilemaker.zip"
  unzip -o "$BUILD_DIR/tilemaker.zip" -d "$BUILD_DIR/"
  chmod +x "$TILEMAKER"
fi
echo "[2/5] tilemaker $("$TILEMAKER" --version 2>&1 | head -1 || echo 'v3.0.0') ✓"

# ── Step 3: Geofabrik Centro-Oeste PBF ───────────────────────────────────────
PBF="$BUILD_DIR/centro-oeste.pbf"
if [ ! -f "$PBF" ]; then
  echo "[3/5] Downloading Geofabrik Centro-Oeste (~300MB)..."
  curl -fsSL -L "$PBF_URL" -o "$PBF"
fi
PBF_SIZE=$(du -h "$PBF" | cut -f1)
echo "[3/5] PBF downloaded ($PBF_SIZE) ✓"

# ── Step 4: osmium extract Cuiabá bbox ───────────────────────────────────────
CUIABA_PBF="$BUILD_DIR/cuiaba.pbf"
echo "[4/5] Extracting Cuiabá bbox ($CUIABA_BBOX)..."
osmium extract \
  --bbox="$CUIABA_BBOX" \
  "$PBF" -o "$CUIABA_PBF" \
  --overwrite \
  --strategy=simple
CUIABA_SIZE=$(du -h "$CUIABA_PBF" | cut -f1)
echo "[4/5] Cuiabá extract: $CUIABA_SIZE ✓"

# ── Step 5: tilemaker → .pmtiles ─────────────────────────────────────────────
echo "[5/5] Building .pmtiles (zoom 8-14)..."
"$TILEMAKER" \
  --input  "$CUIABA_PBF" \
  --output "$OUTPUT" \
  --config "$REPO_ROOT/scripts/tilemaker/hermes-config.json" \
  --process "$REPO_ROOT/scripts/tilemaker/hermes-process.lua"

OUTPUT_SIZE=$(du -h "$OUTPUT" | cut -f1)
echo ""
echo "✅ Done: $OUTPUT ($OUTPUT_SIZE)"
echo "   Served at: http://100.74.227.37:8801/tiles/cuiaba.pmtiles"
