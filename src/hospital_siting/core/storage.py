"""Armazenamento em camadas: raw (original imutável + manifest), bronze e silver (Parquet)."""

from __future__ import annotations

import hashlib
import json
import urllib.request
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

import geopandas as gpd
import httpx
import pandas as pd
import pyarrow.parquet as pq

from hospital_siting.core.config import Config

USER_AGENT = "hospital-siting/0.1 (projeto de portfolio)"
TIMEOUT = httpx.Timeout(120.0, connect=30.0)


@dataclass(frozen=True)
class RawFile:
    fonte: str
    ref: str
    path: Path
    sha256: str
    url: str
    coletado_em: datetime
    novo: bool


def _manifest(cfg: Config, fonte: str) -> Path:
    return cfg.data_dir / "raw" / fonte / "manifest.jsonl"


def _ler_manifest(cfg: Config, fonte: str) -> list[dict]:
    m = _manifest(cfg, fonte)
    if not m.exists():
        return []
    return [json.loads(x) for x in m.read_text(encoding="utf-8").splitlines() if x.strip()]


def _from_entry(cfg: Config, e: dict, novo: bool) -> RawFile:
    return RawFile(e["fonte"], e["ref"], cfg.data_dir / e["path"], e["sha256"], e["url"],
                   datetime.fromisoformat(e["coletado_em"]), novo)


def save_raw(cfg: Config, fonte: str, ref: str, filename: str, content: bytes, url: str) -> RawFile:
    """Grava o arquivo original em data/raw/<fonte>/<ref>/ e registra no manifest. Idempotente por sha256."""
    sha = hashlib.sha256(content).hexdigest()
    for e in _ler_manifest(cfg, fonte):
        if e["sha256"] == sha and e["ref"] == ref and e["filename"] == filename and (cfg.data_dir / e["path"]).exists():
            return _from_entry(cfg, e, novo=False)

    destino = cfg.data_dir / "raw" / fonte / ref / filename
    if destino.exists():  # mesmo nome, conteúdo diferente: preserva o original anterior
        destino = destino.with_name(f"{destino.stem}.{sha[:8]}{destino.suffix}")
    destino.parent.mkdir(parents=True, exist_ok=True)
    destino.write_bytes(content)

    entry = {
        "fonte": fonte, "ref": ref, "filename": filename,
        "path": destino.relative_to(cfg.data_dir).as_posix(), "sha256": sha, "url": url,
        "bytes": len(content), "coletado_em": datetime.now(UTC).isoformat(),
    }
    m = _manifest(cfg, fonte)
    m.parent.mkdir(parents=True, exist_ok=True)
    with m.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    return _from_entry(cfg, entry, novo=True)


def _baixar(url: str, client: httpx.Client | None) -> bytes:
    if url.startswith("ftp://"):
        req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
        with urllib.request.urlopen(req, timeout=300) as r:  # noqa: S310 - URLs de fontes públicas fixas
            return r.read()
    if client is not None:
        resp = client.get(url)
    else:
        with httpx.Client(headers={"User-Agent": USER_AGENT}, timeout=TIMEOUT, follow_redirects=True) as c:
            resp = c.get(url)
    resp.raise_for_status()
    return resp.content


def fetch_to_raw(
    cfg: Config, fonte: str, ref: str, url: str, filename: str, client: httpx.Client | None = None
) -> RawFile:
    """Baixa `url` para raw, sem nova requisição se (ref, filename, url) já estiver no manifest."""
    for e in reversed(_ler_manifest(cfg, fonte)):
        if e["ref"] == ref and e["filename"] == filename and e["url"] == url and (cfg.data_dir / e["path"]).exists():
            return _from_entry(cfg, e, novo=False)
    return save_raw(cfg, fonte, ref, filename, _baixar(url, client), url)


def bronze_path(cfg: Config, fonte: str, nome: str) -> Path:
    p = cfg.data_dir / "bronze" / fonte / f"{nome}.parquet"
    p.parent.mkdir(parents=True, exist_ok=True)
    return p


def silver_path(cfg: Config, nome: str) -> Path:
    p = cfg.data_dir / "silver" / f"{nome}.parquet"
    p.parent.mkdir(parents=True, exist_ok=True)
    return p


def write_parquet(df: pd.DataFrame, path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(path, index=False)  # GeoDataFrame grava GeoParquet
    return path


def read_parquet(path: Path) -> pd.DataFrame:
    meta = pq.read_schema(path).metadata or {}
    return gpd.read_parquet(path) if b"geo" in meta else pd.read_parquet(path)
