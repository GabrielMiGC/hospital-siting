import pandas as pd
import pytest

from hospital_siting.core.money import corrigir, fator, mes_de_ano

IDX = pd.DataFrame({"indice": ["IPCA"] * 3, "mes": ["2024-12", "2025-12", "2026-09"], "valor": [100.0, 105.0, 108.15]})


def test_fator():
    assert fator(IDX, "IPCA", "2024-12", "2026-09") == pytest.approx(1.0815)


def test_corrigir_series():
    out = corrigir(pd.Series([1000.0, 1000.0]), pd.Series(["2024-12", "2025-12"]), IDX, "IPCA", "2026-09")
    assert out.round(2).tolist() == [1081.50, 1030.0]


def test_fator_missing_month_raises():
    with pytest.raises(KeyError):
        fator(IDX, "IPCA", "2019-01", "2026-09")


def test_mes_de_ano():
    assert mes_de_ano(2024) == "2024-12"
