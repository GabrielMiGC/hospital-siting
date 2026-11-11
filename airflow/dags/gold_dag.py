"""DAG gold: espera as DAGs dos outros 7 domínios e então executa a camada gold."""

from _common import DEFAULT_ARGS, START_DATE, TAG, task_run, ultima_execucao
from airflow.sensors.external_task import ExternalTaskSensor

from airflow import DAG

DOMINIOS = ["ibge", "cnes", "sih", "siconfi", "indices", "custos", "rotas"]

with DAG(
    dag_id="gold",
    schedule=None,
    catchup=False,
    start_date=START_DATE,
    default_args=DEFAULT_ARGS,
    tags=[TAG],
) as dag:
    esperas = [
        ExternalTaskSensor(
            task_id=f"espera_{d}",
            external_dag_id=d,
            external_task_id=None,
            execution_date_fn=ultima_execucao(d),
            mode="reschedule",
            poke_interval=60,
            timeout=6 * 3600,
        )
        for d in DOMINIOS
    ]
    esperas >> task_run("gold")
