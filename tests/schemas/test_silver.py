import geopandas as gpd
import pandas as pd
import pandera.errors
import pytest
from shapely.geometry import MultiPolygon, Point, Polygon

from hospital_siting.schemas import silver as S


def _leitos(qtd_total, qtd_sus, tipo="clinico"):
    return pd.DataFrame(
        {
            "cnes": ["1234567"],
            "cod_ibge": ["2927408"],
            "cod_leito": ["33"],
            "tipo_leito": [tipo],
            "qtd_total": [qtd_total],
            "qtd_sus": [qtd_sus],
            "competencia": ["2026-09"],
        }
    )


def test_cnes_leitos_sus_le_total():
    with pytest.raises(pandera.errors.SchemaErrors):
        S.CNES_LEITOS.validate(_leitos(5, 6), lazy=True)
    S.CNES_LEITOS.validate(_leitos(6, 5))


def test_cnes_leitos_tipo_invalido():
    S.CNES_LEITOS.validate(_leitos(1, 1, "fora_do_escopo"))
    with pytest.raises(pandera.errors.SchemaErrors):
        S.CNES_LEITOS.validate(_leitos(1, 1, "queimados"), lazy=True)


def test_matriz_tempo_unique_and_nullable():
    df = pd.DataFrame(
        {"origem": ["2927408"] * 2, "destino": ["2910800"] * 2, "minutos_osrm": [None, 1.0], "km": [None, 1.0]}
    )
    with pytest.raises(pandera.errors.SchemaErrors):
        S.MATRIZ_TEMPO.validate(df, lazy=True)
    S.MATRIZ_TEMPO.validate(df.iloc[:1])


def test_indice_unique():
    df = pd.DataFrame({"indice": ["IPCA", "IPCA"], "mes": ["2026-09", "2026-09"], "valor": [1.0, 2.0]})
    with pytest.raises(pandera.errors.SchemaErrors):
        S.INDICE.validate(df, lazy=True)


def test_municipio_geo_crs():
    poly = MultiPolygon([Polygon([(0, 0), (1, 0), (1, 1)])])
    g = gpd.GeoDataFrame(
        {
            "cod_ibge": ["2927408"],
            "geom_sede": gpd.GeoSeries([Point(0.5, 0.2)], crs=4674),
            "geom_limite": gpd.GeoSeries([poly], crs=4674),
        },
        geometry="geom_limite",
        crs=4674,
    )
    S.validate_municipio_geo(g)
    with pytest.raises(ValueError):
        S.validate_municipio_geo(g.to_crs(4326))


def test_tipos_leito():
    assert S.TIPOS_LEITO == ("clinico", "cirurgico", "obstetrico", "pediatrico", "uti_adulto", "uti_neo_ped")
