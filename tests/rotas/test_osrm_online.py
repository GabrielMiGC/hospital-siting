import httpx
import pytest

from hospital_siting.rotas.matriz import tabela_osrm

# Salvador e Feira de Santana (lon, lat), SIRGAS 2000 ~ WGS84.
SALVADOR = (-38.5108, -12.9714)
FEIRA = (-38.9669, -12.2664)


@pytest.mark.online
def test_osrm_local_salvador_feira_minutos():
    # Requer o OSRM local em http://localhost:5000 (docker compose -f docker-compose.osrm.yml up -d).
    try:
        seg, _ = tabela_osrm([SALVADOR, FEIRA], "http://localhost:5000")
    except httpx.ConnectError:
        pytest.skip("OSRM local não está rodando")
    minutos = seg[0, 1] / 60
    assert 80 <= minutos <= 150
