"""CLI: `python -m hospital_siting.cli run <dominio> [--uf BA]`."""

from __future__ import annotations

import importlib
from enum import StrEnum

import typer

from hospital_siting.core.config import load_config

app = typer.Typer(no_args_is_help=True, add_completion=False)


class Dominio(StrEnum):
    ibge = "ibge"
    cnes = "cnes"
    sih = "sih"
    siconfi = "siconfi"
    indices = "indices"
    custos = "custos"
    rotas = "rotas"
    gold = "gold"
    all = "all"


MODULOS = {
    "ibge": "hospital_siting.ibge.pipeline",
    "cnes": "hospital_siting.cnes.pipeline",
    "sih": "hospital_siting.sih.pipeline",
    "siconfi": "hospital_siting.siconfi.pipeline",
    "indices": "hospital_siting.indices.pipeline",
    "custos": "hospital_siting.custos.pipeline",
    "rotas": "hospital_siting.rotas.pipeline",
    "gold": "hospital_siting.gold",
}
# ibge primeiro (fornece a lista de municípios), gold por último
ORDEM_ALL = ["ibge", "indices", "cnes", "sih", "siconfi", "custos", "rotas", "gold"]


@app.callback()
def main() -> None:
    """Pipeline de dados do hospital-siting."""


@app.command()
def run(dominio: Dominio, uf: str | None = typer.Option(None, help="UF alvo (padrão: config)")) -> None:
    """Executa o pipeline de um domínio (ou todos)."""
    cfg = load_config(uf=uf)
    alvos = ORDEM_ALL if dominio == Dominio.all else [dominio.value]
    for nome in alvos:
        typer.echo(f"[{cfg.uf}] executando {nome}...")
        importlib.import_module(MODULOS[nome]).run(cfg)


@app.command()
def docs(
    orcamento: float = typer.Option(1e9, help="Orçamento do exemplo resolvido (R$)"),
    uf: str | None = typer.Option(None, help="UF alvo (padrão: config)"),
) -> None:
    """Gera docs/como-funciona/index.html, com a seção da Fase 2 calculada a partir da gold."""
    from hospital_siting.core.config import REPO_ROOT
    from hospital_siting.docs_page import render

    cfg = load_config(uf=uf)
    fase2 = None
    try:
        from hospital_siting.produto.custos import Premissas, custos_portes
        from hospital_siting.produto.dados import carregar_gold
        from hospital_siting.produto.otimizador import Parametros, otimizar
        from hospital_siting.produto.pagina import secao_fase2

        gold = carregar_gold(cfg.pg_dsn)
        fase2 = secao_fase2(custos_portes(gold, Premissas()), otimizar(gold, Parametros(orcamento=orcamento)))
    except Exception as e:  # noqa: BLE001 — sem banco, a página sai com o texto padrão
        typer.echo(f"gold indisponível ({e.__class__.__name__}); seção da Fase 2 com texto padrão")
    out = render(cfg, REPO_ROOT / "docs" / "como-funciona" / "index.html", fase2_html=fase2)
    typer.echo(f"página gerada em {out}")


if __name__ == "__main__":
    app()
