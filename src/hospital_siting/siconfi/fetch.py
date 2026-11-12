"""Coleta da DCA (Anexo I-C) na API de dados abertos do SICONFI."""

from __future__ import annotations

import json
import time
from datetime import date

import httpx

from hospital_siting.core.config import Config, load_config
from hospital_siting.core.storage import bronze_path, fetch_to_raw, read_parquet, silver_path

URL = "https://apidatalake.tesouro.gov.br/ords/siconfi/tt/dca"
ANEXO = "DCA-Anexo%20I-C"
FONTE = "siconfi"
INTERVALO_S = 0.2
LIMIAR_FECHADO = 0.8


def codigos_municipios(cfg: Config) -> list[str]:
    """Códigos IBGE de 7 dígitos da silver `municipio`."""
    df = read_parquet(silver_path(cfg, "municipio"))
    return sorted(df["cod_ibge"].astype(str))


def _url(exercicio: int, cod_ibge: str, offset: int) -> str:
    u = f"{URL}?an_exercicio={exercicio}&no_anexo={ANEXO}&id_ente={cod_ibge}"
    return u + (f"&offset={offset}" if offset else "")


def _espera(ultimo: list[float]) -> None:
    falta = INTERVALO_S - (time.monotonic() - ultimo[0])
    if falta > 0:
        time.sleep(falta)


def _municipio(cfg: Config, exercicio: int, cod: str, client: httpx.Client, ultimo: list[float]) -> list[dict]:
    itens: list[dict] = []
    offset = 0
    while True:
        url = _url(exercicio, cod, offset)
        # fetch_to_raw é idempotente: só espera/requisita se não estiver no manifest
        _espera(ultimo)
        raw = fetch_to_raw(cfg, FONTE, str(exercicio), url, f"dca_{cod}_{offset}.json", client)
        if raw.novo:
            ultimo[0] = time.monotonic()
        page = json.loads(raw.path.read_text(encoding="utf-8"))
        itens.extend(page.get("items", []))
        if not page.get("hasMore"):
            return itens
        offset += int(page.get("limit") or len(page.get("items", [])) or 1)


def dca(cfg: Config, exercicio: int, client: httpx.Client) -> list[dict]:
    """Itens da DCA-Anexo I-C de todos os municípios da UF (uma requisição por município, paginada)."""
    ultimo = [0.0]
    out: list[dict] = []
    for cod in codigos_municipios(cfg):
        out.extend(_municipio(cfg, exercicio, cod, client, ultimo))
    bronze_path(cfg, FONTE, f"dca_{exercicio}")  # garante diretório
    return out


def ultimo_exercicio_fechado(client: httpx.Client, cfg: Config | None = None) -> int:
    """Maior exercício em que ≥ 80% dos municípios da UF entregaram a DCA."""
    cfg = cfg or load_config()
    cods = codigos_municipios(cfg)
    ultimo = [0.0]
    for ano in range(date.today().year - 1, date.today().year - 8, -1):
        entregues = 0
        for i, cod in enumerate(cods):
            if _municipio(cfg, ano, cod, client, ultimo):
                entregues += 1
            if entregues + (len(cods) - i - 1) < LIMIAR_FECHADO * len(cods):
                break
        if entregues >= LIMIAR_FECHADO * len(cods):
            return ano
    raise RuntimeError("nenhum exercício recente com DCA fechada")
