"""Registro de linhagem: validações e execuções (jsonl em data/meta, carregados no schema meta pela gold)."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any, Literal

from hospital_siting.core.config import Config

Status = Literal["pass", "warn", "fail"]


def _append(cfg: Config, nome: str, registro: dict[str, Any]) -> None:
    p = cfg.data_dir / "meta" / f"{nome}.jsonl"
    p.parent.mkdir(parents=True, exist_ok=True)
    registro = {"em": datetime.now(UTC).isoformat(), "uf": cfg.uf, **registro}
    with p.open("a", encoding="utf-8") as f:
        f.write(json.dumps(registro, ensure_ascii=False, default=str) + "\n")


def record_validation(cfg: Config, dataset: str, check: str, status: Status, detalhe: str = "") -> None:
    _append(cfg, "validacoes", {"dataset": dataset, "check": check, "status": status, "detalhe": detalhe})


def record_run(cfg: Config, dominio: str, status: str, extra: dict[str, Any]) -> None:
    _append(cfg, "execucoes", {"dominio": dominio, "status": status, "extra": extra})
