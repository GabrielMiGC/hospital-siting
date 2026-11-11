"""Download do extrato OSM (Geofabrik, região Nordeste)."""

from __future__ import annotations

from pathlib import Path

from hospital_siting.core.config import Config
from hospital_siting.core.storage import fetch_to_raw

FONTE = "osm"
PBF_URL = "https://download.geofabrik.de/south-america/brazil/nordeste-latest.osm.pbf"
PBF_NOME = "nordeste-latest.osm.pbf"


def baixar_pbf(cfg: Config) -> Path:
    """Baixa o PBF do Nordeste para raw (idempotente) e devolve o caminho local."""
    return fetch_to_raw(cfg, FONTE, "nordeste", PBF_URL, PBF_NOME).path
