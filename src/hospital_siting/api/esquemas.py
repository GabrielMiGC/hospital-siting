"""Entrada da API (validação dos sliders) e conversão do resultado para JSON."""

from __future__ import annotations

import dataclasses
import math
from typing import Literal

from pydantic import BaseModel, Field, model_validator

from hospital_siting.produto.custos import CustoPorte, Premissas
from hospital_siting.produto.otimizador import Parametros

Porte = Literal["H1", "H2", "H3", "H4"]

# Valores do slider de orçamento (o cache pré-calcula estes com os parâmetros padrão).
ORCAMENTOS_SUGERIDOS = [
    1e8, 1.5e8, 2e8, 3e8, 4e8, 5e8, 7.5e8, 1e9, 1.25e9, 1.5e9, 2e9, 2.5e9, 3e9, 4e9, 5e9,
]  # fmt: skip


class OtimizarEntrada(BaseModel):
    orcamento: float = Field(ge=1e7, le=2e10, description="R$ na data-base da gold")
    portes: list[Porte] = Field(default=["H1", "H2", "H3", "H4"], min_length=1)
    pct_receita: float = Field(0.20, ge=0, le=0.5, description="fração da receita corrente municipal")
    t_full: float = Field(30, ge=0, le=180, description="min com cobertura de 100%")
    t_max: float = Field(180, ge=15, le=360, description="min em que a cobertura chega a zero")
    fator_osrm: float = Field(1.0, ge=1.0, le=2.0)
    ocupacao: float = Field(0.80, ge=0.3, le=1.0)
    peso_concentracao: float = Field(1.0, ge=0, le=20)
    t_conc: float = Field(60, ge=10, le=180)
    aporte_por_leito: float = Field(0.0, ge=0, le=1e6)
    pop_min_candidato: int = Field(20_000, ge=5_000, le=500_000)
    fator_hospitalar: float = Field(2.5, ge=1.0, le=5.0)
    fator_pessoal_nao_normatizado: float = Field(1.0, ge=0, le=3.0)

    @model_validator(mode="after")
    def _tempos(self) -> OtimizarEntrada:
        if self.t_max <= self.t_full:
            raise ValueError("t_max precisa ser maior que t_full")
        return self

    def premissas(self) -> Premissas:
        return Premissas(
            fator_hospitalar=self.fator_hospitalar,
            fator_pessoal_nao_normatizado=self.fator_pessoal_nao_normatizado,
            ocupacao=self.ocupacao,
        )

    def parametros(self) -> Parametros:
        return Parametros(
            orcamento=self.orcamento,
            portes=sorted(set(self.portes)),
            pct_receita=self.pct_receita,
            t_full=self.t_full,
            t_max=self.t_max,
            fator_osrm=self.fator_osrm,
            peso_concentracao=self.peso_concentracao,
            t_conc=self.t_conc,
            aporte_por_leito=self.aporte_por_leito,
            pop_min_candidato=self.pop_min_candidato,
            premissas=self.premissas(),
        )


def limites() -> dict:
    out = {}
    for nome, campo in OtimizarEntrada.model_fields.items():
        meta = {type(m).__name__: m for m in campo.metadata}
        lim = {}
        if "Ge" in meta:
            lim["min"] = meta["Ge"].ge
        if "Le" in meta:
            lim["max"] = meta["Le"].le
        if lim:
            out[nome] = lim
    return out


def padroes() -> dict:
    return {
        n: c.default for n, c in OtimizarEntrada.model_fields.items() if n != "orcamento" and c.default is not None
    }


def _limpo(v):
    if isinstance(v, float):
        return None if not math.isfinite(v) else round(v, 4)
    if isinstance(v, dict):
        return {k: _limpo(x) for k, x in v.items()}
    if isinstance(v, list | tuple):
        return [_limpo(x) for x in v]
    return v


def custo_json(c: CustoPorte) -> dict:
    d = dataclasses.asdict(c)
    d["custo_leito_ano"] = c.custo_leito_ano
    return _limpo(d)


def resultado_json(res) -> dict:
    d = {
        f.name: getattr(res, f.name)
        for f in dataclasses.fields(res)
        if f.name not in {"hospitais", "descartados", "custos_portes"}
    }
    d["hospitais"] = []
    for h in res.hospitais:
        hj = {f.name: getattr(h, f.name) for f in dataclasses.fields(h) if f.name not in {"custo", "viabilidade"}}
        hj["municipios"] = [dataclasses.asdict(m) for m in h.municipios]
        hj["custo"] = custo_json(h.custo)
        hj["viabilidade"] = dataclasses.asdict(h.viabilidade) | {"cobertura_pct": h.viabilidade.cobertura_pct}
        d["hospitais"].append(hj)
    d["descartados"] = [dataclasses.asdict(x) for x in res.descartados]
    return _limpo(d)
