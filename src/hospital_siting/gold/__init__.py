"""Camada gold: build → checagens → carga → verificação de contrato."""

from __future__ import annotations

from sqlalchemy import create_engine

from hospital_siting.core.config import Config
from hospital_siting.core.meta import gravar_execucao, nova_execucao, record_run


def run(cfg: Config) -> None:
    from hospital_siting.gold.build import checks_gold, tabelas_gold
    from hospital_siting.gold.contract import aplicar_ddl, verificar
    from hospital_siting.gold.load import carregar

    try:
        t = tabelas_gold(cfg)
        checks_gold(cfg, t)
        engine = create_engine(cfg.pg_dsn)
        aplicar_ddl(engine)
        divergencias = verificar(engine)  # antes da carga: contrato divergente não chega a tocar nos dados
        if divergencias:
            raise RuntimeError("contrato gold divergente: " + "; ".join(divergencias[:20]))
        execucao = nova_execucao(
            cfg, "gold", "ok", {"data_base": t["_data_base"], "municipios": len(t["dim_municipio"])}
        )
        carregar(cfg, t, engine, execucao)  # o banco já recebe o registro desta execução
        gravar_execucao(cfg, execucao)  # o jsonl só registra "ok" depois do commit
    except Exception as exc:
        record_run(cfg, "gold", "fail", {"erro": str(exc)})
        raise
