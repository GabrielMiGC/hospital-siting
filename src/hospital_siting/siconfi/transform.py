"""Transformações puras do SICONFI (DCA, Anexo I-C)."""

from __future__ import annotations

import unicodedata

import pandas as pd

CONTA_RECEITA_CORRENTE = "RO1.0.0.0.00.0.0"


def _norm(s: str) -> str:
    nfkd = unicodedata.normalize("NFKD", str(s))
    return " ".join("".join(c for c in nfkd if not unicodedata.combining(c)).lower().split())


def receita_corrente(itens: pd.DataFrame, cod_uf: str) -> pd.DataFrame:
    """Receita corrente municipal líquida de deduções (nominal, no exercício da DCA).

    Regra: "Receitas Brutas Realizadas" menos as colunas de dedução ("Deduções - FUNDEB" e
    "Outras Deduções da Receita") da conta "Receitas Correntes" (cod_conta RO1.0.0.0.00.0.0).
    Colunas são comparadas sem acento/caixa. Município sem a linha bruta fica ausente.
    """
    cols = ["cod_ibge", "exercicio", "receita_corrente"]
    df = itens.copy()
    df["cod_ibge"] = df["cod_ibge"].astype(str).str.strip().str.replace(r"\.0$", "", regex=True).str.zfill(7)
    df = df[df["cod_ibge"].str.startswith(str(cod_uf)) & (df["cod_conta"] == CONTA_RECEITA_CORRENTE)]
    if df.empty:
        return pd.DataFrame({"cod_ibge": pd.Series(dtype=str), "exercicio": pd.Series(dtype=int),
                             "receita_corrente": pd.Series(dtype=float)})[cols]
    col = df["coluna"].map(_norm)
    bruta = col == "receitas brutas realizadas"
    deducao = col.str.startswith("deducoes") | col.str.startswith("outras deducoes")
    df = df.assign(_sinal=bruta.astype(float) - deducao.astype(float), _bruta=bruta)
    df = df[bruta | deducao]
    df["valor"] = df["valor"].astype(float) * df["_sinal"]
    g = df.groupby(["cod_ibge", "exercicio"], as_index=False).agg(
        receita_corrente=("valor", "sum"), _tem_bruta=("_bruta", "any"))
    g = g[g["_tem_bruta"]]
    g = g.sort_values(["cod_ibge", "exercicio"]).drop_duplicates("cod_ibge", keep="last")
    g["exercicio"] = g["exercicio"].astype(int)
    g["receita_corrente"] = g["receita_corrente"].astype(float).round(2)
    return g[cols].reset_index(drop=True)
