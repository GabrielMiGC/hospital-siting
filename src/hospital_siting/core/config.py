"""Carregamento da configuração do pipeline (config/settings.yaml + variáveis de ambiente)."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

REPO_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_SETTINGS = REPO_ROOT / "config" / "settings.yaml"


@dataclass(frozen=True)
class Config:
    uf: str
    cod_uf: str
    n_municipios: int
    data_base: str
    data_dir: Path
    seeds_dir: Path
    pg_dsn: str
    params: dict[str, Any] = field(default_factory=dict)
    sih_competencias: int = 36


def _resolve(p: str | Path) -> Path:
    p = Path(p)
    return p if p.is_absolute() else REPO_ROOT / p


def load_config(path: Path | None = None, uf: str | None = None) -> Config:
    raw = yaml.safe_load((path or DEFAULT_SETTINGS).read_text(encoding="utf-8"))
    uf_ativa = (uf or raw["uf"]).upper()
    info = raw["ufs"][uf_ativa]  # KeyError para UF não configurada
    data_dir = Path(os.environ["HS_DATA_DIR"]) if os.environ.get("HS_DATA_DIR") else _resolve(raw["data_dir"])
    return Config(
        uf=uf_ativa,
        cod_uf=str(info["cod_uf"]),
        n_municipios=int(info["n_municipios"]),
        data_base=str(raw.get("data_base", "auto")),
        data_dir=data_dir,
        seeds_dir=_resolve(raw.get("seeds_dir", "seeds")),
        pg_dsn=os.environ.get("HS_PG_DSN") or raw["pg_dsn"],
        params=dict(raw.get("params", {})),
        sih_competencias=int(raw.get("sih_competencias", 36)),
    )
