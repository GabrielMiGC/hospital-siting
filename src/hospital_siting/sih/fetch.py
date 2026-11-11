"""Descoberta das competências do SIH publicadas no FTP do DATASUS."""

from __future__ import annotations

import re
from ftplib import FTP  # noqa: S402 - fonte pública fixa

import httpx

from hospital_siting.core.config import load_config

HOST = "ftp.datasus.gov.br"
DIR = "/dissemin/publicos/SIHSUS/200801_/Dados/"
BASE_FTP = f"ftp://{HOST}{DIR}"
BASE_HTTPS = f"https://{HOST}{DIR}"


def nome_arquivo(uf: str, competencia: str) -> str:
    """'2026-06' -> 'RD{UF}2606.dbc'."""
    ano, mes = competencia.split("-")
    return f"RD{uf}{ano[2:]}{mes}.dbc"


def url_arquivo(uf: str, competencia: str) -> str:
    return BASE_FTP + nome_arquivo(uf, competencia)


def _listar_http(client: httpx.Client) -> list[str]:
    resp = client.get(BASE_HTTPS)
    resp.raise_for_status()
    return re.findall(r"RD[A-Z]{2}\d{4}\.dbc", resp.text, flags=re.IGNORECASE)


def _listar_ftp() -> list[str]:
    with FTP(HOST, timeout=60) as ftp:  # noqa: S321
        ftp.login()
        ftp.cwd(DIR)
        return ftp.nlst()


def competencias(n: int, client: httpx.Client | None, uf: str | None = None) -> list[str]:
    """As `n` últimas competências publicadas (RD{UF}{YYMM}.dbc), em ordem cronológica, como 'AAAA-MM'."""
    uf = (uf or load_config().uf).upper()
    padrao = re.compile(rf"^RD{uf}(\d{{2}})(\d{{2}})\.dbc$", re.IGNORECASE)
    try:
        if client is None:
            raise httpx.HTTPError("sem cliente HTTP")
        nomes = _listar_http(client)
    except httpx.HTTPError:
        nomes = _listar_ftp()
    comps = set()
    for nome in nomes:
        m = padrao.match(nome.rsplit("/", 1)[-1])
        if m and 1 <= int(m.group(2)) <= 12:
            comps.add(f"20{m.group(1)}-{m.group(2)}")
    return sorted(comps)[-n:]
