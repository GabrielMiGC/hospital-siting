"""Validação com Pandera + registro do resultado em data/meta/validacoes.jsonl."""

from __future__ import annotations

import pandas as pd
import pandera.errors
import pandera.pandas as pa

from hospital_siting.core.config import Config
from hospital_siting.core.meta import record_validation


def validate(cfg: Config, schema: pa.DataFrameSchema, df: pd.DataFrame, dataset: str) -> pd.DataFrame:
    try:
        out = schema.validate(df, lazy=True)
    except pandera.errors.SchemaErrors as e:
        casos = e.failure_cases.head(20).to_string(index=False)
        record_validation(cfg, dataset, f"schema:{schema.name or dataset}", "fail", casos)
        raise
    record_validation(cfg, dataset, f"schema:{schema.name or dataset}", "pass", f"{len(out)} linhas")
    return out


def warn_if(cfg: Config, cond: bool, dataset: str, check: str, detalhe: str) -> None:
    if cond:
        record_validation(cfg, dataset, check, "warn", detalhe)
