"""Transformação do seed de CUB do Sinduscon-BA."""

from __future__ import annotations

import pandas as pd

from hospital_siting.core.parsing import parse_brl


def custo_m2(tabela: pd.DataFrame, mes: str) -> pd.DataFrame:
    """Converte os padrões comerciais/hospitalares do CUB para a silver."""
    col_valor = next((col for col in ("valor_m2", "valor") if col in tabela.columns), None)
    if "padrao" not in tabela.columns or col_valor is None:
        raise ValueError("tabela CUB requer as colunas 'padrao' e 'valor' ou 'valor_m2'")

    valores = tabela[col_valor].map(parse_brl)
    out = pd.DataFrame(
        {
            "fonte": "CUB",
            "padrao": tabela["padrao"].astype("string").str.strip(),
            "valor_m2": pd.to_numeric(valores, errors="coerce").astype(float),
            "mes": mes,
        }
    )
    return out.dropna(subset=["padrao", "valor_m2"]).reset_index(drop=True)
