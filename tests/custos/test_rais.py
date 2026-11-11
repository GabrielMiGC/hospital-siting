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
    out = rais.salarios(RAIS_FIX, ["223505"], cfg_repo.cod_uf, 2024)
    assert out.set_index("cbo").loc["223505", "salario_medio"] == pytest.approx(4500.0)
    assert set(out.cbo) == {"223505"}
