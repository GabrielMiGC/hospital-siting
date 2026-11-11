"""Transformações puras: IPCA (SIDRA 1737), INCC (SGS 192) e SIGTAP (largura fixa)."""

from __future__ import annotations

import pandas as pd


def ipca(sidra_raw: pd.DataFrame) -> pd.DataFrame:
    """Número-índice IPCA a partir das linhas SIDRA (sem cabeçalho). Marcadores ('...', '-', etc.) são descartados."""
    d3 = sidra_raw["D3C"].astype(str)
    valor = pd.to_numeric(sidra_raw["V"], errors="coerce")
    out = pd.DataFrame({"indice": "IPCA", "mes": d3.str[:4] + "-" + d3.str[4:6], "valor": valor.astype(float)})
    out = out[out["valor"].notna()]
    return out.sort_values("mes").reset_index(drop=True)


def incc(raw: pd.DataFrame) -> pd.DataFrame:
    """INCC-M: encadeia as variações % mensais em número-índice (1º mês = 100.0; sua variação é ignorada)."""
    df = pd.DataFrame(
        {"data": pd.to_datetime(raw["data"], format="%d/%m/%Y"), "pct": pd.to_numeric(raw["valor"], errors="coerce")}
    ).dropna()
    df = df.sort_values("data").reset_index(drop=True)
    fatores = 1 + df["pct"] / 100.0
    fatores.iloc[0] = 1.0
    valor = 100.0 * fatores.cumprod()
    return pd.DataFrame({"indice": "INCC", "mes": df["data"].dt.strftime("%Y-%m"), "valor": valor.astype(float)})


def sigtap(layout: pd.DataFrame, linhas: list[str], competencia: str) -> pd.DataFrame:
    """tb_procedimento.txt (largura fixa, Inicio 1-based) -> procedimentos com valores em reais."""
    pos = {r["Coluna"]: (int(r["Inicio"]) - 1, int(r["Fim"])) for _, r in layout.iterrows()}

    def campo(nome: str) -> list[str]:
        i, f = pos[nome]
        return [ln[i:f] for ln in linhas]

    def reais(nome: str) -> list[float]:
        return [int(v.strip() or 0) / 100.0 for v in campo(nome)]

    return pd.DataFrame(
        {
            "co_procedimento": [v.strip() for v in campo("CO_PROCEDIMENTO")],
            "no_procedimento": [v.strip() for v in campo("NO_PROCEDIMENTO")],
            "valor_sh": reais("VL_SH"),
            "valor_sp": reais("VL_SP"),
            "competencia": competencia,
        }
    )


def desde_incc(raw: pd.DataFrame, mes_inicio: str = "1995-01") -> pd.DataFrame:
    """INCC encadeado só a partir de `mes_inicio` (padrão: pós-Real), evitando números-índice astronômicos
    herdados da hiperinflação; as razões entre meses — as únicas usadas na correção — são idênticas."""
    datas = pd.to_datetime(raw["data"], format="%d/%m/%Y")
    return incc(raw.loc[datas >= pd.Timestamp(f"{mes_inicio}-01")].reset_index(drop=True))
