import time

import numpy as np
import pandas as pd
import pytest

from hospital_siting.modelo.acesso import deficit, two_step_fca
from hospital_siting.schemas.silver import TIPOS_LEITO


def matriz(pares: dict[tuple[str, str], float]) -> pd.DataFrame:
    """Matriz de tempos origem/destino/minutos para os municípios presentes nos pares.

    Simétrica (t[a,b] == t[b,a]), diagonal 0, pares não informados = NaN.
    """
    municipios = sorted({m for par in pares for m in par})
    linhas = []
    for o in municipios:
        for d in municipios:
            minutos = 0.0 if o == d else pares.get((o, d), pares.get((d, o), np.nan))
            linhas.append((o, d, float(minutos)))
    return pd.DataFrame(linhas, columns=["origem", "destino", "minutos"])


DEM = pd.DataFrame({"cod_ibge": ["A", "B", "C"], "populacao": [1000, 1000, 2000]})
OF = pd.DataFrame({"cod_ibge": ["A"], "tipo_leito": ["uti_adulto"], "leitos": [10]})
T = matriz({("A", "B"): 60, ("A", "C"): 200, ("B", "C"): 100})


def test_matriz_simetrica_diagonal_zero_e_nan_para_nao_informados():
    m = matriz({("A", "B"): 60, ("B", "C"): 100})
    assert list(m.columns) == ["origem", "destino", "minutos"]
    assert len(m) == 9
    by = m.set_index(["origem", "destino"]).minutos
    assert by[("A", "B")] == by[("B", "A")] == 60
    assert all(by[(x, x)] == 0 for x in "ABC")
    assert np.isnan(by[("A", "C")]) and np.isnan(by[("C", "A")])


def test_2sfca_example():
    out = two_step_fca(OF, DEM, T, 120).set_index("cod_ibge").oferta_acessivel
    assert out.to_dict() == pytest.approx({"A": 5.0, "B": 5.0, "C": 0.0})


def test_2sfca_conserves_supply_when_all_reachable():
    assert two_step_fca(OF, DEM, T, 300).oferta_acessivel.sum() == pytest.approx(10.0)


def test_2sfca_nan_time_is_unreachable():
    t = T.copy()
    t.loc[(t.origem == "A") & (t.destino == "B"), "minutos"] = np.nan
    t.loc[(t.origem == "B") & (t.destino == "A"), "minutos"] = np.nan
    out = two_step_fca(OF, DEM, t, 120).set_index("cod_ibge").oferta_acessivel
    assert out["A"] == pytest.approx(10.0) and out["B"] == 0.0


def test_deficit_math():
    nec = pd.DataFrame({"tipo_leito": ["uti_adulto"], "leitos_por_mil_hab": [2.0]})
    acc = two_step_fca(OF, DEM, T, 120)
    out = deficit(DEM, nec, OF.rename(columns={"leitos": "existente_local_sus"}), acc).set_index("cod_ibge")
    assert out.loc["C", "necessidade"] == 4.0 and out.loc["C", "deficit"] == 4.0
    assert out.loc["A", "deficit"] == pytest.approx(-3.0)


def test_2sfca_performance_417():
    rng = np.random.default_rng(42)
    codigos = [f"{i:07d}" for i in range(417)]
    dem = pd.DataFrame({"cod_ibge": codigos, "populacao": rng.integers(1_000, 500_000, size=417)})
    of = pd.DataFrame(
        [
            {"cod_ibge": c, "tipo_leito": tipo, "leitos": int(rng.integers(1, 50))}
            for c in codigos
            for tipo in TIPOS_LEITO
        ]
    )
    pares = {}
    for i in range(417):
        for j in range(i + 1, 417):
            pares[(codigos[i], codigos[j])] = float(rng.uniform(1, 300))
    tempo = matriz(pares)

    inicio = time.perf_counter()
    out = two_step_fca(of, dem, tempo, 120)
    duracao = time.perf_counter() - inicio

    assert duracao < 2.0
    assert len(out) == 417 * len(TIPOS_LEITO)
