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


def test_prioridade_de_uti_na_bahia_troca_h1_por_portes_com_uti(gold_real):
    neutro = otimizar(gold_real, Parametros(orcamento=1e9))
    uti = otimizar(gold_real, Parametros(orcamento=1e9, pesos_leito={"uti_adulto": 3, "uti_neo_ped": 3}))
    assert neutro.tempo_s < 10
    assert uti.status in {"ótimo", "limite de tempo"} and uti.tempo_s < 12

    def leitos_uti(r):
        tipos = ("uti_adulto", "uti_neo_ped")
        return sum(h.deficit_por_tipo.get(t, 0) for h in r.hospitais for t in tipos)

    assert leitos_uti(uti) > 3 * leitos_uti(neutro)
    assert sum(h.porte == "H1" for h in uti.hospitais) < sum(h.porte == "H1" for h in neutro.hospitais)
