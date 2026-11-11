"""Pipeline SICONFI: DCA -> bronze (itens) -> silver `receita_municipal`."""

from __future__ import annotations

import httpx
import pandas as pd

from hospital_siting.core.config import Config
from hospital_siting.core.meta import record_run
from hospital_siting.core.storage import USER_AGENT, bronze_path, silver_path, write_parquet
from hospital_siting.core.validation import validate, warn_if
from hospital_siting.schemas.silver import RECEITA_MUNICIPAL
from hospital_siting.siconfi.fetch import FONTE, codigos_municipios, dca, ultimo_exercicio_fechado
from hospital_siting.siconfi.transform import receita_corrente


def run(cfg: Config) -> None:
    with httpx.Client(headers={"User-Agent": USER_AGENT}, timeout=60.0, follow_redirects=True) as client:
        exercicio = ultimo_exercicio_fechado(client, cfg)
        itens = dca(cfg, exercicio, client)
    df_itens = pd.DataFrame(itens)
    write_parquet(df_itens, bronze_path(cfg, FONTE, f"dca_{exercicio}"))
    out = validate(cfg, RECEITA_MUNICIPAL, receita_corrente(df_itens, cfg.cod_uf), "receita_municipal")
    sem = sorted(set(codigos_municipios(cfg)) - set(out["cod_ibge"]))
    warn_if(cfg, bool(sem), "receita_municipal", "municipios_sem_receita", f"{len(sem)}: {', '.join(sem)}")
    write_parquet(out, silver_path(cfg, "receita_municipal"))
    record_run(cfg, "siconfi", "ok", {"exercicio": exercicio, "municipios": len(out), "sem_receita": sem})
