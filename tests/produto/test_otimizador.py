"""Casos pequenos com solução conhecida.

Custos da gold de teste (Premissas padrão): H1 ≈ R$ 2,25 mi (10 leitos clínicos), H2 ≈ R$ 6,8 mi (20 clínicos + 10 UTI).
"""

import pytest

from hospital_siting.produto.otimizador import Parametros, otimizar
from tests.produto.conftest import fazer_gold

RICO = 1e9  # receita que torna qualquer consórcio viável


def _abertos(res):
    return sorted((h.cod_ibge, h.porte) for h in res.hospitais)


def test_um_hospital_vai_para_o_municipio_central():
    # A —25— B —25— C ; A—C 50 min. Em B tudo fica a até 30 min (peso 1).
    g = fazer_gold(
        municipios=[("A", "A", 30_000, RICO, 0, 0), ("B", "B", 30_000, RICO, 0, 1), ("C", "C", 30_000, RICO, 0, 2)],
        deficit=[("A", "clinico", 4), ("B", "clinico", 2), ("C", "clinico", 4)],
        tempos={("A", "B"): 25, ("B", "C"): 25, ("A", "C"): 50},
    )
    res = otimizar(g, Parametros(orcamento=3e6, portes=["H1", "H2"]))
    assert _abertos(res) == [("B", "H1")]
    assert res.deficit_coberto == pytest.approx(10)
    h = res.hospitais[0]
    assert {m.cod_ibge for m in h.municipios} == {"A", "B", "C"}
    assert h.populacao_atendida == pytest.approx(90_000)


def test_cobertura_gradual_reduz_o_que_conta():
    # Só A tem candidato (B pequeno); B a 105 min -> peso 0,5.
    g = fazer_gold(
        municipios=[("A", "A", 30_000, RICO, 0, 0), ("B", "B", 5_000, RICO, 0, 1)],
        deficit=[("B", "clinico", 8)],
        tempos={("A", "B"): 105},
    )
    res = otimizar(g, Parametros(orcamento=3e6, portes=["H1"]))
    assert res.deficit_coberto == pytest.approx(4)


def test_capacidade_limita_cobertura():
    g = fazer_gold(
        municipios=[("A", "A", 30_000, RICO, 0, 0)],
        deficit=[("A", "clinico", 50)],
        tempos={},
    )
    res = otimizar(g, Parametros(orcamento=3e6, portes=["H1"]))
    assert res.deficit_coberto == pytest.approx(10)  # H1 tem 10 leitos clínicos


def test_concentracao_desempata_contra_quem_ja_tem_hospitais():
    g = fazer_gold(
        municipios=[("A", "A", 30_000, RICO, 0, 0), ("C", "C", 30_000, RICO, 0, 5)],
        deficit=[("A", "clinico", 10), ("C", "clinico", 10)],
        tempos={("A", "C"): 300},
        estabelecimentos=[("1", "C", 10), ("2", "C", 10), ("3", "C", 10)],
    )
    res = otimizar(g, Parametros(orcamento=3e6, portes=["H1"], peso_concentracao=1.0))
    assert _abertos(res) == [("A", "H1")]
    assert res.hospitais[0].hospitais_no_raio == 0


def test_orcamento_para_dois_gera_consorcios_disjuntos():
    g = fazer_gold(
        municipios=[("A", "A", 30_000, RICO, 0, 0), ("B", "B", 5_000, RICO, 0, 1), ("D", "D", 30_000, RICO, 0, 9)],
        deficit=[("A", "clinico", 10), ("D", "clinico", 10), ("B", "clinico", 3)],
        tempos={("A", "D"): 400, ("A", "B"): 20, ("B", "D"): 100},
    )
    res = otimizar(g, Parametros(orcamento=5e6, portes=["H1"]))
    assert _abertos(res) == [("A", "H1"), ("D", "H1")]
    membros = [{m.cod_ibge for m in h.municipios} for h in res.hospitais]
    assert not (membros[0] & membros[1])
    assert res.custo_total <= 5e6


def test_porte_sem_uti_nao_cobre_uti():
    g = fazer_gold(
        municipios=[("A", "A", 30_000, RICO, 0, 0)],
        deficit=[("A", "uti_adulto", 5)],
        tempos={},
    )
    so_h1 = otimizar(g, Parametros(orcamento=1e8, portes=["H1"]))
    assert so_h1.hospitais == []
    com_h2 = otimizar(g, Parametros(orcamento=1e8, portes=["H1", "H2"]))
    assert _abertos(com_h2) == [("A", "H2")]
    assert com_h2.hospitais[0].deficit_por_tipo["uti_adulto"] == pytest.approx(5)


def test_consorcio_inviavel_e_descartado_com_motivo():
    g = fazer_gold(
        municipios=[("A", "A", 30_000, 1_000.0, 0, 0)],
        deficit=[("A", "clinico", 10)],
        tempos={},
    )
    res = otimizar(g, Parametros(orcamento=3e6, portes=["H1"]))
    assert res.hospitais == []
    assert res.descartados and res.descartados[0].cod_ibge == "A"
    assert "consórcio" in res.descartados[0].motivo


def test_municipio_sem_receita_contribui_zero():
    g = fazer_gold(
        municipios=[("A", "A", 30_000, None, 0, 0), ("B", "B", 30_000, RICO, 0, 1)],
        deficit=[("A", "clinico", 10)],
        tempos={("A", "B"): 20},
    )
    res = otimizar(g, Parametros(orcamento=3e6, portes=["H1"], pop_min_candidato=30_000))
    h = res.hospitais[0]
    contrib = {m.cod_ibge: m.contribuicao for m in h.municipios}
    assert contrib.get("A", 0.0) == 0.0
    assert h.viabilidade.contribuicao_municipal == pytest.approx(0.2 * RICO)


def test_orcamento_insuficiente_retorna_zero_hospitais_com_mensagem():
    g = fazer_gold(
        municipios=[("A", "A", 30_000, RICO, 0, 0)],
        deficit=[("A", "clinico", 10)],
        tempos={},
    )
    res = otimizar(g, Parametros(orcamento=1e6, portes=["H1", "H2"]))
    assert res.hospitais == []
    assert "mais barato" in res.mensagem


def test_resultado_traz_status_gap_e_justificativa():
    g = fazer_gold(
        municipios=[("A", "A", 30_000, RICO, 0, 0)],
        deficit=[("A", "clinico", 10)],
        tempos={},
    )
    res = otimizar(g, Parametros(orcamento=3e6, portes=["H1"]))
    assert res.status in {"ótimo", "limite de tempo"}
    assert res.gap is not None and res.gap >= 0
    assert "H1" in res.hospitais[0].justificativa and "A" in res.hospitais[0].justificativa


def test_receita_de_um_municipio_nao_sustenta_dois_consorcios():
    # A e C pobres, distantes entre si; B (não candidato) no meio paga a operação de um H1, mas não de dois.
    # H1 de teste: operação ≈ R$ 246 mil/ano, SUS ≈ R$ 58 mil, Estado 40% -> municípios precisam de ≈ R$ 89 mil.
    g = fazer_gold(
        municipios=[
            ("A", "A", 30_000, 1_000.0, 0, 0),
            ("B", "B", 5_000, 600_000.0, 0, 1),
            ("C", "C", 30_000, 1_000.0, 0, 2),
        ],
        deficit=[("A", "clinico", 10), ("C", "clinico", 10)],
        tempos={("A", "B"): 20, ("B", "C"): 20, ("A", "C"): 300},
    )
    res = otimizar(g, Parametros(orcamento=5e6, portes=["H1"]))
    assert len(res.hospitais) == 1
    socio_b = [h.cod_ibge for h in res.hospitais for m in h.municipios if m.cod_ibge == "B" and m.consorciado]
    assert len(socio_b) == 1
    assert res.hospitais[0].viabilidade.cobertura_pct >= 100


def test_municipio_atendido_por_dois_hospitais_conta_inteiro_no_relatorio():
    # B (não candidato) tem 20 leitos de déficit e fica a 20 min de A e de C; cada H1 tem 10 leitos clínicos.
    g = fazer_gold(
        municipios=[("A", "A", 30_000, RICO, 0, 0), ("B", "B", 5_000, RICO, 0, 1), ("C", "C", 30_000, RICO, 0, 2)],
        deficit=[("B", "clinico", 20)],
        tempos={("A", "B"): 20, ("B", "C"): 20, ("A", "C"): 300},
    )
    res = otimizar(g, Parametros(orcamento=5e6, portes=["H1"]))
    assert _abertos(res) == [("A", "H1"), ("C", "H1")]
    assert res.deficit_coberto == pytest.approx(20)
    assert [h.deficit_coberto for h in res.hospitais] == pytest.approx([10, 10])
    socios_b = [h.cod_ibge for h in res.hospitais for m in h.municipios if m.cod_ibge == "B" and m.consorciado]
    assert len(socios_b) == 1  # atendido pelos dois, sócio de um só
