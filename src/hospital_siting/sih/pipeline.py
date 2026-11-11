"""Pipeline SIH: raw (DBC) -> bronze (agregado por competência) -> silver `sih_agg`."""

from __future__ import annotations

import json

import duckdb
import pandas as pd

from hospital_siting.core.config import Config
from hospital_siting.core.ids import build_ibge6_map
from hospital_siting.core.meta import record_run, record_validation
from hospital_siting.core.parsing import decompress_dbc, read_dbf
from hospital_siting.core.storage import (
    bronze_path,
    fetch_to_raw,
    read_parquet,
    silver_path,
    write_parquet,
)
from hospital_siting.core.validation import validate
from hospital_siting.schemas.silver import SIH_AGG
from hospital_siting.sih.fetch import competencias, nome_arquivo, url_arquivo
from hospital_siting.sih.transform import agregar_rd

FONTE = "sih"


def _mapa6(cfg: Config) -> dict[str, str]:
    mun = read_parquet(silver_path(cfg, "municipio"))
    return build_ibge6_map(mun["cod_ibge"].astype(str))


def run(cfg: Config) -> None:
    mapa6 = _mapa6(cfg)
    mapa_espec = pd.read_csv(cfg.seeds_dir / "mapa_espec_sih.csv", dtype=str)
    comps = competencias(cfg.sih_competencias, None, cfg.uf)

    parciais: list[str] = []
    descartes = {"residencia_fora_uf": 0, "codigo_invalido": 0}
    for comp in comps:
        parcial = bronze_path(cfg, FONTE, f"agg_{cfg.uf}_{comp}")
        desc_path = parcial.with_suffix(".descartes.json")
        if parcial.exists() and desc_path.exists():
            desc = json.loads(desc_path.read_text(encoding="utf-8"))
        else:
            raw = fetch_to_raw(cfg, FONTE, comp, url_arquivo(cfg.uf, comp), nome_arquivo(cfg.uf, comp))
            dbf = decompress_dbc(raw.path, cfg.data_dir / "bronze" / FONTE / "dbf")
            agg, desc = agregar_rd(read_dbf(dbf), mapa6, mapa_espec, comp)
            write_parquet(agg, parcial)
            desc_path.write_text(json.dumps(desc), encoding="utf-8")
            dbf.unlink(missing_ok=True)  # DBF é grande e reconstruível a partir do raw
        for k in descartes:
            descartes[k] += int(desc.get(k, 0))
        parciais.append(parcial.as_posix())

    destino = silver_path(cfg, "sih_agg")
    lista = ", ".join(f"'{p}'" for p in parciais)
    con = duckdb.connect()
    try:
        con.execute(f"COPY (SELECT * FROM read_parquet([{lista}])) TO '{destino.as_posix()}' (FORMAT PARQUET)")
    finally:
        con.close()

    df = validate(cfg, SIH_AGG, read_parquet(destino), "sih_agg")
    for k, n in descartes.items():
        if n:
            record_validation(cfg, "sih_agg", f"descarte:{k}", "warn", f"{n} AIHs descartadas")
    record_run(cfg, FONTE, "ok", {"competencias": len(comps), "linhas": len(df), **descartes})
