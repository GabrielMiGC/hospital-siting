"""Seeds curados à mão (seeds/*.csv), sempre com colunas de proveniência."""

from __future__ import annotations

import pandas as pd

from hospital_siting.core.config import Config

PROVENIENCIA = ("fonte", "documento", "pagina_ou_artigo", "observacao")
SEEDS = (
    "necessidade_leitos",
    "mapa_leitos_cnes",
    "mapa_espec_sih",
    "dimensionamento_equipe",
    "custeio",
    "consorcio",
    "arquetipos",
)
# colunas de código que precisam continuar texto (zeros à esquerda)
TEXTO = {"cod_leito", "espec", "cbo", "porte", "tipo_leito", "parametro", "setor", "unidade", *PROVENIENCIA}


def load(cfg: Config, nome: str) -> pd.DataFrame:
    path = cfg.seeds_dir / f"{nome}.csv"
    cab = pd.read_csv(path, nrows=0).columns
    df = pd.read_csv(path, dtype={c: str for c in cab if c in TEXTO}, keep_default_na=False, na_values=[""])
    faltando = [c for c in PROVENIENCIA if c not in df.columns]
    if faltando:
        raise ValueError(f"seed {nome} sem colunas de proveniência: {faltando}")
    df["observacao"] = df["observacao"].fillna("")
    return df


def necessidade(cfg: Config) -> pd.DataFrame:
    """Parâmetro de leitos por mil habitantes no cenário configurado (padrão: 2)."""
    df = load(cfg, "necessidade_leitos")
    if "cenario" in df.columns:
        cen = int(cfg.params.get("cenario_necessidade", 2))
        df = df[df["cenario"].astype(int) == cen]
        if df.empty:
            raise ValueError(f"necessidade_leitos sem linhas para o cenário {cen}")
    return df
