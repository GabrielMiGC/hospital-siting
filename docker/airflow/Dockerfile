FROM apache/airflow:2.10.5-python3.12

USER root
# docker CLI + compose plugin (a DAG rotas sobe o OSRM via socket do host)
COPY --from=docker:27-cli /usr/local/bin/docker /usr/local/bin/docker
COPY --from=docker:27-cli /usr/local/libexec/docker/cli-plugins/docker-compose /usr/local/libexec/docker/cli-plugins/docker-compose
RUN apt-get update && apt-get install -y --no-install-recommends postgresql-client \
    && rm -rf /var/lib/apt/lists/* \
    && mkdir -p /opt/hs-venv /opt/hospital_siting \
    && chown airflow:root /opt/hs-venv /opt/hospital_siting

USER airflow
# O pacote exige SQLAlchemy>=2 e pandas>=2.2, incompatíveis com o Airflow 2.10 (SQLAlchemy<2).
# Por isso vive num venv próprio (/opt/hs-venv), instalado em modo editável; em runtime o
# repositório é montado sobre /opt/hospital_siting e as tasks chamam o CLI desse venv.
COPY --chown=airflow:root pyproject.toml README.md /opt/hospital_siting/
COPY --chown=airflow:root src /opt/hospital_siting/src
RUN python -m venv /opt/hs-venv && /opt/hs-venv/bin/pip install --no-cache-dir -e /opt/hospital_siting
