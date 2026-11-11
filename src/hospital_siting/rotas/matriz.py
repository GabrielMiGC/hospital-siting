"""Matriz de tempo de viagem via OSRM (/table) e utilitários geométricos."""

from __future__ import annotations

import geopandas as gpd
import httpx
import numpy as np
import pandas as pd
import shapely

CRS_METRICO = 5880  # SIRGAS 2000 / Brazil Polyconic


def poligono_buffer(limites: gpd.GeoDataFrame, km: float) -> shapely.Geometry:
    """União dos limites com buffer de `km` (em projeção métrica), em EPSG:4326."""
    metrico = limites.to_crs(CRS_METRICO)
    uniao = metrico.geometry.union_all().buffer(km * 1000)
    return gpd.GeoSeries([uniao], crs=CRS_METRICO).to_crs(4326).iloc[0]


def _fmt_coords(coords: list[tuple[float, float]]) -> str:
    return ";".join(f"{lon:.6f},{lat:.6f}" for lon, lat in coords)


def _nan_se_none(linhas: list[list[float | None]]) -> np.ndarray:
    return np.array([[np.nan if v is None else v for v in linha] for linha in linhas], dtype=float)


def tabela_osrm(
    coords: list[tuple[float, float]],
    base_url: str,
    bloco: int = 100,
    client: httpx.Client | None = None,
) -> tuple[np.ndarray, np.ndarray]:
    """Matrizes n×n (segundos, metros) via /table/v1/driving em blocos origem × destino.

    Pares sem rota (`null` na resposta) viram NaN.
    """
    n = len(coords)
    seg = np.full((n, n), np.nan)
    met = np.full((n, n), np.nan)
    base = base_url.rstrip("/")
    proprio = client is None
    cli = client or httpx.Client(timeout=httpx.Timeout(600.0, connect=30.0))
    try:
        faixas = [range(i, min(i + bloco, n)) for i in range(0, n, bloco)]
        for orig in faixas:
            for dest in faixas:
                pts = [coords[i] for i in orig] + [coords[j] for j in dest]
                params = {
                    "sources": ";".join(str(k) for k in range(len(orig))),
                    "destinations": ";".join(str(len(orig) + k) for k in range(len(dest))),
                    "annotations": "duration,distance",
                }
                resp = cli.get(f"{base}/table/v1/driving/{_fmt_coords(pts)}", params=params)
                resp.raise_for_status()
                corpo = resp.json()
                if corpo.get("code") != "Ok":
                    raise RuntimeError(f"OSRM /table falhou: {corpo.get('code')} {corpo.get('message', '')}")
                seg[np.ix_(orig, dest)] = _nan_se_none(corpo["durations"])
                met[np.ix_(orig, dest)] = _nan_se_none(corpo["distances"])
    finally:
        if proprio:
            cli.close()
    return seg, met


def para_long(cods: list[str], seg: np.ndarray, met: np.ndarray) -> pd.DataFrame:
    """Matrizes n×n -> formato longo (`MATRIZ_TEMPO`): minutos = seg/60, km = met/1000, diagonal 0."""
    n = len(cods)
    seg = np.array(seg, dtype=float)
    met = np.array(met, dtype=float)
    np.fill_diagonal(seg, 0.0)
    np.fill_diagonal(met, 0.0)
    idx_o, idx_d = np.divmod(np.arange(n * n), n)
    arr = np.asarray(cods, dtype=object)
    return pd.DataFrame(
        {
            "origem": arr[idx_o],
            "destino": arr[idx_d],
            "minutos_osrm": (seg / 60.0).ravel(),
            "km": (met / 1000.0).ravel(),
        }
    )
