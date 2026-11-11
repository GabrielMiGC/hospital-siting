"""Aquisição idempotente das fontes IBGE e geobr."""

from __future__ import annotations

import json

import duckdb
import geobr
import geopandas as gpd
import pandas as pd
from geobr import _duckdb_backend

from hospital_siting.core.config import Config
from hospital_siting.core.storage import fetch_to_raw

SIDRA_BASE = "https://apisidra.ibge.gov.br/values"
ANO_MALHA = 2025
ANO_SEDES = 2022
ANO_REGIOES = 2025


def _url_sidra(tabela: int, variavel: int, periodo: str, cod_uf: str) -> str:
    return (
        f"{SIDRA_BASE}/t/{tabela}/n6/in%20n3%20{cod_uf}/v/{variavel}/p/{periodo}"
        "?formato=json"
    )


def _ler_sidra(path) -> pd.DataFrame:
    registros = json.loads(path.read_text(encoding="utf-8"))
    if not registros:
        return pd.DataFrame()
    dados = pd.DataFrame(registros[1:], dtype=str)
    # A API real usa D2 para variável e D3 para ano; internamente adotamos o
    # contrato estável D2=ano e D3=variável usado pelas fixtures.
    if not dados.empty and not dados["D2C"].str.fullmatch(r"\d{4}").all():
        dados[["D2C", "D3C"]] = dados[["D3C", "D2C"]].to_numpy()
        dados[["D2N", "D3N"]] = dados[["D3N", "D2N"]].to_numpy()
    return dados


def sidra(cfg: Config) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Baixa Censo, estimativa e PIB e devolve os frames no contrato bruto."""
    fontes = (
        ("pop_censo", 9514, 93, "2022", "censo_2022.json"),
        ("pop_estimativa", 6579, 9324, "last%201", "estimativa_recente.json"),
        ("pib", 5938, 37, "last%201", "pib_recente.json"),
    )
    frames: dict[str, pd.DataFrame] = {}
    for nome, tabela, variavel, periodo, arquivo in fontes:
        raw = fetch_to_raw(
            cfg,
            "ibge_sidra",
            nome,
            _url_sidra(tabela, variavel, periodo, cfg.cod_uf),
            arquivo,
        )
        frames[nome] = _ler_sidra(raw.path)
    return pd.concat([frames["pop_censo"], frames["pop_estimativa"]], ignore_index=True), frames[
        "pib"
    ]


def _compat_duckdb_geobr(cfg: Config) -> None:
    """Mantém geobr 0.2 compatível com a API de relação do DuckDB 2."""
    if not hasattr(duckdb.DuckDBPyRelation, "fetchone"):
        duckdb.DuckDBPyRelation.fetchone = lambda rel: (rel.fetchall() or [None])[0]
    extensoes = (cfg.data_dir / "raw" / "ibge_geobr" / "duckdb_extensions").resolve()
    extensoes.mkdir(parents=True, exist_ok=True)
    conexao = _duckdb_backend.duckdb_connection()
    conexao.execute("SET extension_directory = ?", [str(extensoes)])
    conexao.execute("INSTALL spatial")
    conexao.execute("LOAD spatial")


def geometrias(
    cfg: Config,
) -> tuple[gpd.GeoDataFrame, gpd.GeoDataFrame, gpd.GeoDataFrame, gpd.GeoDataFrame]:
    """Lê limites, sedes, regiões e macrorregiões da versão corrente do geobr."""
    _compat_duckdb_geobr(cfg)
    limites = geobr.read_municipality(
        ANO_MALHA, code_muni=cfg.uf, show_progress=False
    )
    sedes = geobr.read_municipal_seat(
        ANO_SEDES, code_muni=cfg.uf, show_progress=False
    )
    regioes = geobr.read_health_region(
        ANO_REGIOES,
        code_state=cfg.uf,
        geometry_level="micro",
        show_progress=False,
    )
    macros = geobr.read_health_region(
        ANO_REGIOES,
        code_state=cfg.uf,
        geometry_level="macro",
        show_progress=False,
    )
    return limites, sedes, regioes, macros
