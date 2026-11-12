import pytest
from fastapi.testclient import TestClient

from hospital_siting.api.app import criar_app
from hospital_siting.api.esquemas import OtimizarEntrada
from hospital_siting.produto.custos import TIPOS_LEITO

GEOJSON = {
    "type": "FeatureCollection",
    "features": [
        {"type": "Feature", "properties": {"cod_ibge": "A", "nome": "Alfa"}, "geometry": None},
        {"type": "Feature", "properties": {"cod_ibge": "B", "nome": "Beta"}, "geometry": None},
    ],
}


@pytest.fixture
def cliente(gold_mini):
    with TestClient(criar_app(gold=gold_mini, geojson=GEOJSON)) as c:
        yield c


def test_saude(cliente):
    r = cliente.get("/api/saude")
    assert r.status_code == 200
    assert r.json() == {"status": "ok", "data_base": "2026-09", "municipios": 2}


def test_parametros_traz_padroes_e_limites(cliente):
    p = cliente.get("/api/parametros").json()
    assert p["padroes"]["pct_receita"] == 0.20
    assert p["padroes"]["t_full"] == 30 and p["padroes"]["t_max"] == 180
    assert p["limites"]["orcamento"]["min"] > 0
    assert p["orcamentos_sugeridos"]


def test_portes_detalha_custos(cliente):
    r = cliente.get("/api/portes", params={"fator_hospitalar": 2.0})
    assert r.status_code == 200
    h1 = next(x for x in r.json() if x["porte"] == "H1")
    assert h1["obra"] == pytest.approx(800 * 1000 * 2.0)
    assert {"equipamentos", "operacao_anual", "total", "custo_leito_ano", "especialidades"} <= set(h1)


def test_municipios_enriquece_o_geojson(cliente):
    fc = cliente.get("/api/municipios").json()
    props = {f["properties"]["cod_ibge"]: f["properties"] for f in fc["features"]}
    assert props["A"]["deficit_total"] == pytest.approx(35.0)
    assert props["A"]["deficit"]["uti_adulto"] == pytest.approx(5.0)
    assert props["B"]["populacao"] == 50_000


def test_otimizar_devolve_indicacoes_com_justificativa(cliente):
    r = cliente.post("/api/otimizar", json={"orcamento": 1e8, "portes": ["H1", "H2"]})
    assert r.status_code == 200
    corpo = r.json()
    assert corpo["hospitais"], corpo
    h = corpo["hospitais"][0]
    assert h["justificativa"]
    assert h["viabilidade"]["cobertura_pct"] > 0
    assert {"obra", "equipamentos", "operacao_anual"} <= set(h["custo"])
    assert corpo["status"] in {"ótimo", "limite de tempo"}
    assert corpo["deficit_coberto"] > 0


def test_otimizar_orcamento_insuficiente_nao_e_erro(cliente):
    r = cliente.post("/api/otimizar", json={"orcamento": 1e7, "portes": ["H2"], "fator_hospitalar": 5})
    assert r.status_code == 200
    assert r.json()["hospitais"] == []
    assert "mais barato" in r.json()["mensagem"]


@pytest.mark.parametrize(
    "corpo",
    [
        {"orcamento": 1e8, "portes": []},
        {"orcamento": -5, "portes": ["H1"]},
        {"orcamento": 1e8, "portes": ["H9"]},
        {"orcamento": 1e8, "portes": ["H1"], "t_full": 200, "t_max": 100},
        {"orcamento": 1e8, "portes": ["H1"], "pct_receita": 3},
        {"orcamento": 1e8, "portes": ["H1"], "peso_uti_adulto": -1},
        {"orcamento": 1e8, "portes": ["H1"], "peso_clinico": 11},
    ],
)
def test_otimizar_rejeita_entrada_invalida_com_422(cliente, corpo):
    assert cliente.post("/api/otimizar", json=corpo).status_code == 422


def test_raiz_serve_a_interface(cliente):
    r = cliente.get("/")
    assert r.status_code == 200
    assert "text/html" in r.headers["content-type"]


def test_parametros_expoe_pesos_por_tipo_neutros(cliente):
    p = cliente.get("/api/parametros").json()
    for t in TIPOS_LEITO:
        assert p["padroes"][f"peso_{t}"] == 1
        assert p["limites"][f"peso_{t}"] == {"min": 0, "max": 10}


def test_pesos_viram_dict_em_parametros():
    par = OtimizarEntrada(orcamento=1e8, peso_uti_adulto=3).parametros()
    assert par.pesos_leito["uti_adulto"] == 3 and par.pesos_leito["clinico"] == 1


def test_otimizar_com_peso_de_uti_muda_o_resultado_e_a_chave_do_cache(cliente):
    # gold_mini: H2 (com UTI) ou H1; com orçamento para um só H2, UTI 5× força leitos de UTI.
    base = cliente.post("/api/otimizar", json={"orcamento": 1e8, "portes": ["H1", "H2"]}).json()
    uti = cliente.post("/api/otimizar", json={"orcamento": 1e8, "portes": ["H1", "H2"], "peso_uti_adulto": 5}).json()
    assert uti["cache"] is False
    assert uti["deficit_ponderado"] > base["deficit_ponderado"]
    assert "prioridade" in uti["mensagem"] and "prioridade" not in base["mensagem"]
