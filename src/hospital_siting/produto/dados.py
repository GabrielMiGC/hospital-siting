"""Leitura da camada gold para o produto (Fase 2). Nada aqui escreve no banco."""

from __future__ import annotations

import json
from dataclasses import dataclass

import pandas as pd


@dataclass(frozen=True)
class Gold:
    """Recorte da gold que o modelo de custos e o otimizador consomem (valores na data-base)."""

    municipios: pd.DataFrame  # cod_ibge, nome, populacao, receita_corrente (0 se ausente), receita_disponivel, lat, lon
    deficit: pd.DataFrame  # cod_ibge, tipo_leito, deficit (negativo = superávit)
    tempos: pd.DataFrame  # origem, destino, minutos (NaN = sem rota)
    estabelecimentos: pd.DataFrame  # cnes, cod_ibge, leitos_sus
    arquetipos: pd.DataFrame  # porte, tipo_leito, leitos, area_m2_ref
    custo_obra_m2: float  # SINAPI (residencial) na data-base
    equipamentos: pd.DataFrame  # ambiente, equipamento, unidade, quantidade_ref, preco_ref
    equipe: pd.DataFrame  # setor, cbo, unidade, razao, turnos_dia, cobertura_dias
    salarios: pd.DataFrame  # cbo, descricao, salario_medio, encargos_pct
    custeio: dict[str, float]  # porte -> custeio não pessoal / pessoal
    valor_internacao: pd.DataFrame  # tipo_leito, unidade, valor_medio, permanencia_media_dias
    consorcio: dict[str, float]  # parametro -> valor
    data_base: str

    @property
    def portes(self) -> list[str]:
        return sorted(self.arquetipos["porte"].unique())


def _engine(dsn: str):
    from sqlalchemy import create_engine

    return create_engine(dsn)


def carregar_gold(dsn: str) -> Gold:
    """Carrega do PostGIS tudo o que o produto usa. Pares sem rota ficam com minutos NaN."""
    eng = _engine(dsn)
    q = lambda sql: pd.read_sql(sql, eng)  # noqa: E731
    mun = q(
        """SELECT cod_ibge, nome, populacao, COALESCE(receita_corrente, 0)::float AS receita_corrente,
                  receita_disponivel, ST_Y(geom_sede) AS lat, ST_X(geom_sede) AS lon,
                  cod_regiao_saude, nome_regiao_saude
           FROM gold.dim_municipio ORDER BY cod_ibge"""
    )
    obra = q("SELECT valor_m2::float AS v FROM gold.custo_obra_m2 WHERE fonte = 'SINAPI'")
    if obra.empty:
        raise ValueError("gold.custo_obra_m2 sem linha do SINAPI")
    exec_ = q(
        "SELECT extra->>'data_base' AS d FROM meta.execucoes "
        "WHERE dominio = 'gold' AND status = 'ok' ORDER BY em DESC LIMIT 1"
    )
    return Gold(
        municipios=mun,
        deficit=q("SELECT cod_ibge, tipo_leito, deficit::float AS deficit FROM gold.deficit_leitos"),
        tempos=q("SELECT origem, destino, minutos_osrm::float AS minutos FROM gold.matriz_tempo_viagem"),
        estabelecimentos=q("SELECT cnes, cod_ibge, leitos_sus FROM gold.estabelecimentos_hospitalares"),
        arquetipos=q("SELECT porte, tipo_leito, leitos, area_m2_ref::float AS area_m2_ref FROM gold.arquetipo_leitos"),
        custo_obra_m2=float(obra["v"].iloc[0]),
        equipamentos=q(
            "SELECT ambiente, equipamento, unidade, quantidade_ref::float AS quantidade_ref, "
            "preco_ref::float AS preco_ref FROM gold.equipamento_ambiente"
        ),
        equipe=q(
            "SELECT setor, cbo, unidade, razao::float AS razao, turnos_dia, cobertura_dias "
            "FROM gold.dimensionamento_equipe_param"
        ),
        salarios=q(
            "SELECT cbo, descricao, salario_medio::float AS salario_medio, encargos_pct::float AS encargos_pct "
            "FROM gold.salario_ocupacao"
        ),
        custeio=dict(
            q("SELECT porte, custeio_nao_pessoal_pct_pessoal::float AS v FROM gold.custeio_param").itertuples(
                index=False
            )
        ),
        valor_internacao=q(
            "SELECT tipo_leito, unidade, valor_medio::float AS valor_medio, "
            "permanencia_media_dias::float AS permanencia_media_dias FROM gold.valor_medio_internacao"
        ),
        consorcio=dict(q("SELECT parametro, valor::float AS v FROM gold.consorcio_param").itertuples(index=False)),
        data_base=exec_["d"].iloc[0] if not exec_.empty else "desconhecida",
    )


def geojson_municipios(dsn: str, tolerancia: float = 0.01) -> dict:
    """Limites municipais simplificados (para o mapa), com cod_ibge e nome nas propriedades."""
    eng = _engine(dsn)
    df = pd.read_sql(
        f"""SELECT cod_ibge, nome,
                   ST_AsGeoJSON(ST_SimplifyPreserveTopology(geom_limite, {float(tolerancia)}), 4) AS g
            FROM gold.dim_municipio ORDER BY cod_ibge""",
        eng,
    )
    return {
        "type": "FeatureCollection",
        "features": [
            {"type": "Feature", "properties": {"cod_ibge": r.cod_ibge, "nome": r.nome}, "geometry": json.loads(r.g)}
            for r in df.itertuples(index=False)
        ],
    }
