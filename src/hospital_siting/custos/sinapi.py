"""Transformação do custo de obra por m² publicado pelo SINAPI."""

from __future__ import annotations

import unicodedata

import pandas as pd

from hospital_siting.core.parsing import parse_brl


def _normalizar(texto: object) -> str:
    sem_acento = unicodedata.normalize("NFKD", str(texto)).encode("ascii", "ignore").decode()
    return " ".join(sem_acento.lower().replace("_", " ").split())


def _coluna(df: pd.DataFrame, *nomes: str) -> object:
    normalizadas = {_normalizar(col): col for col in df.columns}
    for nome in nomes:
        if nome in normalizadas:
            return normalizadas[nome]
    raise ValueError(f"planilha SINAPI sem coluna esperada: {nomes}")


def custo_m2(xls: pd.DataFrame, uf: str, mes: str) -> pd.DataFrame:
    """Extrai os projetos de referência da UF e converte valores monetários BR."""
    col_uf = _coluna(xls, "uf")
    col_padrao = _coluna(xls, "projeto de referencia", "padrao")
    col_valor = _coluna(xls, "custo medio m2 (r$)", "custo medio m² (r$)", "valor m2", "valor")

    filtro = xls[col_uf].astype("string").str.strip().str.upper().eq(uf.strip().upper())
    dados = xls.loc[filtro, [col_padrao, col_valor]].copy()
    valores = dados[col_valor].map(parse_brl)
    out = pd.DataFrame(
        {
            "fonte": "SINAPI",
            "padrao": dados[col_padrao].astype("string").str.strip(),
            "valor_m2": pd.to_numeric(valores, errors="coerce").astype(float),
            "mes": mes,
        }
    )
    return out.dropna(subset=["padrao", "valor_m2"]).reset_index(drop=True)


def de_sidra(linhas: pd.DataFrame) -> pd.DataFrame:
    """SINAPI via IBGE/SIDRA tabela 2296, variável 48 (custo médio m² em moeda corrente), linhas sem cabeçalho."""
    dados = linhas.loc[linhas["D2C"].astype(str) == "48"].copy()
    dados["valor_m2"] = pd.to_numeric(dados["V"], errors="coerce")
    dados = dados.dropna(subset=["valor_m2"])
    mes = dados["D3C"].astype(str).str[:4] + "-" + dados["D3C"].astype(str).str[4:6]
    out = pd.DataFrame(
        {
            "fonte": "SINAPI",
            "padrao": "Custo médio m² SINAPI (IBGE/Caixa, média residencial da UF; NÃO é custo hospitalar)",
            "valor_m2": dados["valor_m2"].astype(float),
            "mes": mes,
        }
    )
    return out.sort_values("mes").reset_index(drop=True)
