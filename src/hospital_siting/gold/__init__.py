"""Camada gold: build → checagens → carga → verificação de contrato."""

from __future__ import annotations

from sqlalchemy import create_engine

from hospital_siting.core.config import Config
from hospital_siting.core.meta import record_run


def run(cfg: Config) -> None:
    from hospital_siting.gold.build import checks_gold, tabelas_gold
    from hospital_siting.gold.contract import aplicar_ddl, verificar
    from hospital_siting.gold.load import carregar

    t = tabelas_gold(cfg)
    checks_gold(cfg, t)
    engine = create_engine(cfg.pg_dsn)
    aplicar_ddl(engine)
    carregar(cfg, t, engine)
    divergencias = verificar(engine)
    if divergencias:
        raise RuntimeError("contrato gold divergente: " + "; ".join(divergencias[:20]))
    record_run(cfg, "gold", "ok", {"data_base": t["_data_base"], "municipios": len(t["dim_municipio"])})
