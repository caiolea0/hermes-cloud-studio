#!/usr/bin/env bash
# UI-P0 B2: Extrai Cuiabá .pmtiles para servir via hermes-web nginx.
# Roda na VPS: bash scripts/fetch_pmtiles.sh
# Requer: curl, go-pmtiles CLI (baixado automaticamente se ausente)
# Output: /opt/hermes/tiles/cuiaba.pmtiles (volume hermes_tiles no docker-compose)

set -euo pipefail

BBOX="-56.20,-15.75,-55.80,-15.40"
TILES_DIR="${TILES_DIR:-/opt/hermes/tiles}"
OUT="${TILES_DIR}/cuiaba.pmtiles"
PMTILES_VERSION="1.22.3"
ARCH="Linux_x86_64"

mkdir -p "${TILES_DIR}"

# ── Instala pmtiles CLI se necessário ────────────────────────────────────────
if ! command -v pmtiles &>/dev/null; then
    echo "Baixando pmtiles CLI v${PMTILES_VERSION}..."
    TMPDIR=$(mktemp -d)
    curl -sSfL \
        "https://github.com/protomaps/go-pmtiles/releases/download/v${PMTILES_VERSION}/go-pmtiles_${PMTILES_VERSION}_${ARCH}.tar.gz" \
        -o "${TMPDIR}/pmtiles.tar.gz"
    tar -xzf "${TMPDIR}/pmtiles.tar.gz" -C "${TMPDIR}" pmtiles
    chmod +x "${TMPDIR}/pmtiles"
    mv "${TMPDIR}/pmtiles" /usr/local/bin/
    rm -rf "${TMPDIR}"
    echo "pmtiles CLI instalado: $(pmtiles version)"
fi

# ── Extrai Cuiabá do Protomaps via HTTP Range Requests ───────────────────────
# pmtiles extract faz HTTP 206 no arquivo remoto — não baixa o planeta inteiro.
# Source: Protomaps planet build (OpenStreetMap data).
# Atualizar PLANET_URL conforme última build em https://protomaps.com/downloads/basemaps
PLANET_URL="${PLANET_URL:-https://build.protomaps.com/downloads/20240101.pmtiles}"

if [[ -f "${OUT}" ]]; then
    echo "Arquivo já existe: ${OUT}"
    echo "Para re-extrair, delete o arquivo e rode novamente."
    pmtiles show "${OUT}"
    exit 0
fi

echo "Extraindo bbox=${BBOX} de ${PLANET_URL}..."
echo "(Usa HTTP Range Requests — baixa apenas tiles da região de Cuiabá)"

pmtiles extract "${PLANET_URL}" "${OUT}" \
    --bbox="${BBOX}" \
    --download-threads=4 \
    --maxzoom=14

echo ""
echo "✓ PMTiles gerado: ${OUT}"
pmtiles show "${OUT}"
echo ""
echo "Próximo passo: docker compose up -d hermes-web"
echo "Teste: curl -sI -H 'Range: bytes=0-1023' http://100.74.227.37:8801/tiles/cuiaba.pmtiles | head"
