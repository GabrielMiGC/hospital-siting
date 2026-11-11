"""Pipeline bronze/silver para custos de obra, equipamentos e salários."""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from hospital_siting.core.config import Config
from hospital_siting.core.meta import record_run, record_validation
from hospital_siting.core.storage import bronze_path, fetch_to_raw, silver_path, write_parquet
from hospital_siting.core.validation import validate, warn_if
from hospital_siting.custos import cub, rais, renem, sinapi
from hospital_siting.schemas.silver import CUSTO_OBRA_M2, EQUIPAMENTO_AMBIENTE, SALARIO_OCUPACAO

RENEM_URL = "https://portalfns.saude.gov.br/idg_download/lista-renem/"
AMBIENTES_OBRIGATORIOS = {
    "uti": ("uti", "terapia intensiva"),
    "centro cirúrgico": ("centro cirúrgico", "sala cirúrgica"),
    "imagem": ("imagem", "diagnóstico por imagem"),
    "ps": ("ps", "pronto-socorro", "pronto socorro", "emergência"),
}


def _param(cfg: Config, nome: str) -> str:
    valor = cfg.params.get(nome)
    if valor in (None, ""):
        raise ValueError(f"cfg.params requer '{nome}' para executar o pipeline de custos")
    return str(valor)


def _csv(path: Path) -> pd.DataFrame:
    with path.open("rb") as arquivo:
        primeira_linha = arquivo.readline()
    try:
        cabecalho = primeira_linha.decode("utf-8")
        encoding = "utf-8"
    except UnicodeDecodeError:
        cabecalho = primeira_linha.decode("latin-1")
        encoding = "latin-1"
    separador = ";" if cabecalho.count(";") > cabecalho.count(",") else ","
    return pd.read_csv(path, sep=separador, encoding=encoding)


def _cbos(seed: pd.DataFrame) -> list[str]:
    coluna = next((col for col in ("cbo", "CBO") if col in seed.columns), None)
    if coluna is None:
        raise ValueError("seed de equipe sem coluna 'cbo'")
    return seed[coluna].dropna().astype(str).str.replace(r"\.0$", "", regex=True).tolist()


def _registrar_cobertura(cfg: Config, equipamentos: pd.DataFrame) -> None:
    nomes = equipamentos["ambiente"].astype(str).str.casefold()
    for ambiente, aliases in AMBIENTES_OBRIGATORIOS.items():
        selecionado = pd.Series(False, index=equipamentos.index)
        for alias in aliases:
            selecionado |= nomes.str.contains(alias, regex=False)
        linhas = equipamentos.loc[selecionado]
        cobertos = int(linhas["preco_ref"].notna().sum())
        total = len(linhas)
        status = "pass" if total and cobertos == total else "warn"
        record_validation(
            cfg,
            "equipamento_ambiente",
            f"cobertura_preco:{ambiente}",
            status,
            f"{cobertos}/{total} equipamentos com preço",
        )


def run(cfg: Config) -> None:
    """Baixa fontes configuradas e materializa as três silvers do domínio."""
    try:
        mes = _param(cfg, "custos_mes")
        ano_rais = int(_param(cfg, "rais_ano"))
        sinapi_url = _param(cfg, "sinapi_url")
        arq_sinapi = fetch_to_raw(cfg, "sinapi", mes, sinapi_url, Path(sinapi_url).name or "sinapi.xlsx")
        bruto_sinapi = pd.read_excel(arq_sinapi.path)
        write_parquet(bruto_sinapi, bronze_path(cfg, "sinapi", f"custos-{mes}"))
        custo_sinapi = sinapi.custo_m2(bruto_sinapi, cfg.uf, mes)

        cub_seed = _csv(cfg.seeds_dir / "cub_ba.csv")
        write_parquet(cub_seed, bronze_path(cfg, "cub", f"custos-{mes}"))
        custo_cub = cub.custo_m2(cub_seed, mes)
        warn_if(cfg, True, "custo_obra_m2", "cub_seed_manual", "CUB transcrito de fonte do Sinduscon")

        renem_url = str(cfg.params.get("renem_url", RENEM_URL))
        arq_renem = fetch_to_raw(cfg, "renem", mes, renem_url, "lista-renem.xlsx")
        bruto_renem = pd.read_excel(arq_renem.path, header=None)
        lista_renem = renem.parse_lista(bruto_renem)
        write_parquet(lista_renem, bronze_path(cfg, "renem", f"lista-{mes}"))
        seed_equipamentos = _csv(cfg.seeds_dir / "equipamentos_ambiente.csv")
        equipamentos = renem.de_seed(seed_equipamentos, lista_renem, mes)

        rais_url = _param(cfg, "rais_url")
        if Path(rais_url).suffix.lower() == ".7z":
            raise RuntimeError("RAIS em .7z requer dependência não disponível; use fonte já extraída")
        arq_rais = fetch_to_raw(cfg, "rais", str(ano_rais), rais_url, Path(rais_url).name or "rais.csv")
        bruto_rais = _csv(arq_rais.path)
        bruto_rais = bruto_rais.loc[bruto_rais[rais.COL_MUNICIPIO].astype(str).str.startswith(cfg.cod_uf)].copy()
        write_parquet(bruto_rais, bronze_path(cfg, "rais", f"vinculos-{cfg.cod_uf}-{ano_rais}"))
        equipe = _csv(cfg.seeds_dir / "dimensionamento_equipe.csv")
        salarios = rais.salarios(bruto_rais, _cbos(equipe), cfg.cod_uf, ano_rais)

        custos = pd.concat([custo_sinapi, custo_cub], ignore_index=True)
        custos = validate(cfg, CUSTO_OBRA_M2, custos, "custo_obra_m2")
        equipamentos = validate(cfg, EQUIPAMENTO_AMBIENTE, equipamentos, "equipamento_ambiente")
        salarios = validate(cfg, SALARIO_OCUPACAO, salarios, "salario_ocupacao")
        write_parquet(custos, silver_path(cfg, "custo_obra_m2"))
        write_parquet(equipamentos, silver_path(cfg, "equipamento_ambiente"))
        write_parquet(salarios, silver_path(cfg, "salario_ocupacao"))
        _registrar_cobertura(cfg, equipamentos)
        record_run(
            cfg,
            "custos",
            "pass",
            {"mes": mes, "ano_rais": ano_rais, "linhas": [len(custos), len(equipamentos), len(salarios)]},
        )
    except Exception as exc:
        record_run(cfg, "custos", "fail", {"erro": str(exc)})
        raise
