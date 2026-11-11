"""Pipeline bronze/silver para custos de obra, equipamentos e salários."""

from __future__ import annotations

import json
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


SINAPI_SIDRA = "https://apisidra.ibge.gov.br/values/t/2296/n3/{cod_uf}/v/48/p/last%2024"


def _sinapi(cfg: Config) -> pd.DataFrame:
    url = SINAPI_SIDRA.format(cod_uf=cfg.cod_uf)
    arq = fetch_to_raw(cfg, "sinapi", "sidra2296", url, "sidra_2296.json", max_idade_dias=30)
    linhas = pd.DataFrame(json.loads(arq.path.read_text(encoding="utf-8"))[1:])
    write_parquet(linhas, bronze_path(cfg, "sinapi", "sidra2296"))
    return sinapi.de_sidra(linhas)


def _cub(cfg: Config, mes: str) -> pd.DataFrame:
    seed = cfg.seeds_dir / "cub_ba.csv"
    if not seed.exists():
        warn_if(cfg, True, "custo_obra_m2", "cub_ausente", "seeds/cub_ba.csv não existe; só SINAPI")
        return pd.DataFrame(columns=["fonte", "padrao", "valor_m2", "mes"])
    warn_if(cfg, True, "custo_obra_m2", "cub_seed_manual", "CUB transcrito de fonte do Sinduscon")
    return cub.custo_m2(_csv(seed), mes)


def _rais(cfg: Config, cbos: list[str]) -> tuple[pd.DataFrame, int]:
    ano = int(_param(cfg, "rais_ano"))
    url = _param(cfg, "rais_url")
    bronze = bronze_path(cfg, "rais", f"vinculos-{cfg.cod_uf}-{ano}")
    if bronze.exists():
        return pd.read_parquet(bronze), ano
    arq = fetch_to_raw(cfg, "rais", str(ano), url, Path(url).name)
    destino = arq.path.parent / "extraido"
    if not any(x.is_file() for x in destino.glob("*")):
        import py7zr

        destino.mkdir(parents=True, exist_ok=True)
        with py7zr.SevenZipFile(arq.path, "r") as z:
            z.extractall(destino)
    partes = [rais.ler_vinculos(txt, cfg.cod_uf, cbos) for txt in sorted(destino.rglob("*")) if txt.is_file()]
    vinc = pd.concat(partes, ignore_index=True)
    write_parquet(vinc, bronze)
    for txt in [
        x for x in destino.rglob("*") if x.is_file()
    ]:  # o .7z original fica em raw; o texto extraído (GBs) é descartável
        txt.unlink()
    return vinc, ano


def run(cfg: Config) -> None:
    """Baixa as fontes reais e materializa as três silvers do domínio."""
    try:
        custo_sinapi = _sinapi(cfg)
        mes = str(custo_sinapi["mes"].max())
        custo_cub = _cub(cfg, mes)

        renem_url = str(cfg.params.get("renem_url", RENEM_URL))
        arq_renem = fetch_to_raw(cfg, "renem", "atual", renem_url, "lista-renem.xlsx", max_idade_dias=30)
        aba = pd.ExcelFile(arq_renem.path).sheet_names[0]
        mes_renem = renem.mes_referencia(aba) or mes
        lista_renem = renem.parse_lista(pd.read_excel(arq_renem.path, header=None))
        write_parquet(lista_renem, bronze_path(cfg, "renem", "lista"))
        equipamentos = renem.de_seed(_csv(cfg.seeds_dir / "equipamentos_ambiente.csv"), lista_renem, mes_renem)

        equipe = _csv(cfg.seeds_dir / "dimensionamento_equipe.csv")
        vinculos, ano_rais = _rais(cfg, _cbos(equipe))
        salarios = rais.salarios(vinculos, _cbos(equipe), cfg.cod_uf, ano_rais)

        custos = pd.concat([d for d in (custo_sinapi, custo_cub) if not d.empty], ignore_index=True)
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
            "ok",
            {"mes": mes, "ano_rais": ano_rais, "linhas": [len(custos), len(equipamentos), len(salarios)]},
        )
    except Exception as exc:
        record_run(cfg, "custos", "fail", {"erro": str(exc)})
        raise
