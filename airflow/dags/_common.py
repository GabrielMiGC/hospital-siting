"""Utilitários compartilhados pelas DAGs: cada DAG é fina e só delega ao `run(cfg)` do domínio."""

from __future__ import annotations

import os
import subprocess
from datetime import datetime

from airflow.models import Variable
from airflow.operators.python import PythonOperator

TAG = "hospital_siting"
DEFAULT_ARGS = {"owner": "hospital_siting", "retries": 0}
START_DATE = datetime(2024, 1, 1)

DOMINIOS = ["ibge", "cnes", "sih", "siconfi", "indices", "custos", "rotas", "gold"]
# venv do projeto (ver docker/airflow/Dockerfile); o CLI executa `pipeline.run(load_config(uf))`.
HS_PYTHON = os.environ.get("HS_PYTHON", "/opt/hs-venv/bin/python")


def _executar(dominio: str) -> None:
    uf = Variable.get("uf", "BA")
    subprocess.run(  # noqa: S603
        [HS_PYTHON, "-m", "hospital_siting.cli", "run", dominio, "--uf", uf],
        check=True,
    )


def task_run(dominio: str) -> PythonOperator:
    """Task que roda `run(load_config(uf=Variable 'uf'))` do domínio (use dentro de `with DAG`)."""
    if dominio not in DOMINIOS:
        raise ValueError(f"domínio desconhecido: {dominio}")
    return PythonOperator(task_id=f"run_{dominio}", python_callable=_executar, op_args=[dominio])


def ultima_execucao(dag_id: str):
    """Retorna `execution_date_fn` que aponta para a última execução de `dag_id`."""

    def _fn(logical_date, **_):
        from airflow.models import DagRun

        runs = DagRun.find(dag_id=dag_id)
        return max((r.execution_date for r in runs), default=logical_date)

    return _fn
