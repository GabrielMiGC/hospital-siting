import pandas as pd
import pytest

from hospital_siting.custos import rais

# Microdados RAIS já lidos: município (7 dígitos IBGE), CBO 2002 e remuneração de dezembro.
RAIS_FIX = pd.DataFrame(
    {
        "Município": ["2927408", "2927408", "2927408", "2927408", "3550308"],
        "CBO Ocupação 2002": ["223505", "223505", "223505", "223565", "223505"],
        "Vl Remun Dezembro Nom": [4000.0, 4500.0, 5000.0, 3000.0, 9000.0],
    }
)


def test_rais_salarios_median_and_filters(cfg_repo):
    # 3550308 (outra UF) e CBO 223565 (fora da lista) não entram na mediana
    out = rais.salarios(RAIS_FIX, ["223505"], cfg_repo.cod_uf, 2024, descricoes={"223505": "Enfermeiro"})
    assert out.set_index("cbo").loc["223505", "salario_medio"] == pytest.approx(4500.0)
    assert set(out.cbo) == {"223505"}


def test_descricoes_cbo_da_tabela_datasus():
    tabela = pd.DataFrame({"CBO": ["223505 ", "225125"], "DS_CBO": ["Enfermeiro  ", "Medico clinico"]})
    assert rais.descricoes_cbo(tabela) == {"223505": "Enfermeiro", "225125": "Medico clinico"}


def test_salarios_usa_descricao_oficial_do_cbo(cfg_repo):
    out = rais.salarios(RAIS_FIX, ["223505"], cfg_repo.cod_uf, 2024, descricoes={"223505": "Enfermeiro"})
    assert out.set_index("cbo").loc["223505", "descricao"] == "Enfermeiro"


def test_salarios_falha_sem_descricao_do_cbo(cfg_repo):
    with pytest.raises(ValueError, match="223505"):
        rais.salarios(RAIS_FIX, ["223505"], cfg_repo.cod_uf, 2024, descricoes={"999999": "Outro"})


def test_schema_rejeita_descricao_igual_ao_codigo():
    import pandera.errors

    from hospital_siting.schemas.silver import SALARIO_OCUPACAO

    df = pd.DataFrame({"cbo": ["223505"], "descricao": ["223505"], "salario_medio": [4500.0], "ano": [2024]})
    with pytest.raises(pandera.errors.SchemaError):
        SALARIO_OCUPACAO.validate(df)
