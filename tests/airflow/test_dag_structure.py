"""Análise estática das DAGs do Airflow (sem importar airflow)."""

from pathlib import Path

ROOT = Path(__file__).parents[2]
DAGS = ROOT / "airflow" / "dags"

DOMINIOS = ["ibge", "cnes", "sih", "siconfi", "indices", "custos", "rotas", "gold"]
OUTROS_DOMINIOS = [d for d in DOMINIOS if d != "gold"]


def _dag_files():
    files = sorted(DAGS.glob("*_dag.py"))
    assert files, f"nenhuma DAG encontrada em {DAGS}"
    return files


def test_every_domain_has_dag():
    names = {p.stem for p in DAGS.glob("*_dag.py")}
    assert names == {f"{d}_dag" for d in DOMINIOS}


def test_dags_call_pipeline_run_only():
    for p in _dag_files():
        src = p.read_text(encoding="utf-8")
        assert "task_run(" in src and "import pandas" not in src, p.name  # DAGs finos


def test_every_dag_has_manual_schedule_and_no_catchup():
    for p in _dag_files():
        src = p.read_text(encoding="utf-8")
        assert "schedule=None" in src, p.name
        assert "catchup=False" in src, p.name


def test_gold_dag_waits_for_other_domains():
    gold = DAGS / "gold_dag.py"
    assert gold.exists(), f"{gold} não existe"
    src = gold.read_text(encoding="utf-8")
    assert "ExternalTaskSensor" in src or "TriggerDagRunOperator" in src
    for d in OUTROS_DOMINIOS:
        assert d in src, f"gold_dag.py não referencia o domínio {d!r}"
