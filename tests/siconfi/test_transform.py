import json
import unicodedata
from pathlib import Path

import pandas as pd
import pytest

from hospital_siting.schemas.silver import RECEITA_MUNICIPAL
from hospital_siting.siconfi.transform import receita_corrente

FIXTURES = Path(__file__).parents[1] / "fixtures" / "siconfi"


@pytest.fixture
def dca_fix() -> pd.DataFrame:
    data = json.loads((FIXTURES / "dca_fix.json").read_text(encoding="utf-8"))
    return pd.DataFrame(data["items"])


def test_receita_corrente_picks_right_account(dca_fix):
    out = receita_corrente(dca_fix, "29")
    by_ibge = out.set_index("cod_ibge")
    # Liquida de deducoes: 13000344191.33 - 566287718.73 - 1696022159.32
    assert by_ibge.loc["2927408", "receita_corrente"] == pytest.approx(10738034313.28, abs=0.01)
    RECEITA_MUNICIPAL.validate(out)


def test_receita_corrente_missing_municipio_absent(dca_fix):
    # DCA_FIX nao traz Sao Felix
    assert "2930709" not in set(receita_corrente(dca_fix, "29").cod_ibge)


def test_receita_corrente_feira_de_santana(dca_fix):
    out = receita_corrente(dca_fix, "29").set_index("cod_ibge")
    # 2153068992.86 - 128664236.34 - 184863.02
    assert out.loc["2910800", "receita_corrente"] == pytest.approx(2024219893.50, abs=0.01)


def test_receita_corrente_ignora_outras_contas(dca_fix):
    out = receita_corrente(dca_fix, "29")
    # Uma linha por municipio, so a conta RO1.0.0.0.00.0.0 entra no calculo
    assert sorted(out.cod_ibge) == ["2910800", "2927408"]
    assert out.cod_ibge.is_unique


def test_receita_corrente_filtra_outra_uf(dca_fix):
    # 2611606 (Recife, PE) esta nos itens mas nao deve aparecer para cod_uf "29"
    assert "2611606" in set(dca_fix.cod_ibge.astype(str))
    assert "2611606" not in set(receita_corrente(dca_fix, "29").cod_ibge)


def _sem_acento_e_caixa(s: str) -> str:
    nfkd = unicodedata.normalize("NFKD", s)
    return "".join(c for c in nfkd if not unicodedata.combining(c)).upper()


def test_receita_corrente_colunas_sem_acento_ou_caixa(dca_fix):
    variante = dca_fix.copy()
    variante["coluna"] = variante["coluna"].map(_sem_acento_e_caixa)
    assert "DEDUCOES - FUNDEB" in set(variante["coluna"])
    out = receita_corrente(variante, "29").set_index("cod_ibge")
    assert out.loc["2927408", "receita_corrente"] == pytest.approx(10738034313.28, abs=0.01)
    assert out.loc["2910800", "receita_corrente"] == pytest.approx(2024219893.50, abs=0.01)
