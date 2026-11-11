import pandas as pd
import pytest

from hospital_siting.custos import cub, sinapi
from hospital_siting.schemas.silver import CUSTO_OBRA_M2

# Planilha SINAPI (custo médio m² por UF) como sai do pd.read_excel: valores em formato BR (texto).
SINAPI_FIX = pd.DataFrame(
    {
        "UF": ["BA", "BA", "SE"],
        "Projeto de referência": ["Hospital Geral Tipo I", "Hospital Geral Tipo II", "Hospital Geral Tipo I"],
        "Custo médio m² (R$)": ["2.345,67", "1.234,56", "2.100,00"],
    }
)


def test_sinapi_custo_m2_brl_parsing():
    out = sinapi.custo_m2(SINAPI_FIX, "BA", "2026-09")
    assert out.valor_m2.gt(0).all() and set(out.fonte) == {"SINAPI"}
    CUSTO_OBRA_M2.validate(out)
    # linha de SE é filtrada fora pela UF
    assert set(out.padrao) == {"Hospital Geral Tipo I", "Hospital Geral Tipo II"}
    assert sorted(out.valor_m2) == pytest.approx([1234.56, 2345.67])


def test_cub_custo_m2_brl_parsing():
    tabela = pd.DataFrame({"padrao": ["Hospital Padrão Médio"], "valor": ["2.345,67"]})
    out = cub.custo_m2(tabela, "2026-09")
    assert set(out.fonte) == {"CUB"}
    assert out.valor_m2.tolist() == pytest.approx([2345.67])
    CUSTO_OBRA_M2.validate(out)
