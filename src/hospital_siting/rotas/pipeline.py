"""Pipeline de rotas: PBF -> OSRM local -> matriz de tempo (silver `matriz_tempo`)."""

from __future__ import annotations

import json
import subprocess
import time

import geopandas as gpd
import httpx

from hospital_siting.core.config import REPO_ROOT, Config
from hospital_siting.core.meta import record_run
from hospital_siting.core.storage import read_parquet, silver_path, write_parquet
from hospital_siting.core.validation import validate, warn_if
from hospital_siting.rotas.fetch import baixar_pbf
from hospital_siting.rotas.matriz import para_long, poligono_buffer, tabela_osrm
from hospital_siting.schemas.silver import MATRIZ_TEMPO

COMPOSE = REPO_ROOT / "docker-compose.osrm.yml"
PREPARE = REPO_ROOT / "docker" / "osrm" / "prepare.sh"
OSRM_URL = "http://localhost:5000"
OSRM_ARQ = "mapa.osrm"


def _esperar_osrm(url: str, timeout_s: int = 600) -> None:
    """Health check: espera o OSRM responder a uma rota simples."""
    limite = time.monotonic() + timeout_s
    teste = "/route/v1/driving/-38.5108,-12.9714;-38.9669,-12.2664"
    while time.monotonic() < limite:
        try:
            if httpx.get(url + teste, timeout=5).status_code in (200, 400):
                return
        except httpx.HTTPError:
            pass
        time.sleep(3)
    raise TimeoutError(f"OSRM não respondeu em {timeout_s}s em {url}")


def _compose(*args: str) -> None:
    subprocess.run(["docker", "compose", "-f", str(COMPOSE), *args], check=True, cwd=REPO_ROOT)  # noqa: S603, S607


def _preparar_grafo(cfg: Config, geo: gpd.GeoDataFrame) -> None:
    osrm_dir = cfg.data_dir / "osrm"
    osrm_dir.mkdir(parents=True, exist_ok=True)
    if (osrm_dir / f"{OSRM_ARQ}.mldgr").exists():
        return
    pbf = baixar_pbf(cfg)
    limites = gpd.GeoDataFrame(geometry=gpd.GeoSeries(geo["geom_limite"], crs=4674))
    poli = poligono_buffer(limites, float(cfg.params["osm_buffer_km"]))
    geom = json.loads(gpd.GeoSeries([poli]).to_json())["features"][0]["geometry"]
    poly_path = osrm_dir / "area.geojson"
    poly_path.write_text(json.dumps({"type": "Feature", "properties": {}, "geometry": geom}), encoding="utf-8")
    subprocess.run(["bash", str(PREPARE), str(pbf), str(poly_path), str(osrm_dir)], check=True)  # noqa: S603, S607


def run(cfg: Config) -> None:
    geo = read_parquet(silver_path(cfg, "municipio_geo")).sort_values("cod_ibge").reset_index(drop=True)
    cods = geo["cod_ibge"].astype(str).tolist()
    coords = [(p.x, p.y) for p in gpd.GeoSeries(geo["geom_sede"], crs=4674)]

    _preparar_grafo(cfg, geo)
    _compose("up", "-d")
    try:
        _esperar_osrm(OSRM_URL)
        seg, met = tabela_osrm(coords, OSRM_URL)
    finally:
        _compose("down")

    df = para_long(cods, seg, met)
    sem_rota = int(df["minutos_osrm"].isna().sum())
    df = validate(cfg, MATRIZ_TEMPO, df, "matriz_tempo")
    write_parquet(df, silver_path(cfg, "matriz_tempo"))
    warn_if(cfg, sem_rota > 0, "matriz_tempo", "pares_sem_rota", f"{sem_rota} pares sem rota")
    record_run(cfg, "rotas", "ok", {"municipios": len(cods), "linhas": len(df), "sem_rota": sem_rota})
