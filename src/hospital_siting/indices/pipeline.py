"""Pipeline de índices e SIGTAP: raw -> bronze -> silver (`indice`, `sigtap_procedimento`)."""

from __future__ import annotations

import io
import json
import zipfile
from pathlib import Path

import pandas as pd

from hospital_siting.core.config import Config
from hospital_siting.core.meta import record_run
from hospital_siting.core.storage import bronze_path, silver_path, write_parquet
from hospital_siting.core.validation import validate
from hospital_siting.indices import fetch, transform
from hospital_siting.schemas import silver as S


def _ler_zip(path: Path) -> tuple[pd.DataFrame, list[str]]:
    with zipfile.ZipFile(path) as z:
        nomes = {n.lower(): n for n in z.namelist()}
        layout = pd.read_csv(io.BytesIO(z.read(nomes["tb_procedimento_layout.txt"])), encoding="latin-1")
        linhas = z.read(nomes["tb_procedimento.txt"]).decode("latin-1").splitlines()
    return layout, [ln for ln in linhas if ln.strip()]


def run(cfg: Config) -> None:
    # IPCA
    f_ipca = fetch.fetch_ipca(cfg)
    rows = json.loads(f_ipca.path.read_text(encoding="utf-8"))
    raw_ipca = pd.DataFrame(rows[1:])
    write_parquet(raw_ipca, bronze_path(cfg, "indices", "ipca_sidra"))
    ipca = transform.ipca(raw_ipca)

    # INCC
    f_incc = fetch.fetch_incc(cfg)
    raw_incc = pd.DataFrame(json.loads(f_incc.path.read_text(encoding="utf-8")))
    write_parquet(raw_incc, bronze_path(cfg, "indices", "incc_sgs"))
    incc = transform.desde_incc(raw_incc, "1995-01")

    indice = validate(cfg, S.INDICE, pd.concat([ipca, incc], ignore_index=True), "indice")
    write_parquet(indice, silver_path(cfg, "indice"))

    # SIGTAP
    comp, f_sig = fetch.fetch_sigtap(cfg)
    layout, linhas = _ler_zip(f_sig.path)
    competencia = f"{comp[:4]}-{comp[4:6]}"
    sig = transform.sigtap(layout, linhas, competencia)
    write_parquet(sig, bronze_path(cfg, "indices", "sigtap_procedimento"))
    sig = validate(cfg, S.SIGTAP_PROCEDIMENTO, sig, "sigtap_procedimento")
    write_parquet(sig, silver_path(cfg, "sigtap_procedimento"))

    record_run(
        cfg,
        "indices",
        "ok",
        {"ipca": len(ipca), "incc": len(incc), "sigtap": len(sig), "sigtap_competencia": competencia},
    )
