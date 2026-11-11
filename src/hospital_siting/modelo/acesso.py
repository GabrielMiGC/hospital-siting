"""Cálculos puros de acessibilidade a leitos e déficit assistencial."""

from __future__ import annotations

import numpy as np
import pandas as pd


def two_step_fca(
    oferta: pd.DataFrame,
    demanda: pd.DataFrame,
    tempo: pd.DataFrame,
    t_max: float,
) -> pd.DataFrame:
    """Distribui a oferta pelo método de área de captação flutuante em dois passos.

    O resultado contém uma linha para cada município da demanda e cada tipo de
    leito presente na oferta. Tempos ausentes ou maiores que ``t_max`` não
    estabelecem acesso; cada município, porém, alcança a oferta nele localizada.
    """
    codigos = demanda["cod_ibge"].to_numpy()
    populacao = demanda["populacao"].to_numpy(dtype=float)
    tipos = oferta["tipo_leito"].drop_duplicates().to_numpy()

    if len(codigos) == 0 or len(tipos) == 0:
        return pd.DataFrame(
            {
                "cod_ibge": pd.Series(dtype=demanda["cod_ibge"].dtype),
                "tipo_leito": pd.Series(dtype=oferta["tipo_leito"].dtype),
                "oferta_acessivel": pd.Series(dtype=float),
            }
        )

    destinos = oferta["cod_ibge"].drop_duplicates().to_numpy()
    origem_idx = pd.Index(codigos)
    destino_idx = pd.Index(destinos)

    alcanca = np.zeros((len(codigos), len(destinos)), dtype=bool)
    origens_tempo = origem_idx.get_indexer(tempo["origem"])
    destinos_tempo = destino_idx.get_indexer(tempo["destino"])
    minutos = pd.to_numeric(tempo["minutos"], errors="coerce").to_numpy()
    validos = (origens_tempo >= 0) & (destinos_tempo >= 0) & ~np.isnan(minutos) & (minutos <= t_max)
    alcanca[origens_tempo[validos], destinos_tempo[validos]] = True

    # A origem sempre conta com tempo zero, mesmo se a diagonal não foi fornecida.
    destinos_locais = destino_idx.get_indexer(codigos)
    locais = destinos_locais >= 0
    alcanca[np.flatnonzero(locais), destinos_locais[locais]] = True

    oferta_agrupada = (
        oferta.groupby(["cod_ibge", "tipo_leito"], sort=False, as_index=False)["leitos"]
        .sum()
        .pivot(index="cod_ibge", columns="tipo_leito", values="leitos")
        .reindex(index=destinos, columns=tipos, fill_value=0)
        .fillna(0)
        .to_numpy(dtype=float)
    )

    populacao_captada = alcanca.T @ populacao
    razao_oferta = np.divide(
        oferta_agrupada,
        populacao_captada[:, None],
        out=np.zeros_like(oferta_agrupada, dtype=float),
        where=populacao_captada[:, None] != 0,
    )
    oferta_acessivel = (alcanca @ razao_oferta) * populacao[:, None]

    return pd.DataFrame(
        {
            "cod_ibge": np.repeat(codigos, len(tipos)),
            "tipo_leito": np.tile(tipos, len(codigos)),
            "oferta_acessivel": oferta_acessivel.reshape(-1),
        }
    )


def deficit(
    demanda: pd.DataFrame,
    necessidade: pd.DataFrame,
    oferta_local: pd.DataFrame,
    oferta_acessivel: pd.DataFrame,
) -> pd.DataFrame:
    """Calcula necessidade e déficit por município e tipo de leito.

    O déficit considera a oferta acessível, que já inclui a oferta local. A
    coluna local é mantida separadamente para permitir a leitura do resultado.
    """
    tipos = necessidade["tipo_leito"].drop_duplicates()
    base = pd.MultiIndex.from_product([demanda["cod_ibge"], tipos], names=["cod_ibge", "tipo_leito"]).to_frame(
        index=False
    )

    taxas = necessidade.groupby("tipo_leito", sort=False, as_index=False)["leitos_por_mil_hab"].sum()
    base = base.merge(demanda[["cod_ibge", "populacao"]], on="cod_ibge", how="left")
    base = base.merge(taxas, on="tipo_leito", how="left")
    base["necessidade"] = base["populacao"] * base["leitos_por_mil_hab"].fillna(0) / 1_000

    local = oferta_local.groupby(["cod_ibge", "tipo_leito"], sort=False, as_index=False)["existente_local_sus"].sum()
    acessivel = oferta_acessivel.groupby(["cod_ibge", "tipo_leito"], sort=False, as_index=False)[
        "oferta_acessivel"
    ].sum()
    acessivel = acessivel.rename(columns={"oferta_acessivel": "oferta_acessivel_sus"})

    base = base.merge(local, on=["cod_ibge", "tipo_leito"], how="left")
    base = base.merge(acessivel, on=["cod_ibge", "tipo_leito"], how="left")
    base[["existente_local_sus", "oferta_acessivel_sus"]] = base[
        ["existente_local_sus", "oferta_acessivel_sus"]
    ].fillna(0)
    base["deficit"] = base["necessidade"] - base["oferta_acessivel_sus"]

    return base[
        [
            "cod_ibge",
            "tipo_leito",
            "necessidade",
            "existente_local_sus",
            "oferta_acessivel_sus",
            "deficit",
        ]
    ]
