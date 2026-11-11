import json
from pathlib import Path

import pandas as pd
import pytest

from hospital_siting.indices.transform import incc, ipca, sigtap
from hospital_siting.schemas import silver as S

FIX = Path(__file__).parents[1] / "fixtures" / "indices"


def _linha_sigtap(co: str, no: str, sh: int, sp: int) -> str:
    """Linha de largura fixa de tb_procedimento.txt: CO(10) NO(250) VL_SH(12) VL_SP(12) = 284 chars."""
    return f"{co:<10}{no:<250}{sh:012d}{sp:012d}"


def test_ipca_from_sidra_fixture_drops_header_and_markers():
    rows = json.loads((FIX / "sidra_ipca_1737.json").read_text(encoding="utf-8"))
    raw = pd.DataFrame(rows[1:])  # linhas sem o cabeçalho da API SIDRA

    out = ipca(raw)

    assert len(out) == 2
    assert out["mes"].tolist() == ["2024-08", "2024-10"]
    assert out["valor"].tolist() == pytest.approx([5900.10, 5950.35])
    assert set(out["indice"]) == {"IPCA"}
    S.INDICE.validate(out, lazy=True)


def test_incc_chained_index_from_monthly_pct():
    raw = pd.DataFrame({"data": ["01/08/2026", "01/09/2026", "01/10/2026"], "valor": ["0.66", "1.0", "0.5"]})

    out = incc(raw)  # 1ª variação (agosto) só define a base; 1.0% set; 0.5% out

    assert out.valor.round(4).tolist() == [100.0, 101.0, 101.505]
    assert out.mes.tolist() == ["2026-08", "2026-09", "2026-10"]
    assert set(out["indice"]) == {"INCC"}
    S.INDICE.validate(out, lazy=True)


def test_sigtap_fixed_width_layout_values_in_reais():
    layout = pd.read_csv(FIX / "tb_procedimento_layout.csv")
    linhas = [
        _linha_sigtap("0301010072", "CONSULTA DE PROFISSIONAL DE NIVEL SUPERIOR", 12345, 6789),
        _linha_sigtap("0301010080", "CONSULTA DE ENFERMAGEM", 0, 25000),
    ]

    out = sigtap(layout, linhas, "2026-09")

    assert out["co_procedimento"].tolist() == ["0301010072", "0301010080"]
    assert out["no_procedimento"].tolist() == ["CONSULTA DE PROFISSIONAL DE NIVEL SUPERIOR", "CONSULTA DE ENFERMAGEM"]
    assert out["valor_sh"].round(2).tolist() == [123.45, 0.0]
    assert out["valor_sp"].round(2).tolist() == [67.89, 250.0]
    assert set(out["competencia"]) == {"2026-09"}
    S.SIGTAP_PROCEDIMENTO.validate(out, lazy=True)
