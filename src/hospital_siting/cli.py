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


if __name__ == "__main__":
    app()
