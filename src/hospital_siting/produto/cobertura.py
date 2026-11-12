"""Cobertura gradual por tempo de viagem e concentração de hospitais existentes."""

from __future__ import annotations

import numpy as np
import pandas as pd

from hospital_siting.produto.dados import Gold


def peso_cobertura(minutos: np.ndarray, t_full: float, t_max: float, fator_osrm: float = 1.0) -> np.ndarray:
    """1 até ``t_full``, linear até 0 em ``t_max``, 0 depois. Sem rota (NaN) = 0. Tempo × ``fator_osrm``."""
    t = np.asarray(minutos, dtype=float) * fator_osrm
    if t_max <= t_full:
        w = (t <= t_full).astype(float)
    else:
        w = np.clip((t_max - t) / (t_max - t_full), 0.0, 1.0)
        w[t >= t_max] = 0.0
    w[np.isnan(t)] = 0.0
    return w


def hospitais_no_raio(gold: Gold, t_min: float, fator_osrm: float = 1.0) -> pd.Series:
    """Nº de estabelecimentos hospitalares a até ``t_min`` da sede de cada município (inclui os do próprio)."""
    est = gold.estabelecimentos.groupby("cod_ibge").size().rename("n")
    tm = gold.tempos[(gold.tempos["minutos"] * fator_osrm) <= t_min][["origem", "destino"]]
    proprios = pd.DataFrame({"origem": gold.municipios["cod_ibge"], "destino": gold.municipios["cod_ibge"]})
    pares = pd.concat([tm, proprios]).drop_duplicates()
    n = pares.merge(est, left_on="destino", right_index=True, how="inner").groupby("origem")["n"].sum()
    return n.reindex(gold.municipios["cod_ibge"], fill_value=0).astype(int).rename_axis(None)
