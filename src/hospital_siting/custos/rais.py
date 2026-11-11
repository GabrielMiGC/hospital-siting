"""Agrega salários nominais por ocupação a partir dos vínculos da RAIS."""

from __future__ import annotations

import pandas as pd

from hospital_siting.core.parsing import parse_brl

COL_MUNICIPIO = "Município"
COL_CBO = "CBO Ocupação 2002"
COL_REMUNERACAO = "Vl Remun Dezembro Nom"


def _codigo(valor: object, largura: int | None = None) -> str:
    if pd.isna(valor):
        return ""
    texto = str(valor).strip()
    if texto.endswith(".0"):
        texto = texto[:-2]
    return texto.zfill(largura) if largura else texto


def salarios(rais_vinc: pd.DataFrame, cbos: list[str], cod_uf: str, ano: int) -> pd.DataFrame:
    """Calcula a mediana da remuneração de dezembro por CBO na UF."""
    obrigatorias = {COL_MUNICIPIO, COL_CBO, COL_REMUNERACAO}
    if faltantes := obrigatorias - set(rais_vinc.columns):
        raise ValueError(f"microdados RAIS sem colunas: {sorted(faltantes)}")

    dados = rais_vinc.copy()
    dados["_municipio"] = dados[COL_MUNICIPIO].map(_codigo)
    dados["_cbo"] = dados[COL_CBO].map(lambda valor: _codigo(valor, 6))
    dados["_salario"] = dados[COL_REMUNERACAO].map(parse_brl)
    cbos_normalizados = {_codigo(cbo, 6) for cbo in cbos}
    filtro = dados["_municipio"].str.startswith(str(cod_uf)) & dados["_cbo"].isin(cbos_normalizados)
    dados = dados.loc[filtro].copy()
    dados["_salario"] = pd.to_numeric(dados["_salario"], errors="coerce")
    dados = dados.loc[dados["_salario"].gt(0)]

    descricoes = next(
        (col for col in ("CBO Ocupação 2002 - Descrição", "Descrição CBO", "descricao") if col in dados),
        None,
    )
    agrupado = dados.groupby("_cbo", sort=True, as_index=False)["_salario"].median()
    if descricoes:
        mapa_descricao = dados.groupby("_cbo")[descricoes].first().astype(str)
        descricao = agrupado["_cbo"].map(mapa_descricao)
    else:
        descricao = agrupado["_cbo"]

    return pd.DataFrame(
        {
            "cbo": agrupado["_cbo"].astype(str),
            "descricao": descricao.astype(str),
            "salario_medio": agrupado["_salario"].astype(float),
            "ano": int(ano),
        }
    )


def ler_vinculos(txt, cod_uf: str, cbos: list[str], chunksize: int = 500_000) -> pd.DataFrame:
    """Lê o .txt de vínculos da RAIS (';', latin-1) em blocos, mantendo só a UF e os CBOs pedidos."""
    colunas = [COL_CBO, COL_MUNICIPIO, COL_REMUNERACAO]
    cab = pd.read_csv(txt, sep=";", encoding="latin-1", nrows=0).columns
    if faltantes := set(colunas) - set(cab):
        raise ValueError(f"RAIS sem colunas: {sorted(faltantes)}")
    alvo = {_codigo(c, 6) for c in cbos}
    partes = []
    for bloco in pd.read_csv(txt, sep=";", encoding="latin-1", dtype=str, usecols=colunas, chunksize=chunksize):
        bloco = bloco[colunas]
        filtro = bloco[COL_MUNICIPIO].str.strip().str.startswith(str(cod_uf)) & bloco[COL_CBO].str.strip().isin(alvo)
        partes.append(bloco.loc[filtro])
    return pd.concat(partes, ignore_index=True) if partes else pd.DataFrame(columns=colunas)
