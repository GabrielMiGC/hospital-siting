import json

import geopandas as gpd
import httpx
import numpy as np
from shapely.geometry import box

from hospital_siting.rotas.matriz import tabela_osrm

BASE_URL = "http://osrm:5000"
OSRM_TABLE_URL = r"http://osrm:5000/table/v1/driving/.*"

# Coordenadas (lon, lat) em EPSG:4674 (SIRGAS 2000), perto de Salvador e Feira de Santana.
COORDS3 = [(-38.510, -12.971), (-38.967, -12.266), (-38.450, -13.010)]

# Par (origem, destino) sem rota: vira null na resposta do OSRM.
PAR_NULL = (0, 2)

# Duração "verdadeira" em segundos e distância em metros (10 m/s), zero na diagonal.
N = len(COORDS3)
SEG_VERDADE = np.array([[0.0 if i == j else 60.0 * (i + j + 1) for j in range(N)] for i in range(N)])
MET_VERDADE = SEG_VERDADE * 10.0

# Dois polígonos pequenos na Bahia (CRS 4674), para poligono_buffer.
LIM_FIX = gpd.GeoDataFrame(
    {"nome": ["poligono_a", "poligono_b"]},
    geometry=[box(-38.60, -12.99, -38.45, -12.90), box(-39.00, -12.35, -38.92, -12.20)],
    crs="EPSG:4674",
)


def _indices_globais(path_coords: str) -> list[int]:
    """Mapeia as coordenadas 'lon,lat;lon,lat;...' da URL para os índices em COORDS3."""
    out = []
    for par in path_coords.split(";"):
        lon, lat = (float(v) for v in par.split(","))
        achado = [
            k
            for k, (x, y) in enumerate(COORDS3)
            if np.isclose(x, lon, atol=1e-9) and np.isclose(y, lat, atol=1e-9)
        ]
        assert len(achado) == 1, f"coordenada fora de COORDS3: {par}"
        out.append(achado[0])
    return out


def _resposta_osrm(request: httpx.Request) -> httpx.Response:
    """Responde a uma requisição /table conforme sources/destinations da query."""
    coords_url = request.url.path.rsplit("/", 1)[-1]
    glob = _indices_globais(coords_url)
    sources = [int(s) for s in request.url.params["sources"].split(";")]
    destinations = [int(d) for d in request.url.params["destinations"].split(";")]

    durations, distances = [], []
    for s in sources:
        linha_seg, linha_met = [], []
        for d in destinations:
            origem, destino = glob[s], glob[d]
            if (origem, destino) == PAR_NULL:
                linha_seg.append(None)
                linha_met.append(None)
            else:
                linha_seg.append(float(SEG_VERDADE[origem, destino]))
                linha_met.append(float(MET_VERDADE[origem, destino]))
        durations.append(linha_seg)
        distances.append(linha_met)

    corpo = {"code": "Ok", "durations": durations, "distances": distances}
    return httpx.Response(200, content=json.dumps(corpo))


def test_tabela_osrm_blocks_and_nulls(respx_mock):
    # 3 coordenadas, bloco=2 → blocos [0,1] e [2] → 2 x 2 = 4 requisições;
    # o par (0, 2) volta como null e deve virar NaN nas duas matrizes.
    route = respx_mock.get(url__regex=OSRM_TABLE_URL).mock(side_effect=_resposta_osrm)

    seg, met = tabela_osrm(COORDS3, BASE_URL, bloco=2)

    assert route.call_count == 4
    assert seg.shape == (3, 3) and met.shape == (3, 3)
    assert np.isnan(seg[PAR_NULL]) and np.isnan(met[PAR_NULL])

    valido = ~np.isnan(seg)
    assert valido.sum() == N * N - 1
    np.testing.assert_allclose(seg[valido], SEG_VERDADE[valido])
    # metros coerentes com os segundos (mesmo par, mesma máscara de nulls)
    np.testing.assert_array_equal(valido, ~np.isnan(met))
    np.testing.assert_allclose(met[valido], seg[valido] * 10.0)
