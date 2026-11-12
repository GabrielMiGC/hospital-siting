"""API FastAPI do hospital-siting: recebe orçamento e parâmetros e devolve as indicações justificadas.

Rodar localmente:  uv run uvicorn hospital_siting.api.app:app --port 8000
"""

from __future__ import annotations

import logging
import os
import threading
from collections import OrderedDict
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Query
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.staticfiles import StaticFiles

from hospital_siting.api.esquemas import (
    ORCAMENTOS_SUGERIDOS,
    OtimizarEntrada,
    custo_json,
    limites,
    padroes,
    resultado_json,
)
from hospital_siting.produto.custos import ORDEM_PORTES, TIPOS_LEITO, Premissas, custos_portes
from hospital_siting.produto.dados import Gold, carregar_gold, geojson_municipios
from hospital_siting.produto.otimizador import otimizar

log = logging.getLogger("hospital_siting.api")
WEB = Path(__file__).resolve().parents[1] / "web"
CACHE_MAX = 256


def _dsn() -> str:
    if os.environ.get("HS_PG_DSN"):
        return os.environ["HS_PG_DSN"]
    from hospital_siting.core.config import load_config

    return load_config().pg_dsn


def _enriquecer(geojson: dict, gold: Gold) -> dict:
    """Acrescenta população, déficit por tipo e hospitais existentes às propriedades de cada município."""
    mun = gold.municipios.set_index("cod_ibge")
    pos = gold.deficit[gold.deficit["deficit"] > 0].pivot_table(
        index="cod_ibge", columns="tipo_leito", values="deficit", aggfunc="sum", fill_value=0.0
    )
    est = gold.estabelecimentos.groupby("cod_ibge").agg(hospitais=("cnes", "size"), leitos_sus=("leitos_sus", "sum"))
    for f in geojson["features"]:
        cod = f["properties"]["cod_ibge"]
        deficit = {t: round(float(pos.at[cod, t]), 2) for t in TIPOS_LEITO if cod in pos.index and t in pos.columns}
        deficit = {t: v for t, v in deficit.items() if v > 0}
        f["properties"].update(
            populacao=int(mun.at[cod, "populacao"]) if cod in mun.index else None,
            deficit=deficit,
            deficit_total=round(sum(deficit.values()), 2),
            hospitais=int(est.at[cod, "hospitais"]) if cod in est.index else 0,
            leitos_sus=int(est.at[cod, "leitos_sus"]) if cod in est.index else 0,
            regiao_saude=mun.at[cod, "nome_regiao_saude"] if "nome_regiao_saude" in mun.columns else None,
        )
    return geojson


class _Estado:
    def __init__(self) -> None:
        self.gold: Gold | None = None
        self.geojson: dict | None = None
        self.cache: OrderedDict[str, dict] = OrderedDict()
        self.trava = threading.Lock()  # um MILP por vez: o servidor tem poucos núcleos

    def resolver(self, entrada: OtimizarEntrada) -> dict:
        chave = entrada.model_dump_json()
        if chave in self.cache:
            self.cache.move_to_end(chave)
            return self.cache[chave] | {"cache": True}
        with self.trava:
            if chave not in self.cache:
                res = resultado_json(otimizar(self.gold, entrada.parametros()))
                self.cache[chave] = res
                while len(self.cache) > CACHE_MAX:
                    self.cache.popitem(last=False)
        return self.cache[chave] | {"cache": False}

    def precalcular(self) -> None:
        for orc in ORCAMENTOS_SUGERIDOS:
            try:
                self.resolver(OtimizarEntrada(orcamento=orc))
            except Exception:  # noqa: BLE001 — pré-cálculo é otimização, não pode derrubar a API
                log.exception("pré-cálculo falhou para orçamento %s", orc)
        log.info("pré-cálculo concluído: %d cenários", len(self.cache))


def criar_app(gold: Gold | None = None, geojson: dict | None = None, precalcular: bool = False) -> FastAPI:
    estado = _Estado()

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        dsn = None
        if gold is None or geojson is None:
            dsn = _dsn()
        estado.gold = gold if gold is not None else carregar_gold(dsn)
        bruto = geojson if geojson is not None else geojson_municipios(dsn)
        estado.geojson = _enriquecer(bruto, estado.gold)
        if precalcular:
            threading.Thread(target=estado.precalcular, daemon=True, name="precalculo").start()
        yield

    app = FastAPI(
        title="hospital-siting",
        description="Onde construir hospitais gerais (H1–H4) na Bahia dado um orçamento. Apoio à decisão.",
        version="0.2.0",
        lifespan=lifespan,
    )
    app.add_middleware(GZipMiddleware, minimum_size=1000)

    @app.get("/api/saude")
    def saude() -> dict:
        return {"status": "ok", "data_base": estado.gold.data_base, "municipios": len(estado.gold.municipios)}

    @app.get("/api/parametros")
    def parametros() -> dict:
        return {
            "padroes": padroes(),
            "limites": limites(),
            "orcamentos_sugeridos": ORCAMENTOS_SUGERIDOS,
            "portes": list(ORDEM_PORTES),
            "data_base": estado.gold.data_base,
        }

    @app.get("/api/portes")
    def portes(
        fator_hospitalar: float = Query(2.5, ge=1.0, le=5.0),
        fator_pessoal_nao_normatizado: float = Query(1.0, ge=0, le=3.0),
        ocupacao: float = Query(0.8, ge=0.3, le=1.0),
    ) -> list[dict]:
        p = Premissas(
            fator_hospitalar=fator_hospitalar,
            fator_pessoal_nao_normatizado=fator_pessoal_nao_normatizado,
            ocupacao=ocupacao,
        )
        return [custo_json(c) for c in custos_portes(estado.gold, p).values()]

    @app.get("/api/municipios")
    def municipios() -> dict:
        return estado.geojson

    @app.post("/api/otimizar")
    def otimizar_rota(entrada: OtimizarEntrada) -> dict:
        return estado.resolver(entrada)

    if WEB.exists():
        app.mount("/", StaticFiles(directory=WEB, html=True), name="web")
    return app


def _app_padrao() -> FastAPI:
    return criar_app(precalcular=os.environ.get("HS_PRECALCULAR", "1") != "0")


app = _app_padrao()
