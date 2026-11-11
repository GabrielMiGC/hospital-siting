"""Descoberta da competência mais recente publicada pelo CNES."""

from __future__ import annotations

import re
from ftplib import FTP

import httpx

FTP_HOST = "ftp.datasus.gov.br"
FTP_BASE = "/dissemin/publicos/CNES/200508_/Dados"


def _disponibilidades(ftp: FTP, sigla: str) -> set[tuple[str, str]]:
    nomes = ftp.nlst(f"{FTP_BASE}/{sigla}/")
    padrao = re.compile(rf"(?:^|/){sigla}([A-Z]{{2}})(\d{{2}})(\d{{2}})\.dbc$", re.IGNORECASE)
    return {
        (match.group(1).upper(), f"20{match.group(2)}-{match.group(3)}")
        for nome in nomes
        if (match := padrao.search(nome.replace("\\", "/")))
    }


def latest_competencia(client: httpx.Client, uf: str | None = None) -> str:
    """Lista ST/LT no FTP do DATASUS e retorna a maior competência comum."""
    del client  # httpx não implementa FTP; a assinatura é uniforme com os demais fetchers.
    with FTP(FTP_HOST, timeout=60) as ftp:
        ftp.login()
        comuns = _disponibilidades(ftp, "ST") & _disponibilidades(ftp, "LT")
    if uf is not None:
        comuns = {(arquivo_uf, comp) for arquivo_uf, comp in comuns if arquivo_uf == uf.upper()}
    if not comuns:
        raise RuntimeError("nenhuma competência comum encontrada nos diretórios ST e LT do CNES")
    return max(comp for _, comp in comuns)
