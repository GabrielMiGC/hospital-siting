"""Silvers e seeds mínimos (3 municípios) para testar o build da gold sem rede."""

from dataclasses import replace
from pathlib import Path

import geopandas as gpd
import pandas as pd
import pytest
from shapely.geometry import MultiPolygon, Point, Polygon

from hospital_siting.core.config import load_config
from hospital_siting.core.storage import silver_path, write_parquet

SEEDS = Path(__file__).parents[1] / "fixtures" / "seeds_gold"
SSA, FSA, SFX = "2927408", "2910800", "2930709"


def _quadrado(x, y):
    return MultiPolygon([Polygon([(x, y), (x + 0.1, y), (x + 0.1, y + 0.1), (x, y + 0.1)])])


def _escrever(cfg, nome, df):
    write_parquet(df, silver_path(cfg, nome))


@pytest.fixture
def cfg_fixture(tmp_path, monkeypatch):
    monkeypatch.delenv("HS_DATA_DIR", raising=False)
    base = load_config()
    cfg = replace(base, data_dir=tmp_path, seeds_dir=SEEDS, n_municipios=3)
    cods = [SSA, FSA, SFX]
    _escrever(
        cfg,
        "municipio",
        pd.DataFrame(
            {
                "cod_ibge": cods,
                "nome": ["Salvador", "Feira de Santana", "São Félix"],
                "uf": ["BA"] * 3,
                "populacao": pd.array([1000, 1000, 2000], dtype="Int64"),
                "ano_populacao": [2025] * 3,
                "pib": [1_000_000.0, 500_000.0, None],
                "ano_pib": [2024] * 3,
            }
        ),
    )
    geo = gpd.GeoDataFrame(
        {
            "cod_ibge": cods,
            "geom_sede": gpd.GeoSeries([Point(-38.5, -12.9), Point(-38.9, -12.2), Point(-38.9, -12.6)], crs=4674),
            "geom_limite": gpd.GeoSeries(
                [_quadrado(-38.55, -12.95), _quadrado(-38.95, -12.25), _quadrado(-38.95, -12.65)], crs=4674
            ),
        },
        geometry="geom_limite",
        crs=4674,
    )
    _escrever(cfg, "municipio_geo", geo)
    _escrever(
        cfg,
        "regiao_saude",
        pd.DataFrame(
            {
                "cod_ibge": cods,
                "cod_regiao_saude": ["29001", "29002", "29001"],
                "nome_regiao_saude": ["Salvador", "Feira", "Salvador"],
                "cod_macrorregiao": ["2901", "2902", "2901"],
            }
        ),
    )
    _escrever(
        cfg,
        "receita_municipal",
        pd.DataFrame(
            {
                "cod_ibge": [SSA, FSA],
                "exercicio": [2024, 2024],
                "receita_corrente": [100.0, 50.0],
            }
        ),
    )
    _escrever(
        cfg,
        "indice",
        pd.DataFrame(
            {
                "indice": ["IPCA", "IPCA", "IPCA", "INCC", "INCC"],
                "mes": ["2024-12", "2025-12", "2026-09", "2024-12", "2026-09"],
                "valor": [100.0, 105.0, 108.15, 100.0, 110.0],
            }
        ),
    )
    _escrever(
        cfg,
        "cnes_estabelecimento",
        pd.DataFrame(
            {
                "cnes": ["1234567"],
                "cod_ibge": [SSA],
                "tipo_unidade": ["05"],
                "natureza": ["publica"],
                "leitos_total": [30],
                "lat": [None],
                "lon": [None],
                "competencia": ["2026-09"],
            }
        ),
    )
    _escrever(
        cfg,
        "cnes_leitos",
        pd.DataFrame(
            {
                "cnes": ["1234567"] * 3,
                "cod_ibge": [SSA] * 3,
                "cod_leito": ["75", "33", "47"],
                "tipo_leito": ["uti_adulto", "clinico", "fora_do_escopo"],
                "qtd_total": [10, 20, 5],
                "qtd_sus": [10, 15, 5],
                "competencia": ["2026-09"] * 3,
            }
        ),
    )
    _escrever(
        cfg,
        "sih_agg",
        pd.DataFrame(
            {
                "cod_ibge_residencia": [SFX, SSA],
                "cod_ibge_ocorrencia": [SSA, SSA],
                "competencia": ["2024-12"] * 2,
                "tipo_leito": ["clinico", "clinico"],
                "internacoes": [1, 1],
                "valor_total": [1000.0, 3000.0],
                "dias_permanencia": [5, 6],
                "diarias_uti": [0, 4],
                "valor_uti": [0.0, 2000.0],
                "faixa_uti": ["nenhuma", "adulto"],
            }
        ),
    )
    tempos = {(SSA, FSA): 60.0, (SSA, SFX): 200.0, (FSA, SFX): 100.0}
    linhas = []
    for o in cods:
        for d in cods:
            m = 0.0 if o == d else tempos.get((o, d), tempos.get((d, o)))
            linhas.append({"origem": o, "destino": d, "minutos_osrm": m, "km": m})
    _escrever(cfg, "matriz_tempo", pd.DataFrame(linhas))
    _escrever(
        cfg,
        "sigtap_procedimento",
        pd.DataFrame(
            {
                "co_procedimento": ["0303010010"],
                "no_procedimento": ["TRATAMENTO X"],
                "valor_sh": [100.0],
                "valor_sp": [20.0],
                "competencia": ["2026-09"],
            }
        ),
    )
    _escrever(
        cfg,
        "custo_obra_m2",
        pd.DataFrame(
            {
                "fonte": ["SINAPI"],
                "padrao": ["R8-N"],
                "valor_m2": [2000.0],
                "mes": ["2026-09"],
            }
        ),
    )
    _escrever(
        cfg,
        "equipamento_ambiente",
        pd.DataFrame(
            {
                "ambiente": ["UTI adulto"],
                "equipamento": ["Monitor multiparamétrico"],
                "unidade": ["por_leito"],
                "quantidade_ref": [1.0],
                "preco_ref": [10000.0],
                "fonte": ["RENEM/FNS"],
                "mes": ["2025-12"],
            }
        ),
    )
    _escrever(
        cfg,
        "salario_ocupacao",
        pd.DataFrame(
            {
                "cbo": ["223505"],
                "descricao": ["Enfermeiro"],
                "salario_medio": [4500.0],
                "ano": [2024],
            }
        ),
    )
    return cfg
