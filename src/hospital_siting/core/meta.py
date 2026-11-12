"""Registro de linhagem: validações e execuções (jsonl em data/meta, carregados no schema meta pela gold)."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any, Literal

from hospital_siting.core.config import Config

Status = Literal["pass", "warn", "fail"]


def _registro(cfg: Config, campos: dict[str, Any]) -> dict[str, Any]:
    return {"em": datetime.now(UTC).isoformat(), "uf": cfg.uf, **campos}


def _append(cfg: Config, nome: str, registro: dict[str, Any], *, pronto: bool = False) -> None:
    p = cfg.data_dir / "meta" / f"{nome}.jsonl"
    p.parent.mkdir(parents=True, exist_ok=True)
    registro = registro if pronto else _registro(cfg, registro)
    with p.open("a", encoding="utf-8") as f:
        f.write(json.dumps(registro, ensure_ascii=False, default=str) + "\n")


def record_validation(cfg: Config, dataset: str, check: str, status: Status, detalhe: str = "") -> None:
    _append(cfg, "validacoes", {"dataset": dataset, "check": check, "status": status, "detalhe": detalhe})


def nova_execucao(cfg: Config, dominio: str, status: str, extra: dict[str, Any]) -> dict[str, Any]:
    """Monta o registro de execução sem gravá-lo (a gold o carrega no banco antes de gravar no jsonl)."""
    return _registro(cfg, {"dominio": dominio, "status": status, "extra": extra})


def record_run(cfg: Config, dominio: str, status: str, extra: dict[str, Any]) -> None:
    gravar_execucao(cfg, nova_execucao(cfg, dominio, status, extra))


def gravar_execucao(cfg: Config, registro: dict[str, Any]) -> None:
    _append(cfg, "execucoes", registro, pronto=True)
