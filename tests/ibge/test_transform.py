from pathlib import Path

import geopandas as gpd
import pandas as pd
from shapely.geometry import MultiPolygon, Point, Polygon

from hospital_siting.ibge.transform import geo_to_municipio_geo, regioes, sidra_to_municipio
from hospital_siting.schemas.silver import MUNICIPIO, REGIAO_SAUDE

FIXTURES = Path(__file__).parents[1] / "fixtures" / "ibge"
CRS_SIRGAS2000 = 4674


def _ler_sidra(nome: str) -> pd.DataFrame:
    return pd.read_csv(FIXTURES / nome, dtype=str, keep_default_na=False)


POP_FIX = _ler_sidra("sidra_pop.csv")
PIB_FIX = _ler_sidra("sidra_pib.csv")


def _quadrado(x0: float, y0: float, lado: float = 10.0) -> Polygon:
    return Polygon([(x0, y0), (x0 + lado, y0), (x0 + lado, y0 + lado), (x0, y0 + lado)])


def test_sidra_to_municipio_shapes_and_types():
    out = sidra_to_municipio(POP_FIX, PIB_FIX, "29")
    assert set(out.cod_ibge) == {"2927408", "2910800", "2930709"}
    assert out.populacao.dtype == "Int64" and (out.populacao > 0).all()
    MUNICIPIO.validate(out)


def test_sidra_missing_marker_becomes_null():
    # na fixture, o PIB de São Félix vem como "..."
    out = sidra_to_municipio(POP_FIX, PIB_FIX, "29")
    assert pd.isna(out.set_index("cod_ibge").loc["2930709", "pib"])


def test_sidra_filters_other_uf():
    # a fixture contém 1 linha de 2611606 (Recife)
    assert not sidra_to_municipio(POP_FIX, PIB_FIX, "29").cod_ibge.str.startswith("26").any()


def test_geo_crs_4674_and_one_row_per_municipio():
    codigos = [2927408.0, 2910800.0, 2930709.0]
    limites = gpd.GeoDataFrame(
        {
            "code_muni": codigos,
            "name_muni": ["Salvador", "Feira de Santana", "São Félix"],
            "abbrev_state": ["BA", "BA", "BA"],
            "geometry": [MultiPolygon([_quadrado(0, 0)]), _quadrado(20, 0), _quadrado(40, 0)],
        },
        geometry="geometry",
        crs=CRS_SIRGAS2000,
    )
    sedes = gpd.GeoDataFrame(
        {
            "code_muni": codigos,
            "name_muni": ["Salvador", "Feira de Santana", "São Félix"],
            "geometry": [Point(5, 5), Point(25, 5), Point(45, 5)],
        },
        geometry="geometry",
        crs=CRS_SIRGAS2000,
    )
    out = geo_to_municipio_geo(limites, sedes)
    assert out.crs.to_epsg() == 4674 and out.cod_ibge.is_unique


def test_regioes_por_sede_e_validacao():
    sedes = gpd.GeoDataFrame(
        {
            "code_muni": [2927408.0, 2910800.0, 2930709.0],
            "name_muni": ["Salvador", "Feira de Santana", "São Félix"],
            "geometry": [Point(5, 5), Point(7, 2), Point(25, 5)],
        },
        geometry="geometry",
        crs=CRS_SIRGAS2000,
    )
    regioes_saude = gpd.GeoDataFrame(
        {
            "code_health_region": ["2901", "2902"],
            "name_health_region": ["Região Leste", "Região Oeste"],
            "geometry": [_quadrado(0, 0), _quadrado(20, 0)],
        },
        geometry="geometry",
        crs=CRS_SIRGAS2000,
    )
    macros = gpd.GeoDataFrame(
        {"code_health_macroregion": ["2900"], "name_health_macroregion": ["Macro"], "geometry": [_quadrado(0, 0, 30)]},
        geometry="geometry",
        crs=CRS_SIRGAS2000,
    )
    out = regioes(sedes, regioes_saude, macros)
    por_municipio = out.set_index("cod_ibge")
    assert por_municipio.loc["2927408", "cod_regiao_saude"] == "2901"
    assert por_municipio.loc["2910800", "cod_regiao_saude"] == "2901"
    assert por_municipio.loc["2930709", "cod_regiao_saude"] == "2902"
    assert por_municipio.loc["2930709", "nome_regiao_saude"] == "Região Oeste"
    assert (out["cod_macrorregiao"] == "2900").all()
    REGIAO_SAUDE.validate(out, lazy=True)
