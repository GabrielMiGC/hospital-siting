"""Monta as tabelas da camada gold (contrato em contracts/gold_schema.sql) a partir das silvers e seeds."""

from __future__ import annotations

import geopandas as gpd
import pandas as pd
from shapely.geometry import MultiPolygon, Point

from hospital_siting import seeds
from hospital_siting.core.config import Config
from hospital_siting.core.meta import record_validation
from hospital_siting.core.money import corrigir, mes_de_ano
from hospital_siting.core.storage import read_parquet, silver_path
from hospital_siting.modelo.acesso import deficit, two_step_fca
from hospital_siting.schemas.silver import TIPOS_LEITO


class GoldCheckError(Exception):
    """Alguma checagem 'fail' da gold falhou (todas são registradas antes)."""


def _silver(cfg: Config, nome: str) -> pd.DataFrame:
    return read_parquet(silver_path(cfg, nome))


def data_base_efetiva(cfg: Config, indices: pd.DataFrame, custo_obra: pd.DataFrame) -> str:
    """'auto' → mês mais recente do SINAPI presente no IPCA e no INCC (sem SINAPI: último mês comum aos índices)."""
    if cfg.data_base != "auto":
        return cfg.data_base
    comuns = set(indices.loc[indices.indice == "IPCA", "mes"]) & set(indices.loc[indices.indice == "INCC", "mes"])
    sinapi = set(custo_obra.loc[custo_obra.fonte == "SINAPI", "mes"]) & comuns
    candidatos = sinapi or comuns
    if not candidatos:
        raise ValueError("sem mês comum entre IPCA, INCC (e SINAPI) para a data-base")
    return max(candidatos)


def _corr(df: pd.DataFrame, col: str, meses: pd.Series, idx: pd.DataFrame, indice: str, base: str) -> pd.Series:
    return corrigir(df[col].astype(float), meses, idx, indice, base)


def _dim_municipio(cfg: Config, idx: pd.DataFrame, base: str) -> pd.DataFrame:
    mun = _silver(cfg, "municipio")
    geo = _silver(cfg, "municipio_geo")
    reg = _silver(cfg, "regiao_saude")
    rec = _silver(cfg, "receita_municipal")

    rec = rec.sort_values("exercicio").groupby("cod_ibge", as_index=False).last()
    rec["receita_corrente"] = _corr(rec, "receita_corrente", rec["exercicio"].map(mes_de_ano), idx, "IPCA", base)
    rec = rec.rename(columns={"exercicio": "exercicio_receita"})

    d = mun.merge(reg, on="cod_ibge", how="left").merge(rec, on="cod_ibge", how="left")
    tem_pib = d["pib"].notna()
    d["pib"] = d["pib"].astype(float)
    d.loc[tem_pib, "pib"] = corrigir(
        d.loc[tem_pib, "pib"], d.loc[tem_pib, "ano_pib"].map(mes_de_ano), idx, "IPCA", base
    )
    d["pib_per_capita"] = d["pib"] / d["populacao"].astype(float)
    d["receita_disponivel"] = d["receita_corrente"].notna()
    d["exercicio_receita"] = d["exercicio_receita"].astype("Int64")
    d["populacao"] = d["populacao"].astype(int)

    g = geo[["cod_ibge", "geom_sede", "geom_limite"]].copy()
    g["geom_limite"] = gpd.GeoSeries(g["geom_limite"]).apply(
        lambda x: MultiPolygon([x]) if x.geom_type == "Polygon" else x
    )
    out = d.merge(pd.DataFrame(g), on="cod_ibge", how="left")
    cols = [
        "cod_ibge",
        "nome",
        "uf",
        "populacao",
        "ano_populacao",
        "pib",
        "pib_per_capita",
        "ano_pib",
        "receita_corrente",
        "exercicio_receita",
        "receita_disponivel",
        "cod_regiao_saude",
        "nome_regiao_saude",
        "cod_macrorregiao",
        "geom_sede",
        "geom_limite",
    ]
    return out[cols]


def _valor_medio(sih: pd.DataFrame) -> pd.DataFrame:
    periodo = f"SIH {sih['competencia'].min()}..{sih['competencia'].max()}"
    enf = sih[sih.tipo_leito.isin(TIPOS_LEITO[:4])]
    g = enf.groupby("tipo_leito").agg(
        v=("valor_enf", "sum"), n=("internacoes", "sum"), dias=("dias_permanencia", "sum")
    )
    linhas = [
        {
            "tipo_leito": t,
            "unidade": "aih",
            "valor_medio": r.v / r.n,
            "permanencia_media_dias": r.dias / r.n,
            "n_observacoes": int(r.n),
            "fonte_periodo": periodo,
        }
        for t, r in g.iterrows()
        if r.n > 0
    ]
    for faixa, tipo in (("adulto", "uti_adulto"), ("neo_ped", "uti_neo_ped")):
        u = sih[sih.faixa_uti == faixa]
        diarias = int(u["diarias_uti"].sum())
        if diarias > 0:
            linhas.append(
                {
                    "tipo_leito": tipo,
                    "unidade": "diaria",
                    "valor_medio": u["valor_uti_corr"].sum() / diarias,
                    "permanencia_media_dias": diarias / int(u["internacoes"].sum()),
                    "n_observacoes": diarias,
                    "fonte_periodo": periodo,
                }
            )
    return pd.DataFrame(linhas)


def tabelas_gold(cfg: Config) -> dict[str, pd.DataFrame]:
    idx = _silver(cfg, "indice")
    obra = _silver(cfg, "custo_obra_m2")
    base = data_base_efetiva(cfg, idx, obra)
    t: dict[str, pd.DataFrame] = {"indice_correcao": idx.copy(), "_custo_obra_silver": obra, "_data_base": base}

    dim = _dim_municipio(cfg, idx, base)
    t["dim_municipio"] = dim

    # CNES
    lei = _silver(cfg, "cnes_leitos")
    est = _silver(cfg, "cnes_estabelecimento")
    t["leitos_existentes"] = lei.groupby(["cod_ibge", "tipo_leito"], as_index=False).agg(
        qtd_total=("qtd_total", "sum"), qtd_sus=("qtd_sus", "sum"), competencia_cnes=("competencia", "max")
    )
    sus_por_cnes = lei.groupby("cnes")["qtd_sus"].sum()
    e = est.copy()
    e["leitos_sus"] = e["cnes"].map(sus_por_cnes).fillna(0).astype(int)
    e["geom"] = [
        Point(lo, la) if pd.notna(lo) and pd.notna(la) else None for lo, la in zip(e["lon"], e["lat"], strict=True)
    ]
    t["estabelecimentos_hospitalares"] = e.rename(columns={"tipo_unidade": "tipo"})[
        ["cnes", "cod_ibge", "tipo", "natureza", "leitos_total", "leitos_sus", "geom"]
    ]

    # Necessidade e déficit (2SFCA)
    nec = seeds.necessidade(cfg)
    t["necessidade_leitos_param"] = nec[["tipo_leito", "leitos_por_mil_hab", "fonte"]].reset_index(drop=True)
    mat = _silver(cfg, "matriz_tempo")
    t["matriz_tempo_viagem"] = mat[["origem", "destino", "minutos_osrm", "km"]].copy()
    t_oferta = float(cfg.params.get("t_oferta_min", 120))
    oferta = lei[lei.tipo_leito.isin(TIPOS_LEITO)].groupby(["cod_ibge", "tipo_leito"], as_index=False)["qtd_sus"].sum()
    demanda = dim[["cod_ibge", "populacao"]]
    acc = two_step_fca(
        oferta.rename(columns={"qtd_sus": "leitos"}), demanda, mat.rename(columns={"minutos_osrm": "minutos"}), t_oferta
    )
    d = deficit(demanda, nec, oferta.rename(columns={"qtd_sus": "existente_local_sus"}), acc)
    d["t_oferta_min"] = int(t_oferta)
    t["deficit_leitos"] = d

    # SIH
    sih = _silver(cfg, "sih_agg").copy()
    sih["valor_total_corr"] = _corr(sih, "valor_total", sih["competencia"], idx, "IPCA", base)
    sih["valor_uti_corr"] = _corr(sih, "valor_uti", sih["competencia"], idx, "IPCA", base)
    sih["valor_enf"] = sih["valor_total_corr"] - sih["valor_uti_corr"]
    sih["ano"] = sih["competencia"].str[:4].astype(int)
    t["fluxo_internacoes"] = sih.groupby(
        ["cod_ibge_residencia", "cod_ibge_ocorrencia", "ano", "tipo_leito"], as_index=False
    ).agg(internacoes=("internacoes", "sum"), valor_total=("valor_total_corr", "sum"))
    t["valor_medio_internacao"] = _valor_medio(sih)

    # Custos
    o = obra.copy()
    o["valor_m2"] = _corr(o, "valor_m2", o["mes"], idx, "INCC", base)
    t["custo_obra_m2"] = o.rename(columns={"mes": "mes_origem"}).assign(data_base=base)[
        ["fonte", "padrao", "valor_m2", "mes_origem", "data_base"]
    ]
    eq = _silver(cfg, "equipamento_ambiente").copy()
    tem = eq["preco_ref"].notna()
    eq["preco_ref"] = eq["preco_ref"].astype(float)
    eq.loc[tem, "preco_ref"] = corrigir(eq.loc[tem, "preco_ref"], eq.loc[tem, "mes"], idx, "IPCA", base)
    t["equipamento_ambiente"] = (
        eq.assign(data_base=base).drop(columns=["mes"]).drop_duplicates(["ambiente", "equipamento"])
    )
    sal = _silver(cfg, "salario_ocupacao").copy()
    sal["salario_medio"] = _corr(sal, "salario_medio", sal["ano"].map(mes_de_ano), idx, "IPCA", base)
    sal["encargos_pct"] = float(cfg.params.get("encargos_pct", 0.70))
    t["salario_ocupacao"] = sal.assign(data_base=base)[
        ["cbo", "descricao", "salario_medio", "encargos_pct", "ano", "data_base"]
    ]

    # Seeds de parâmetros
    eqp = seeds.load(cfg, "dimensionamento_equipe")
    t["dimensionamento_equipe_param"] = eqp[
        ["setor", "cbo", "unidade", "razao", "turnos_dia", "cobertura_dias", "fonte"]
    ]
    cons = seeds.load(cfg, "consorcio")
    t["consorcio_param"] = cons[["parametro", "valor", "fonte"]]
    cus = seeds.load(cfg, "custeio")
    t["custeio_param"] = cus[["porte", "custeio_nao_pessoal_pct_pessoal", "fonte"]]
    arq = seeds.load(cfg, "arquetipos")
    t["arquetipo_leitos"] = arq[["porte", "tipo_leito", "leitos", "area_m2_ref"]]
    return t


TABELAS_COM_MUNICIPIO = {
    "leitos_existentes": ["cod_ibge"],
    "estabelecimentos_hospitalares": ["cod_ibge"],
    "deficit_leitos": ["cod_ibge"],
    "fluxo_internacoes": ["cod_ibge_residencia", "cod_ibge_ocorrencia"],
    "matriz_tempo_viagem": ["origem", "destino"],
}
TABELAS_MONETARIAS = ("custo_obra_m2", "equipamento_ambiente", "salario_ocupacao")


def checks_gold(cfg: Config, t: dict) -> None:
    falhas: list[str] = []

    def check(nome: str, ok: bool, detalhe: str = "", severidade: str = "fail") -> None:
        record_validation(cfg, "gold", nome, "pass" if ok else severidade, detalhe)
        if not ok and severidade == "fail":
            falhas.append(f"{nome}: {detalhe}")

    dim = t["dim_municipio"]
    cods = set(dim["cod_ibge"])
    check(
        "dim_municipio_contagem",
        len(dim) == cfg.n_municipios and dim["cod_ibge"].is_unique,
        f"{len(dim)} linhas, esperado {cfg.n_municipios}",
    )
    for tab, cols in TABELAS_COM_MUNICIPIO.items():
        orfaos = set().union(*(set(t[tab][c]) - cods for c in cols))
        check(f"orfaos_{tab}", not orfaos, ", ".join(sorted(orfaos)[:10]))
    mat = t["matriz_tempo_viagem"]
    diag = mat[mat.origem == mat.destino]
    check(
        "matriz_completa",
        len(mat) == len(cods) ** 2 and len(diag) == len(cods) and (diag.minutos_osrm == 0).all(),
        f"{len(mat)} pares, esperado {len(cods) ** 2}",
    )
    bases = set().union(*(set(t[tab]["data_base"]) for tab in TABELAS_MONETARIAS))
    check("data_base_unica", bases == {t["_data_base"]}, str(sorted(bases)))
    geoms_ok = all(g is not None and g.is_valid for col in ("geom_sede", "geom_limite") for g in dim[col])
    check("geometrias_validas", geoms_ok)
    sem_receita = sorted(cods - set(dim.loc[dim.receita_disponivel, "cod_ibge"]))
    check("municipios_sem_receita", not sem_receita, f"{len(sem_receita)}: {', '.join(sem_receita[:20])}", "warn")

    # sanidade: polos que mais recebem pacientes de fora deveriam ter déficit ≤ 0 (aviso)
    f = t["fluxo_internacoes"]
    externos = f[f.cod_ibge_residencia != f.cod_ibge_ocorrencia].groupby("cod_ibge_ocorrencia")["internacoes"].sum()
    polos = externos.nlargest(10).index
    d = t["deficit_leitos"].groupby("cod_ibge")["deficit"].sum()
    estranhos = [c for c in polos if d.get(c, 0) > 0]
    check("polos_com_deficit", not estranhos, ", ".join(estranhos), "warn")

    if falhas:
        raise GoldCheckError("; ".join(falhas))
