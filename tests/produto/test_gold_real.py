"""Contra a gold real da Bahia no PostGIS local. Pulado quando a base não está carregada (como no CI)."""

import pytest

from hospital_siting.core.config import load_config
from hospital_siting.produto.custos import Premissas, custos_portes
from hospital_siting.produto.otimizador import Parametros, otimizar

pytestmark = pytest.mark.db


@pytest.fixture(scope="module")
def gold_real():
    from hospital_siting.produto.dados import carregar_gold

    try:
        g = carregar_gold(load_config().pg_dsn)
    except Exception as e:  # noqa: BLE001
        pytest.skip(f"gold indisponível: {e.__class__.__name__}")
    if len(g.municipios) < 400:
        pytest.skip("gold carregada não é a da Bahia completa")
    return g


def test_gold_real_tem_a_bahia_inteira(gold_real):
    assert len(gold_real.municipios) == 417
    assert gold_real.data_base == "2026-09"
    assert gold_real.tempos["minutos"].notna().all()


def test_custos_reais_crescem_com_o_porte_e_tem_precos(gold_real):
    c = custos_portes(gold_real, Premissas())
    totais = [c[p].total for p in ("H1", "H2", "H3", "H4")]
    assert totais == sorted(totais)
    assert 20e6 < c["H1"].total < 100e6
    assert c["H4"].equipamentos > c["H3"].equipamentos > c["H2"].equipamentos  # neuro, hemodinâmica, ortopedia


def test_otimizador_resolve_a_bahia(gold_real):
    res = otimizar(gold_real, Parametros(orcamento=3e8))
    assert res.status in {"ótimo", "limite de tempo"}
    assert res.hospitais and res.custo_total <= 3e8
    assert res.tempo_s < 30
    membros = [m.cod_ibge for h in res.hospitais for m in h.municipios if m.consorciado]
    assert len(membros) == len(set(membros))  # cada município em no máximo um consórcio
