"""Pipeline raw → bronze → silver do CNES."""

from __future__ import annotations

import re

import httpx
import pandas as pd

from hospital_siting.cnes.fetch import FTP_BASE, FTP_HOST, latest_competencia
from hospital_siting.cnes.transform import estabelecimentos, leitos
from hospital_siting.core.config import Config
from hospital_siting.core.ids import build_ibge6_map
from hospital_siting.core.meta import record_run
from hospital_siting.core.parsing import decompress_dbc, read_dbf
from hospital_siting.core.storage import (
    TIMEOUT,
    USER_AGENT,
    bronze_path,
    fetch_to_raw,
    read_parquet,
    silver_path,
    write_parquet,
)
from hospital_siting.core.validation import validate
from hospital_siting.schemas.silver import CNES_ESTABELECIMENTO, CNES_LEITOS


def _competencia(cfg: Config, client: httpx.Client) -> str:
    if re.fullmatch(r"\d{4}-\d{2}", cfg.data_base):
        return cfg.data_base
    return latest_competencia(client, cfg.uf)


def _arquivo_url(sigla: str, uf: str, competencia: str) -> tuple[str, str]:
    aamm = competencia[2:4] + competencia[5:7]
    filename = f"{sigla}{uf}{aamm}.dbc"
    return filename, f"ftp://{FTP_HOST}{FTP_BASE}/{sigla}/{filename}"


def run(cfg: Config) -> None:
    """Baixa a competência, persiste bronze e valida as duas silvers do CNES."""
    competencia: str | None = None
    try:
        with httpx.Client(headers={"User-Agent": USER_AGENT}, timeout=TIMEOUT, follow_redirects=True) as client:
            competencia = _competencia(cfg, client)
            brutos: dict[str, pd.DataFrame] = {}
            for sigla in ("ST", "LT"):
                filename, url = _arquivo_url(sigla, cfg.uf, competencia)
                raw = fetch_to_raw(cfg, "cnes", competencia, url, filename, client)
                dbf_dir = cfg.data_dir / "bronze" / "cnes" / "dbf" / competencia
                frame = read_dbf(decompress_dbc(raw.path, dbf_dir))
                brutos[sigla] = frame
                write_parquet(frame, bronze_path(cfg, "cnes", f"{sigla.lower()}_{competencia}"))

        municipios = read_parquet(silver_path(cfg, "municipio"))
        mapa6 = build_ibge6_map(municipios["cod_ibge"].astype("string"))
        mapa_leitos = pd.read_csv(cfg.seeds_dir / "mapa_leitos_cnes.csv", dtype={"cod_leito": "string"})

        silver_leitos = leitos(brutos["LT"], mapa6, mapa_leitos, competencia)
        silver_estabelecimentos = estabelecimentos(brutos["ST"], mapa6, competencia, leitos=silver_leitos)
        silver_leitos = validate(cfg, CNES_LEITOS, silver_leitos, "cnes_leitos")
        silver_estabelecimentos = validate(
            cfg,
            CNES_ESTABELECIMENTO,
            silver_estabelecimentos,
            "cnes_estabelecimento",
        )
        write_parquet(silver_leitos, silver_path(cfg, "cnes_leitos"))
        write_parquet(silver_estabelecimentos, silver_path(cfg, "cnes_estabelecimento"))
        record_run(
            cfg,
            "cnes",
            "pass",
            {
                "competencia": competencia,
                "cnes_estabelecimento": len(silver_estabelecimentos),
                "cnes_leitos": len(silver_leitos),
            },
        )
    except Exception as exc:
        record_run(cfg, "cnes", "fail", {"competencia": competencia, "erro": str(exc)})
        raise
