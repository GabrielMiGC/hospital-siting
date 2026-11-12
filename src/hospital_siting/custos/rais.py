"""Agrega salários nominais por ocupação a partir dos vínculos da RAIS."""

from __future__ import annotations

from collections.abc import Mapping

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


def descricoes_cbo(tabela: pd.DataFrame) -> dict[str, str]:
    """Mapa código → título da ocupação a partir da tabela CBO do DATASUS (DBF/CBO.dbf: CBO, DS_CBO)."""
    return {
        _codigo(cbo, 6): str(ds).strip()
        for cbo, ds in zip(tabela["CBO"], tabela["DS_CBO"], strict=True)
        if str(ds).strip()
    }


def salarios(
    rais_vinc: pd.DataFrame,
    cbos: list[str],
    cod_uf: str,
    ano: int,
    descricoes: Mapping[str, str] | None = None,
) -> pd.DataFrame:
    """Calcula a mediana da remuneração de dezembro por CBO na UF (normalizada a 40 h semanais)."""
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
    if COL_HORAS in dados:  # normaliza para 40 h semanais; contratos sem horas são descartados
        horas = pd.to_numeric(dados[COL_HORAS], errors="coerce")
        dados = dados.loc[horas.gt(0)].copy()
        dados["_salario"] = dados["_salario"] * 40 / horas[horas.gt(0)]

    agrupado = dados.groupby("_cbo", sort=True, as_index=False)["_salario"].median()
    if descricoes is None:  # microdados da RAIS 2024 trazem só o código; a coluna existe em layouts antigos
        col = next((c for c in ("CBO Ocupação 2002 - Descrição", "Descrição CBO", "descricao") if c in dados), None)
        descricoes = dados.groupby("_cbo")[col].first().astype(str).to_dict() if col else {}
    descricao = agrupado["_cbo"].map(descricoes)
    if faltando := sorted(agrupado.loc[descricao.isna(), "_cbo"]):
        raise ValueError(f"CBO sem descrição na tabela de ocupações: {faltando}")

    return pd.DataFrame(
        {
            "cbo": agrupado["_cbo"].astype(str),
            "descricao": descricao.astype(str),
            "salario_medio": agrupado["_salario"].astype(float),
            "ano": int(ano),
        }
    )


ALIASES = {
    COL_CBO: ("CBO Ocupação 2002", "CBO 2002 Ocupação - Código"),
    COL_MUNICIPIO: ("Município", "Município - Código"),
    COL_REMUNERACAO: ("Vl Remun Dezembro Nom", "Vl Rem Dezembro Nom"),
}
COL_HORAS = "Qtd Hora Contr"


def ler_vinculos(txt, cod_uf: str, cbos: list[str], chunksize: int = 500_000) -> pd.DataFrame:
    """Lê os vínculos da RAIS em blocos (layout até 2023: ';' e vírgula decimal; 2024+: ',' com aspas e ponto
    decimal), mantendo só a UF e os CBOs pedidos, com colunas canônicas."""
    with open(txt, "rb") as f:
        primeira = f.readline().decode("latin-1")
    sep = ";" if primeira.count(";") > primeira.count(",") else ","
    cab = list(pd.read_csv(txt, sep=sep, encoding="latin-1", nrows=0).columns)
    origem = {}
    for canonica, nomes in ALIASES.items():
        achada = next((n for n in nomes if n in cab), None)
        if achada is None:
            raise ValueError(f"RAIS sem coluna {canonica} (aceitas: {nomes})")
        origem[achada] = canonica
    if COL_HORAS in cab:
        origem[COL_HORAS] = COL_HORAS
    alvo = {_codigo(c, 6) for c in cbos}
    partes = []
    leitor = pd.read_csv(txt, sep=sep, encoding="latin-1", dtype=str, usecols=list(origem), chunksize=chunksize)
    for bloco in leitor:
        bloco = bloco.rename(columns=origem)[
            [COL_CBO, COL_MUNICIPIO, COL_REMUNERACAO, *([COL_HORAS] if COL_HORAS in origem else [])]
        ]
        mun = bloco[COL_MUNICIPIO].str.strip()
        cbo = bloco[COL_CBO].str.strip().map(lambda v: _codigo(v, 6))
        partes.append(bloco.loc[mun.str.startswith(str(cod_uf)) & cbo.isin(alvo)].assign(**{COL_CBO: cbo}))
    out = pd.concat(partes, ignore_index=True) if partes else pd.DataFrame(columns=list(ALIASES))
    if sep == ",":  # ponto decimal: converter já, para parse_brl não confundir com separador de milhar
        out[COL_REMUNERACAO] = pd.to_numeric(out[COL_REMUNERACAO].str.strip(), errors="coerce")
    return out
