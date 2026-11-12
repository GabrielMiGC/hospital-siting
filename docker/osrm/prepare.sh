#!/usr/bin/env bash
# Uso: prepare.sh <pbf> <poly.geojson> <out_dir>
# Recorta o PBF pelo polígono e prepara o grafo OSRM (MLD) em <out_dir>/mapa.osrm*.
set -euo pipefail

PBF=$(realpath "$1")
POLY=$(realpath "$2")
OUT=$(realpath "$3")
mkdir -p "$OUT"
export MSYS_NO_PATHCONV=1

docker run --rm -v "$(dirname "$PBF"):/in:ro" -v "$(dirname "$POLY"):/poly:ro" -v "$OUT:/out" \
  stefda/osmium-tool osmium extract -p "/poly/$(basename "$POLY")" "/in/$(basename "$PBF")" \
  -o /out/mapa.osm.pbf --overwrite

for passo in \
  "osrm-extract -p /opt/car.lua /data/mapa.osm.pbf" \
  "osrm-partition /data/mapa.osrm" \
  "osrm-customize /data/mapa.osrm"; do
  # shellcheck disable=SC2086
  docker run --rm -v "$OUT:/data" osrm/osrm-backend $passo
done
