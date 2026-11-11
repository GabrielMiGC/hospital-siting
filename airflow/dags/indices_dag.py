"""DAG do domínio indices: executa `pipeline.run(cfg)`."""

from _common import DEFAULT_ARGS, START_DATE, TAG, task_run

from airflow import DAG

with DAG(
    dag_id="indices",
    schedule=None,
    catchup=False,
    start_date=START_DATE,
    default_args=DEFAULT_ARGS,
    tags=[TAG],
) as dag:
    task_run("indices")
