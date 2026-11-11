"""Transformações puras das fontes SIDRA e geobr."""

from __future__ import annotations

import geopandas as gpd
import pandas as pd
from shapely.geometry import MultiPolygon, Polygon

from hospital_siting.core.parsing import parse_ibge_number
from hospital_siting.schemas.silver import REGIAO_SAUDE, validate_municipio_geo

CRS_SIRGAS2000 = 4674


def _codigo_municipio(valor: object) -> str:
    """Normaliza os códigos numéricos do geobr sem perder zeros."""
    return str(int(float(valor))).zfill(7)


def _nome_e_uf(nome: pd.Series) -> tuple[pd.Series, pd.Series]:
    partes = nome.astype("string").str.rsplit(" - ", n=1, expand=True)
    return partes[0].astype(str), partes[1].astype(str)


def sidra_to_municipio(
    pop_raw: pd.DataFrame, pib_raw: pd.DataFrame, cod_uf: str
) -> pd.DataFrame:
    """Combina população e PIB municipais devolvidos pela API SIDRA."""
    pop = pop_raw.loc[pop_raw["D1C"].astype(str).str.startswith(str(cod_uf))].copy()
    pop["valor"] = pop["V"].map(parse_ibge_number)
    pop["ano"] = pd.to_numeric(pop["D2C"], errors="raise").astype(int)
    pop = pop.loc[pop["valor"].notna()].sort_values("ano", ascending=False)
    pop = pop.drop_duplicates("D1C", keep="first")

    nomes, ufs = _nome_e_uf(pop["D1N"])
    municipio = pd.DataFrame(
        {
            "cod_ibge": pop["D1C"].astype(str).str.zfill(7),
            "nome": nomes,
            "uf": ufs,
            "populacao": pd.array(pop["valor"], dtype="Int64"),
            "ano_populacao": pop["ano"].to_numpy(dtype=int),
        }
    ).reset_index(drop=True)

    pib = pib_raw.loc[pib_raw["D1C"].astype(str).str.startswith(str(cod_uf))].copy()
    pib["ano_pib"] = pd.to_numeric(pib["D2C"], errors="raise").astype(int)
    pib["pib"] = pib["V"].map(parse_ibge_number).astype(float) * 1000.0
    pib = pib.sort_values("ano_pib", ascending=False).drop_duplicates("D1C", keep="first")
    pib = pib.rename(columns={"D1C": "cod_ibge"})[["cod_ibge", "pib", "ano_pib"]]
    pib["cod_ibge"] = pib["cod_ibge"].astype(str).str.zfill(7)

    out = municipio.merge(pib, on="cod_ibge", how="left", validate="one_to_one")
    out["pib"] = out["pib"].astype(float)
    out["ano_pib"] = out["ano_pib"].astype(int)
    return out[
        ["cod_ibge", "nome", "uf", "populacao", "ano_populacao", "pib", "ano_pib"]
    ]


def _sirgas(gdf: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    if gdf.crs is None:
        raise ValueError("geometria sem CRS")
    return gdf.copy() if gdf.crs.to_epsg() == CRS_SIRGAS2000 else gdf.to_crs(CRS_SIRGAS2000)


def _multipolygon(geometria: object) -> object:
    return MultiPolygon([geometria]) if isinstance(geometria, Polygon) else geometria


def geo_to_municipio_geo(
    limites: gpd.GeoDataFrame, sedes: gpd.GeoDataFrame
) -> gpd.GeoDataFrame:
    """Une limites e sedes municipais no contrato GeoParquet da silver."""
    lim = _sirgas(limites)[["code_muni", "geometry"]].copy()
    sed = _sirgas(sedes)[["code_muni", "geometry"]].copy()
    lim["cod_ibge"] = lim["code_muni"].map(_codigo_municipio)
    sed["cod_ibge"] = sed["code_muni"].map(_codigo_municipio)
    lim["geom_limite"] = lim.geometry.map(_multipolygon)
    sed = sed.rename_geometry("geom_sede")

    dados = lim[["cod_ibge", "geom_limite"]].merge(
        sed[["cod_ibge", "geom_sede"]].drop_duplicates("cod_ibge"),
        on="cod_ibge",
        how="left",
        validate="one_to_one",
    )
    out = gpd.GeoDataFrame(dados, geometry="geom_limite", crs=CRS_SIRGAS2000)
    out["geom_sede"] = gpd.GeoSeries(out["geom_sede"], index=out.index, crs=CRS_SIRGAS2000)
    return validate_municipio_geo(out[["cod_ibge", "geom_sede", "geom_limite"]])


def _associar_poligono(
    sedes: gpd.GeoDataFrame,
    poligonos: gpd.GeoDataFrame,
    colunas: list[str],
) -> pd.DataFrame:
    candidatos = gpd.sjoin(
        sedes[["cod_ibge", "geometry"]],
        poligonos[[*colunas, "geometry"]],
        how="left",
        predicate="within",
    ).drop(columns="index_right")
    candidatos = candidatos.drop_duplicates("cod_ibge", keep="first")

    ausentes = candidatos[colunas[0]].isna()
    if ausentes.any():
        pontos_m = candidatos.loc[ausentes, ["cod_ibge", "geometry"]].to_crs(3857)
        poligonos_m = poligonos[[*colunas, "geometry"]].to_crs(3857)
        proximos = gpd.sjoin_nearest(pontos_m, poligonos_m, how="left").drop(
            columns="index_right"
        )
        proximos = proximos.drop_duplicates("cod_ibge", keep="first").set_index("cod_ibge")
        base = candidatos.set_index("cod_ibge")
        base.loc[proximos.index, colunas] = proximos[colunas]
        candidatos = base.reset_index()
    return pd.DataFrame(candidatos.drop(columns="geometry"))


def regioes(
    sedes: gpd.GeoDataFrame,
    regioes: gpd.GeoDataFrame,
    macros: gpd.GeoDataFrame | None,
) -> pd.DataFrame:
    """Associa cada município à região e macrorregião de saúde pela sede."""
    pontos = _sirgas(sedes)[["code_muni", "geometry"]].copy()
    pontos["cod_ibge"] = pontos["code_muni"].map(_codigo_municipio)
    pontos = pontos.drop_duplicates("cod_ibge")

    reg = _sirgas(regioes)
    out = _associar_poligono(
        pontos,
        reg,
        ["code_health_region", "name_health_region"],
    ).rename(
        columns={
            "code_health_region": "cod_regiao_saude",
            "name_health_region": "nome_regiao_saude",
        }
    )

    out["cod_macrorregiao"] = None
    if macros is not None and not macros.empty:
        macro = _sirgas(macros)
        coluna_codigo = next(
            (
                nome
                for nome in ("code_health_macroregion", "code_health_marcroregion")
                if nome in macro.columns
            ),
            None,
        )
        if coluna_codigo is None:
            raise ValueError("macrorregiões sem coluna de código")
        associados = _associar_poligono(pontos, macro, [coluna_codigo])
        mapa = associados.set_index("cod_ibge")[coluna_codigo]
        out["cod_macrorregiao"] = out["cod_ibge"].map(mapa)

    resultado = out[
        ["cod_ibge", "cod_regiao_saude", "nome_regiao_saude", "cod_macrorregiao"]
    ].copy()
    for coluna in ("cod_ibge", "cod_regiao_saude", "nome_regiao_saude"):
        resultado[coluna] = resultado[coluna].astype(str)
    resultado["cod_macrorregiao"] = resultado["cod_macrorregiao"].astype("string")
    return REGIAO_SAUDE.validate(resultado, lazy=True)

