"""Contrato da gold: aplica o DDL versionado e compara o banco com ele."""

from __future__ import annotations

from sqlalchemy import Engine, text

from hospital_siting.core.config import REPO_ROOT

DDL_PATH = REPO_ROOT / "contracts" / "gold_schema.sql"
_COLS = """
select table_name, column_name, data_type, udt_name, is_nullable
from information_schema.columns where table_schema = :s order by table_name, column_name
"""
_GEOM = "select f_table_name, f_geometry_column, srid, type from geometry_columns where f_table_schema = :s"


def _ddl() -> str:
    return DDL_PATH.read_text(encoding="utf-8")


def aplicar_ddl(engine: Engine) -> None:
    # gold e meta são regenerados por inteiro a cada carga: recriar garante o DDL da versão atual
    with engine.begin() as c:
        c.exec_driver_sql("DROP SCHEMA IF EXISTS gold CASCADE; DROP SCHEMA IF EXISTS meta CASCADE")
        c.exec_driver_sql(_ddl())


def _snapshot(c, schema: str) -> set[tuple]:
    cols = {tuple(r) for r in c.execute(text(_COLS), {"s": schema})}
    geoms = {("geom",) + tuple(r) for r in c.execute(text(_GEOM), {"s": schema})}
    return cols | geoms


def verificar(engine: Engine) -> list[str]:
    """Cria o DDL num schema temporário e compara colunas/tipos/geometrias com gold e meta. Vazio = ok."""
    divergencias: list[str] = []
    ddl = _ddl()
    with engine.begin() as c:
        for schema in ("gold", "meta"):
            tmp = f"_contrato_{schema}"
            c.exec_driver_sql(f"DROP SCHEMA IF EXISTS {tmp} CASCADE")
            c.exec_driver_sql(f"CREATE SCHEMA {tmp}")
            corpo = "\n".join(
                ln.split("--")[0]
                for ln in ddl.splitlines()
                if not ln.strip().upper().startswith(("CREATE SCHEMA", "CREATE EXTENSION", "--"))
            )
            c.exec_driver_sql(_so_schema(corpo, schema, tmp))
            esperado = _snapshot(c, tmp)
            real = _snapshot(c, schema)
            for item in sorted(esperado - real, key=str):
                divergencias.append(f"{schema}: falta/difere {item}")
            for item in sorted(real - esperado, key=str):
                divergencias.append(f"{schema}: não previsto {item}")
            c.exec_driver_sql(f"DROP SCHEMA {tmp} CASCADE")
    return divergencias


def _so_schema(corpo: str, schema: str, tmp: str) -> str:
    """Mantém só os CREATE TABLE do schema pedido, reescritos para o schema temporário."""
    blocos = [b for b in corpo.split(";") if f"{schema}." in b]
    return ";\n".join(b.replace(f"{schema}.", f"{tmp}.") for b in blocos) + ";"
