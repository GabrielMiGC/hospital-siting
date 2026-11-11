"""Parsing de formatos das fontes públicas brasileiras."""

from __future__ import annotations

from pathlib import Path

import pandas as pd
from dbfread import DBF

AUSENTES_IBGE = {"", "-", "..", "...", "X", "x"}


def parse_brl(s: str | float | None) -> float | None:
    """'1.234,56' / 'R$ 2.345,00' → float; vazio → None. Números já numéricos passam direto."""
    if s is None:
        return None
    if isinstance(s, (int, float)):
        return None if pd.isna(s) else float(s)
    t = str(s).replace("R$", "").replace("\xa0", "").replace(" ", "").strip()
    if t in ("", "-"):
        return None
    return float(t.replace(".", "").replace(",", "."))


def parse_ibge_number(s: object) -> float | None:
    """Valores da API SIDRA (ponto decimal). Marcadores de ausência (-, .., ..., X) → None."""
    if s is None:
        return None
    if isinstance(s, (int, float)):
        return None if pd.isna(s) else float(s)
    t = str(s).strip()
    if t in AUSENTES_IBGE:
        return None
    return float(t)


def read_dbf(path: Path, encoding: str = "latin-1") -> pd.DataFrame:
    return pd.DataFrame(iter(DBF(str(path), encoding=encoding, char_decode_errors="replace")))


def decompress_dbc(src: Path, dst_dir: Path) -> Path:
    """Descomprime .dbc (DATASUS) para .dbf em dst_dir; reaproveita se já existir."""
    import datasus_dbc

    dst_dir.mkdir(parents=True, exist_ok=True)
    dst = dst_dir / (Path(src).stem + ".dbf")
    if not dst.exists():
        datasus_dbc.decompress(str(src), str(dst))
    return dst
