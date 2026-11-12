from dataclasses import replace

import pandas as pd
import pytest

from hospital_siting.produto.custos import Premissas, custo_porte, receita_sus_anual


def test_obra_usa_area_custo_m2_e_fator_hospitalar(gold_mini):
    c = custo_porte(gold_mini, "H1", Premissas(fator_hospitalar=2.5))
    assert c.area_m2 == 800
    assert c.obra == pytest.approx(800 * 1000 * 2.5)


def test_equipamento_so_dos_ambientes_do_porte(gold_mini):
    h1 = custo_porte(gold_mini, "H1", Premissas())
    h2 = custo_porte(gold_mini, "H2", Premissas())
    # H1: 10 camas + raio-X + 1 sala cirúrgica (mínimo); sem UTI e sem tomógrafo
    assert h1.equipamentos == pytest.approx(10 * 100 + 5000 + 700)
    # H2: 20 camas (UTI não usa cama de internação) + 10 monitores + raio-X + tomógrafo + 1 sala
    assert h2.equipamentos == pytest.approx(20 * 100 + 10 * 1000 + 5000 + 50000 + 700)
    assert h2.itens_sem_preco == ["UTI adulto: Sem preço"]
    assert h1.itens_sem_preco == []


def test_operacao_anual_inclui_ist_encargos_nao_normatizado_e_custeio(gold_mini):
    p = Premissas(ist=0.15, horas_turno=8, fator_pessoal_nao_normatizado=1.0)
    c = custo_porte(gold_mini, "H1", p)
    fte = 0.1 * 10 * 3 * 8 * 7 / 40 * 1.15
    assert c.fte == pytest.approx(fte)
    pessoal = fte * 1000 * 12 * 1.7 * 2.0
    assert c.pessoal_anual == pytest.approx(pessoal)
    assert c.custeio_anual == pytest.approx(pessoal * 0.25)
    assert c.operacao_anual == pytest.approx(pessoal * 1.25)
    assert c.total == pytest.approx(c.obra + c.equipamentos + c.operacao_anual)


def test_fte_uti_aplica_minimo_de_um_por_turno(gold_mini):
    arq = pd.DataFrame(
        [("H2", "clinico", 0, 0.0), ("H2", "uti_adulto", 5, 400.0)],
        columns=["porte", "tipo_leito", "leitos", "area_m2_ref"],
    )
    g = replace(gold_mini, arquetipos=arq)
    c = custo_porte(g, "H2", Premissas(ist=0.0))
    # 0,1 × 5 = 0,5 posto → "ou fração" = 1 posto por turno
    assert c.fte == pytest.approx(1 * 3 * 8 * 7 / 40)


def test_receita_sus_por_aih_e_por_diaria(gold_mini):
    assert receita_sus_anual(gold_mini, {"clinico": 10}, 0.8) == pytest.approx(10 * 0.8 * 365 / 5 * 100)
    assert receita_sus_anual(gold_mini, {"uti_adulto": 10}, 0.8) == pytest.approx(10 * 0.8 * 365 * 500)


def test_porte_inexistente_falha(gold_mini):
    with pytest.raises(KeyError):
        custo_porte(gold_mini, "H9", Premissas())
