"""Transformações puras dos arquivos ST e LT do CNES."""

from __future__ import annotations

import warnings

import pandas as pd

from hospital_siting.core.ids import to_ibge7
from hospital_siting.schemas.silver import FORA_DO_ESCOPO

TIPOS_HOSPITALARES = frozenset({"05", "07", "15", "62"})


def _codigo(values: pd.Series, largura: int) -> pd.Series:
    """Normaliza campos de código lidos de DBF/CSV sem perder zeros à esquerda."""
    return values.astype("string").str.strip().str.removesuffix(".0").str.zfill(largura)


def _natureza(st: pd.DataFrame) -> pd.Series:
    nat_jur = st.get("NAT_JUR", pd.Series(pd.NA, index=st.index, dtype="string"))
    nat_jur = nat_jur.astype("string").str.strip()
    tem_nat_jur = nat_jur.notna() & nat_jur.ne("")
    natureza = nat_jur.str[:1].map({"1": "publica", "2": "privada", "3": "filantropica"}).fillna("outra")

    if "ESFERA_A" in st:
        esfera = st["ESFERA_A"].astype("string").str.strip().str.upper()
        por_esfera = esfera.map(
            {
                "1": "publica",
                "2": "publica",
                "3": "publica",
                "4": "privada",
                "F": "publica",
                "E": "publica",
                "M": "publica",
                "P": "privada",
            }
        )
        natureza = natureza.where(tem_nat_jur, por_esfera.fillna("outra"))
    return natureza.astype("string")


def estabelecimentos(
    st: pd.DataFrame,
    mapa6: dict[str, str],
    competencia: str,
    leitos: pd.DataFrame | None = None,
) -> pd.DataFrame:
    """Seleciona estabelecimentos hospitalares e os adapta ao contrato silver."""
    tipo_unidade = _codigo(st["TP_UNID"], 2)
    selecionados = st.loc[tipo_unidade.isin(TIPOS_HOSPITALARES)].copy()
    selecionados["tipo_unidade"] = tipo_unidade.loc[selecionados.index]
    selecionados["cod_ibge"] = to_ibge7(selecionados["CODUFMUN"], mapa6)
    selecionados = selecionados.loc[selecionados["cod_ibge"].notna()].copy()

    totais = pd.Series(dtype="int64")
    if leitos is not None and not leitos.empty:
        totais = leitos.groupby("cnes", sort=False)["qtd_total"].sum()

    cnes = _codigo(selecionados["CNES"], 7)
    out = pd.DataFrame(
        {
            "cnes": cnes,
            "cod_ibge": selecionados["cod_ibge"].astype("string"),
            "tipo_unidade": selecionados["tipo_unidade"].astype("string"),
            "natureza": _natureza(selecionados),
            "leitos_total": cnes.map(totais).fillna(0).astype(int),
            "lat": pd.Series(float("nan"), index=selecionados.index, dtype=float),
            "lon": pd.Series(float("nan"), index=selecionados.index, dtype=float),
            "competencia": pd.Series(competencia, index=selecionados.index, dtype="string"),
        }
    )
    return out.reset_index(drop=True)


def leitos(
    lt: pd.DataFrame,
    mapa6: dict[str, str],
    mapa_leitos: pd.DataFrame,
    competencia: str,
) -> pd.DataFrame:
    """Converte leitos do CNES, limitando a quantidade SUS ao total existente."""
    base = lt.copy()
    base["cod_ibge"] = to_ibge7(base["CODUFMUN"], mapa6)
    base = base.loc[base["cod_ibge"].notna()].copy()
    base["cnes"] = _codigo(base["CNES"], 7)
    base["cod_leito"] = _codigo(base["CODLEITO"], 2)

    mapa = mapa_leitos.loc[:, ["cod_leito", "tipo_leito"]].copy()
    mapa["cod_leito"] = _codigo(mapa["cod_leito"], 2)
    tipo_por_codigo = mapa.drop_duplicates("cod_leito").set_index("cod_leito")["tipo_leito"]
    base["tipo_leito"] = base["cod_leito"].map(tipo_por_codigo)

    desconhecidos = sorted(base.loc[base["tipo_leito"].isna(), "cod_leito"].unique())
    if desconhecidos:
        warnings.warn(
            f"códigos de leito ausentes do mapa: {', '.join(desconhecidos)}",
            UserWarning,
            stacklevel=2,
        )
    base["tipo_leito"] = base["tipo_leito"].fillna(FORA_DO_ESCOPO).astype("string")

    qtd_total = pd.to_numeric(base["QT_EXIST"], errors="coerce").fillna(0).clip(lower=0).astype(int)
    qtd_sus = pd.to_numeric(base["QT_SUS"], errors="coerce").fillna(0).clip(lower=0).astype(int)

    out = pd.DataFrame(
        {
            "cnes": base["cnes"].astype("string"),
            "cod_ibge": base["cod_ibge"].astype("string"),
            "cod_leito": base["cod_leito"].astype("string"),
            "tipo_leito": base["tipo_leito"],
            "qtd_total": qtd_total,
            "qtd_sus": qtd_sus.clip(upper=qtd_total),
            "competencia": pd.Series(competencia, index=base.index, dtype="string"),
        }
    )
    return out.reset_index(drop=True)
