import httpx
import pytest
from hospital_siting.sih.fetch import competencias


@pytest.mark.online
def test_competencias_retorna_n_publicadas():
    with httpx.Client(timeout=60) as client:
        out = competencias(36, client)
    assert len(out) == 36 and len(set(out)) == 36
