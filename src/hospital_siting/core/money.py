"""Correção monetária por números-índice (IPCA, INCC). Usada só na gold; a silver guarda valores nominais."""

from __future__ import annotations

import pandas as pd


def _serie(indices: pd.DataFrame, indice: str) -> dict[str, float]:
    sub = indices[indices["indice"] == indice]
    return dict(zip(sub["mes"], sub["valor"].astype(float), strict=True))


def _valor(serie: dict[str, float], indice: str, mes: str) -> float:
    try:
        return serie[mes]
    except KeyError:
        raise KeyError(f"índice {indice} sem valor para {mes}") from None


def fator(indices: pd.DataFrame, indice: str, mes_origem: str, mes_base: str) -> float:
    """Fator multiplicativo que leva um valor de `mes_origem` para preços de `mes_base`."""
    s = _serie(indices, indice)
    return _valor(s, indice, mes_base) / _valor(s, indice, mes_origem)


def corrigir(valores: pd.Series, meses: pd.Series, indices: pd.DataFrame, indice: str, mes_base: str) -> pd.Series:
    """Corrige `valores` (nominais em `meses`, 'AAAA-MM') para `mes_base`. KeyError se faltar índice."""
    s = _serie(indices, indice)
    base = _valor(s, indice, mes_base)
    for m in pd.unique(meses.dropna()):
        _valor(s, indice, m)
    fatores = meses.map(lambda m: base / s[m])
    return valores * fatores


def mes_de_ano(ano: int) -> str:
    """Mês de referência para séries anuais (dezembro)."""
    return f"{ano}-12"
