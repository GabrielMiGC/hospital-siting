"""Contratos da camada silver (data/silver/<nome>.parquet). Fonte única de verdade entre os domínios e a gold."""

from __future__ import annotations

import geopandas as gpd
from pandera.pandas import Check, Column, DataFrameSchema

TIPOS_LEITO = ("clinico", "cirurgico", "obstetrico", "pediatrico", "uti_adulto", "uti_neo_ped")
FORA_DO_ESCOPO = "fora_do_escopo"

COD7 = Check.str_matches(r"^\d{7}$")
MES = Check.str_matches(r"^\d{4}-\d{2}$")
NAO_NEG = Check.ge(0)
POS = Check.gt(0)


def _cod(**kw) -> Column:
    return Column(str, COD7, **kw)


MUNICIPIO = DataFrameSchema(
    {
        "cod_ibge": _cod(unique=True),
        "nome": Column(str),
        "uf": Column(str, Check.str_length(2, 2)),
        "populacao": Column("Int64", POS),
        "ano_populacao": Column(int),
        "pib": Column(float, POS, nullable=True),
        "ano_pib": Column(int),
    },
    name="municipio",
)

REGIAO_SAUDE = DataFrameSchema(
    {
        "cod_ibge": _cod(unique=True),
        "cod_regiao_saude": Column(str),
        "nome_regiao_saude": Column(str),
        "cod_macrorregiao": Column(str, nullable=True),
    },
    name="regiao_saude",
)

CNES_ESTABELECIMENTO = DataFrameSchema(
    {
        "cnes": Column(str, Check.str_matches(r"^\d{7}$"), unique=True),
        "cod_ibge": _cod(),
        "tipo_unidade": Column(str),
        "natureza": Column(str, Check.isin(["publica", "privada", "filantropica", "outra"])),
        "leitos_total": Column(int, NAO_NEG),
        "lat": Column(float, nullable=True),
        "lon": Column(float, nullable=True),
        "competencia": Column(str, MES),
    },
    name="cnes_estabelecimento",
)

CNES_LEITOS = DataFrameSchema(
    {
        "cnes": Column(str, Check.str_matches(r"^\d{7}$")),
        "cod_ibge": _cod(),
        "cod_leito": Column(str),
        "tipo_leito": Column(str, Check.isin([*TIPOS_LEITO, FORA_DO_ESCOPO])),
        "qtd_total": Column(int, NAO_NEG),
        "qtd_sus": Column(int, NAO_NEG),
        "competencia": Column(str, MES),
    },
    checks=[Check(lambda df: df["qtd_sus"] <= df["qtd_total"], name="qtd_sus_le_total")],
    name="cnes_leitos",
)

SIH_AGG = DataFrameSchema(
    {
        "cod_ibge_residencia": _cod(),
        "cod_ibge_ocorrencia": _cod(),
        "competencia": Column(str, MES),
        "tipo_leito": Column(str, Check.isin([*TIPOS_LEITO, FORA_DO_ESCOPO])),
        "internacoes": Column(int, POS),
        "valor_total": Column(float, NAO_NEG),
        "dias_permanencia": Column(int, NAO_NEG),
        "diarias_uti": Column(int, NAO_NEG),
        "valor_uti": Column(float, NAO_NEG),
        "faixa_uti": Column(str, Check.isin(["adulto", "neo_ped", "nenhuma"])),
    },
    name="sih_agg",
)

RECEITA_MUNICIPAL = DataFrameSchema(
    {"cod_ibge": _cod(unique=True), "exercicio": Column(int), "receita_corrente": Column(float, POS)},
    name="receita_municipal",
)

INDICE = DataFrameSchema(
    {"indice": Column(str, Check.isin(["IPCA", "INCC"])), "mes": Column(str, MES), "valor": Column(float, POS)},
    unique=["indice", "mes"],
    name="indice",
)

SIGTAP_PROCEDIMENTO = DataFrameSchema(
    {
        "co_procedimento": Column(str, Check.str_matches(r"^\d{10}$")),
        "no_procedimento": Column(str),
        "valor_sh": Column(float, NAO_NEG),
        "valor_sp": Column(float, NAO_NEG),
        "competencia": Column(str, MES),
    },
    unique=["co_procedimento", "competencia"],
    name="sigtap_procedimento",
)

CUSTO_OBRA_M2 = DataFrameSchema(
    {
        "fonte": Column(str, Check.isin(["SINAPI", "CUB"])),
        "padrao": Column(str),
        "valor_m2": Column(float, POS),
        "mes": Column(str, MES),
    },
    name="custo_obra_m2",
)

EQUIPAMENTO_AMBIENTE = DataFrameSchema(
    {
        "ambiente": Column(str),
        "equipamento": Column(str),
        "unidade": Column(str, Check.isin(["por_leito", "por_sala", "por_hospital"])),
        "quantidade_ref": Column(float, POS),
        "preco_ref": Column(float, POS, nullable=True),
        "fonte": Column(str),
        "mes": Column(str, MES),
    },
    name="equipamento_ambiente",
)

SALARIO_OCUPACAO = DataFrameSchema(
    {
        "cbo": Column(str, Check.str_matches(r"^\d{6}$"), unique=True),
        "descricao": Column(str, Check.str_matches(r".*[^\d\s].*")),  # título, não o código repetido
        "salario_medio": Column(float, POS),
        "ano": Column(int),
    },
    name="salario_ocupacao",
)

MATRIZ_TEMPO = DataFrameSchema(
    {
        "origem": _cod(),
        "destino": _cod(),
        "minutos_osrm": Column(float, NAO_NEG, nullable=True),
        "km": Column(float, NAO_NEG, nullable=True),
    },
    unique=["origem", "destino"],
    name="matriz_tempo",
)

SCHEMAS = {
    s.name: s
    for s in (
        MUNICIPIO,
        REGIAO_SAUDE,
        CNES_ESTABELECIMENTO,
        CNES_LEITOS,
        SIH_AGG,
        RECEITA_MUNICIPAL,
        INDICE,
        SIGTAP_PROCEDIMENTO,
        CUSTO_OBRA_M2,
        EQUIPAMENTO_AMBIENTE,
        SALARIO_OCUPACAO,
        MATRIZ_TEMPO,
    )
}


def validate_municipio_geo(gdf: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    """Contrato de `municipio_geo` (GeoParquet). Pandera não cobre bem múltiplas colunas geométricas."""
    faltando = {"cod_ibge", "geom_sede", "geom_limite"} - set(gdf.columns)
    if faltando:
        raise ValueError(f"municipio_geo sem colunas {sorted(faltando)}")
    if not gdf["cod_ibge"].is_unique or not gdf["cod_ibge"].astype(str).str.fullmatch(r"\d{7}").all():
        raise ValueError("municipio_geo: cod_ibge deve ser único e ter 7 dígitos")
    for col, tipos in (("geom_sede", {"Point"}), ("geom_limite", {"MultiPolygon", "Polygon"})):
        s = gpd.GeoSeries(gdf[col])
        if s.crs is None or s.crs.to_epsg() != 4674:
            raise ValueError(f"municipio_geo.{col} deve estar em EPSG:4674")
        if not set(s.geom_type.dropna()) <= tipos:
            raise ValueError(f"municipio_geo.{col} com tipo inválido: {set(s.geom_type)}")
    return gdf
