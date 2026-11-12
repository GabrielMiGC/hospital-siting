"""Lista RENEM e vínculo curado entre equipamentos e ambientes."""

from __future__ import annotations

import json
import time
import unicodedata
from typing import Any

import pandas as pd

from hospital_siting.core.config import Config
from hospital_siting.core.parsing import parse_brl
from hospital_siting.core.storage import save_raw

CONSULTA_EQUIPAMENTOS_URL = "https://consultafns.saude.gov.br/recursos/equipamento/consultar"
COLUNAS_LISTA = ["cod_item", "item", "classificacao", "valor_sugerido", "dolarizado"]


def _normalizar(texto: object) -> str:
    sem_acento = unicodedata.normalize("NFKD", str(texto)).encode("ascii", "ignore").decode()
    return " ".join(sem_acento.lower().replace("_", " ").split())


def _codigo(valor: object) -> str:
    if pd.isna(valor):
        return ""
    texto = str(valor).strip()
    return texto[:-2] if texto.endswith(".0") else texto


def _dolarizado(valor: object) -> bool:
    texto = _normalizar(valor)
    if texto in {"s", "sim", "true", "1"}:
        return True
    if texto in {"n", "nao", "false", "0"}:
        return False
    raise ValueError(f"valor inválido em Item Dolarizado: {valor!r}")


def parse_lista(df_raw: pd.DataFrame) -> pd.DataFrame:
    """Lê a planilha RENEM carregada com ``header=None``."""
    if len(df_raw) < 2:
        raise ValueError("planilha RENEM sem a linha de cabeçalho")

    cabecalho = {_normalizar(valor): i for i, valor in enumerate(df_raw.iloc[1]) if pd.notna(valor)}
    esperadas = {
        "cod_item": "cod. item",
        "item": "item",
        "classificacao": "classificacao",
        "valor_sugerido": "r$ valor sugerido",
        "dolarizado": "item dolarizado",
    }
    faltantes = [original for original in esperadas.values() if original not in cabecalho]
    if faltantes:
        raise ValueError(f"planilha RENEM sem colunas: {faltantes}")

    dados = df_raw.iloc[2:].reset_index(drop=True)
    out = pd.DataFrame(
        {
            "cod_item": dados.iloc[:, cabecalho[esperadas["cod_item"]]].map(_codigo),
            "item": dados.iloc[:, cabecalho[esperadas["item"]]].astype("string").str.strip(),
            "classificacao": dados.iloc[:, cabecalho[esperadas["classificacao"]]].astype("string").str.strip(),
            "valor_sugerido": dados.iloc[:, cabecalho[esperadas["valor_sugerido"]]].map(parse_brl),
            "dolarizado": dados.iloc[:, cabecalho[esperadas["dolarizado"]]].map(_dolarizado),
        }
    )
    out = out.loc[out["cod_item"].ne("") & out["item"].notna()].copy()
    out["valor_sugerido"] = pd.to_numeric(out["valor_sugerido"], errors="coerce").astype(float)
    out["dolarizado"] = out["dolarizado"].astype(bool)
    return out[COLUNAS_LISTA].reset_index(drop=True)


def de_seed(seed: pd.DataFrame, lista: pd.DataFrame, mes: str) -> pd.DataFrame:
    """Associa o seed ambiente/equipamento ao valor nominal sugerido pela RENEM."""
    obrigatorias = {"ambiente", "equipamento", "cod_item_renem", "unidade", "quantidade_ref"}
    if faltantes := obrigatorias - set(seed.columns):
        raise ValueError(f"seed de equipamentos sem colunas: {sorted(faltantes)}")

    vinculos = seed.copy()
    vinculos["cod_item_renem"] = vinculos["cod_item_renem"].map(_codigo)
    precos = lista[["cod_item", "valor_sugerido"]].copy()
    precos["cod_item"] = precos["cod_item"].map(_codigo)
    unidos = vinculos.merge(precos, how="left", left_on="cod_item_renem", right_on="cod_item", validate="m:1")
    return pd.DataFrame(
        {
            "ambiente": unidos["ambiente"].astype(str).str.strip(),
            "equipamento": unidos["equipamento"].astype(str).str.strip(),
            "unidade": unidos["unidade"].astype(str).str.strip(),
            "quantidade_ref": pd.to_numeric(unidos["quantidade_ref"], errors="raise").astype(float),
            "preco_ref": pd.to_numeric(unidos["valor_sugerido"], errors="coerce").astype(float),
            "fonte": "RENEM/FNS",
            "mes": mes,
        }
    )


def _conteudo_json(response: Any) -> tuple[bytes, dict[str, Any]]:
    response.raise_for_status()
    payload = response.json()
    return json.dumps(payload, ensure_ascii=False).encode(), payload


def crawl_ambientes(cfg: Config, ambientes: list[str], client: Any) -> pd.DataFrame:
    """Consulta a API pública do FNS, com uma requisição por código de ambiente.

    ``ambientes`` recebe os valores de ``coAmbiente``. O JSON original é sempre
    preservado em raw; a tabela retornada mantém os campos disponibilizados pela API.
    """
    frames: list[pd.DataFrame] = []
    ano = str(cfg.params.get("renem_ano", pd.Timestamp.now().year))
    for indice, ambiente in enumerate(ambientes):
        if indice:
            time.sleep(1.0)
        params = {
            "ano": ano,
            "coAmbiente": str(ambiente),
            "abaAtiva": 2,
            "page": 1,
            "count": 10000,
            "stPlanilha": "false",
            "stCardapio": "false",
        }
        response = client.get(CONSULTA_EQUIPAMENTOS_URL, params=params)
        content, payload = _conteudo_json(response)
        request = getattr(response, "request", None)
        url = str(request.url) if request is not None else CONSULTA_EQUIPAMENTOS_URL
        save_raw(cfg, "renem", ano, f"ambiente-{ambiente}.json", content, url)
        resultado = payload.get("resultado", {})
        itens = resultado.get("itensPagina", []) if isinstance(resultado, dict) else []
        frame = pd.DataFrame(itens)
        if not frame.empty:
            frames.append(frame)
    return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()


def mes_referencia(nome_aba: str) -> str | None:
    """'Renem 03_03_26' → '2026-03' (data de referência dos valores sugeridos)."""
    import re

    m = re.search(r"(\d{2})_(\d{2})_(\d{2})", nome_aba)
    return f"20{m.group(3)}-{m.group(2)}" if m else None
