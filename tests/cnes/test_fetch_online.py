import re

import httpx
import pytest

from hospital_siting.cnes.fetch import latest_competencia
from hospital_siting.core.storage import USER_AGENT


@pytest.mark.online
def test_latest_competencia_lista_ftp_datasus():
    with httpx.Client(headers={"User-Agent": USER_AGENT}, timeout=60) as client:
        comp = latest_competencia(client)
    assert re.fullmatch(r"\d{4}-\d{2}", comp)
    assert comp >= "2020-01"
