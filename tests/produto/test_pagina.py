from hospital_siting.produto.custos import Premissas, custos_portes
from hospital_siting.produto.otimizador import Parametros, otimizar
from hospital_siting.produto.pagina import secao_fase2


def test_secao_fase2_tem_formulacao_custos_e_exemplo(gold_mini):
    custos = custos_portes(gold_mini, Premissas())
    exemplo = otimizar(gold_mini, Parametros(orcamento=1e8, portes=["H1", "H2"]))
    html = secao_fase2(custos, exemplo)
    assert "<table" in html and "H1" in html and "H2" in html
    assert "R$" in html
    assert "Alfa" in html  # município indicado no exemplo
    assert "consórcio" in html
    assert "<script" not in html.lower()


def test_secao_fase2_sem_exemplo(gold_mini):
    html = secao_fase2(custos_portes(gold_mini, Premissas()), None)
    assert "H1" in html and "exemplo" not in html.lower()


def test_secao_fase2_explica_prioridade(gold_mini):
    html = secao_fase2(custos_portes(gold_mini, Premissas()), None)
    assert "Prioridade por tipo de leito" in html and "todos 1" in html
    assert "π" in html
