"""Agregação pura das AIHs (RD) por residência, ocorrência, tipo de leito e faixa de UTI."""

from __future__ import annotations

import pandas as pd

from hospital_siting.core.ids import to_ibge7
from hospital_siting.schemas.silver import FORA_DO_ESCOPO

CHAVES = ["cod_ibge_residencia", "cod_ibge_ocorrencia", "competencia", "tipo_leito", "faixa_uti"]
COLUNAS = [*CHAVES, "internacoes", "valor_total", "dias_permanencia", "diarias_uti", "valor_uti"]
TIPOS = {
    "internacoes": "int64",
    "valor_total": "float64",
    "dias_permanencia": "int64",
    "diarias_uti": "int64",
    "valor_uti": "float64",
}


def _norm_cod(s: pd.Series) -> pd.Series:
    """Texto limpo (sem espaços nem sufixo '.0'); vazio vira NA."""
    t = s.astype("string").str.strip().str.replace(r"\.0+$", "", regex=True)
    return t.mask(t == "")


def _num(s: pd.Series) -> pd.Series:
    return pd.to_numeric(s, errors="coerce").fillna(0)


def agregar_rd(
    rd: pd.DataFrame, mapa6: dict[str, str], mapa_espec: pd.DataFrame, competencia: str
) -> tuple[pd.DataFrame, dict[str, int]]:
    """Agrega o RD de uma competência. Devolve (SIH_AGG, descartes)."""
    prefixos = {v[:2] for v in mapa6.values()}
    res_raw = _norm_cod(rd["MUNIC_RES"])
    mov_raw = _norm_cod(rd["MUNIC_MOV"])

    fora_uf = (res_raw.notna() & ~res_raw.str[:2].isin(prefixos)).fillna(False).astype(bool)
    res7 = to_ibge7(res_raw, mapa6)
    mov7 = to_ibge7(mov_raw, mapa6)
    invalido = (~fora_uf & (res7.isna() | mov7.isna())).astype(bool)
    descartes = {"residencia_fora_uf": int(fora_uf.sum()), "codigo_invalido": int(invalido.sum())}

    ok = ~(fora_uf | invalido)
    df = rd.loc[ok]

    idade = _num(df["IDADE"])
    cod_idade = _norm_cod(df["COD_IDADE"])
    menor = (cod_idade.isin(["0", "1", "2", "3"]) | ((cod_idade == "4") & (idade < 18))).fillna(False)
    uti = _num(df["UTI_MES_TO"])
    faixa = pd.Series("nenhuma", index=df.index, dtype=object)
    faixa[(uti > 0) & menor] = "neo_ped"
    faixa[(uti > 0) & ~menor] = "adulto"

    mapa = dict(zip(mapa_espec["espec"].astype(str).str.strip(), mapa_espec["tipo_leito"], strict=True))
    tipo = _norm_cod(df["ESPEC"]).map(mapa).fillna(FORA_DO_ESCOPO).astype(object)

    base = pd.DataFrame(
        {
            "cod_ibge_residencia": res7[ok].astype(str),
            "cod_ibge_ocorrencia": mov7[ok].astype(str),
            "competencia": competencia,
            "tipo_leito": tipo,
            "faixa_uti": faixa,
            "valor_total": _num(df["VAL_TOT"]).astype(float),
            "dias_permanencia": _num(df["DIAS_PERM"]).astype("int64"),
            "diarias_uti": uti.astype("int64"),
            "valor_uti": _num(df["VAL_UTI"]).astype(float),
        },
        index=df.index,
    )
    if base.empty:
        vazio = pd.DataFrame({c: pd.Series(dtype=object) for c in COLUNAS})
        return vazio.astype(TIPOS), descartes

    out = base.groupby(CHAVES, as_index=False).agg(
        internacoes=("valor_total", "size"),
        valor_total=("valor_total", "sum"),
        dias_permanencia=("dias_permanencia", "sum"),
        diarias_uti=("diarias_uti", "sum"),
        valor_uti=("valor_uti", "sum"),
    )
    return out[COLUNAS].astype({"internacoes": "int64"}), descartes
