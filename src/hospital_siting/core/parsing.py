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
    """Lê DBF com dbfread; se o cabeçalho estiver sem o terminador 0x0D (comum em DBFs do DATASUS),
    usa um leitor que confia no tamanho de cabeçalho declarado. No fallback, todos os campos vêm como texto."""
    try:
        return pd.DataFrame(iter(DBF(str(path), encoding=encoding, char_decode_errors="replace")))
    except Exception:  # noqa: BLE001 - qualquer falha do dbfread cai no leitor tolerante
        return _read_dbf_tolerante(Path(path), encoding)


def _read_dbf_tolerante(path: Path, encoding: str) -> pd.DataFrame:
    import struct

    import numpy as np

    with path.open("rb") as f:
        cab = f.read(32)
        n_reg, tam_cab, tam_reg = struct.unpack("<IHH", cab[4:12])
        desc = f.read(tam_cab - 32)
        campos: list[tuple[str, int]] = []
        for i in range((tam_cab - 33) // 32):
            d = desc[i * 32 : (i + 1) * 32]
            if d[0] == 0x0D:
                break
            campos.append((d[:11].split(b"\0")[0].decode("ascii", "replace"), d[16]))
        f.seek(tam_cab)
        bruto = np.frombuffer(f.read(n_reg * tam_reg), dtype=np.uint8)[: n_reg * tam_reg]
    regs = bruto.reshape(-1, tam_reg)
    regs = regs[regs[:, 0] != 0x2A]  # '*' = registro apagado
    dados, pos = {}, 1
    for nome, largura in campos:
        col = regs[:, pos : pos + largura]
        dados[nome] = [bytes(r).decode(encoding, "replace").strip() for r in col]
        pos += largura
    return pd.DataFrame(dados)


def decompress_dbc(src: Path, dst_dir: Path) -> Path:
    """Descomprime .dbc (DATASUS) para .dbf em dst_dir; reaproveita se já existir."""
    import datasus_dbc

    dst_dir.mkdir(parents=True, exist_ok=True)
    dst = dst_dir / (Path(src).stem + ".dbf")
    if not dst.exists():
        datasus_dbc.decompress(str(src), str(dst))
    return dst
