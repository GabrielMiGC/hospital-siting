"""Downloads: IPCA (SIDRA), INCC (SGS/BCB) e SIGTAP (FTP DATASUS) para data/raw."""

from __future__ import annotations

import re
import urllib.request

from hospital_siting.core.config import Config
from hospital_siting.core.storage import USER_AGENT, RawFile, fetch_to_raw

SIDRA_URL = "https://apisidra.ibge.gov.br/values/t/1737/n1/all/v/2266/p/all"
SGS_INCC_URL = "https://api.bcb.gov.br/dados/serie/bcdata.sgs.192/dados?formato=json"
SIGTAP_FTP_DIR = "ftp://ftp2.datasus.gov.br/pub/sistemas/tup/downloads/"
_ZIP_RE = re.compile(r"TabelaUnificada_(\d{6})_v\d+\.zip")


def fetch_ipca(cfg: Config) -> RawFile:
    return fetch_to_raw(cfg, "ipca", "sidra_1737", SIDRA_URL, "sidra_1737.json")


def fetch_incc(cfg: Config) -> RawFile:
    return fetch_to_raw(cfg, "incc", "sgs_192", SGS_INCC_URL, "sgs_192.json")


def ultimo_sigtap_zip() -> tuple[str, str]:
    """Descobre no FTP o zip da competência mais recente: (competencia 'AAAAMM', nome do arquivo)."""
    req = urllib.request.Request(SIGTAP_FTP_DIR, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=120) as r:  # noqa: S310 - URL fixa de fonte pública
        listagem = r.read().decode("latin-1")
    achados = sorted({(m.group(1), m.group(0)) for m in _ZIP_RE.finditer(listagem)})
    if not achados:
        raise RuntimeError("nenhum zip TabelaUnificada encontrado no FTP do DATASUS")
    return achados[-1]


def fetch_sigtap(cfg: Config) -> tuple[str, RawFile]:
    comp, nome = ultimo_sigtap_zip()
    return comp, fetch_to_raw(cfg, "sigtap", comp, SIGTAP_FTP_DIR + nome, nome)
