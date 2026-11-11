"""Códigos de município: IBGE 7 dígitos (chave universal) e conversão do formato DATASUS (6 dígitos)."""

from __future__ import annotations

from collections.abc import Iterable

import pandas as pd


def build_ibge6_map(cod7: Iterable[str]) -> dict[str, str]:
    """Mapa 6→7 dígitos construído a partir da lista oficial (sem calcular dígito verificador)."""
    mapa: dict[str, str] = {}
    for c in cod7:
        c = str(c).strip()
        k = c[:6]
        if k in mapa and mapa[k] != c:
            raise ValueError(f"colisão no código de 6 dígitos {k}: {mapa[k]} e {c}")
        mapa[k] = c
    return mapa


def to_ibge7(cod6: pd.Series, mapa: dict[str, str]) -> pd.Series:
    """Converte códigos de 6 (ou 7) dígitos; inválidos, ignorados ou de outra UF viram NA."""
    validos7 = set(mapa.values())

    def conv(v: object) -> object:
        if v is None or (isinstance(v, float) and pd.isna(v)) or v is pd.NA:
            return pd.NA
        s = "".join(ch for ch in str(v).strip().split(".")[0] if ch.isdigit())
        if len(s) == 7:
            return s if s in validos7 else pd.NA
        if len(s) == 6:
            return mapa.get(s, pd.NA)
        return pd.NA

    return cod6.map(conv).astype("string")
