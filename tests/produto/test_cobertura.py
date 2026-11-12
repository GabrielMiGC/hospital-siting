import numpy as np
import pytest

from hospital_siting.produto.cobertura import hospitais_no_raio, peso_cobertura
from tests.produto.conftest import fazer_gold


def test_peso_100_ate_t_full():
    assert peso_cobertura(np.array([0.0, 15.0, 30.0]), 30, 180).tolist() == [1.0, 1.0, 1.0]


def test_peso_cai_linear_ate_t_max():
    assert peso_cobertura(np.array([105.0]), 30, 180)[0] == pytest.approx(0.5)


def test_peso_zero_apos_t_max_e_sem_rota():
    assert peso_cobertura(np.array([180.0, 200.0, np.nan]), 30, 180).tolist() == [0.0, 0.0, 0.0]


def test_fator_osrm_alonga_o_tempo():
    # 70 min × 1,5 = 105 min -> 0,5
    assert peso_cobertura(np.array([70.0]), 30, 180, fator_osrm=1.5)[0] == pytest.approx(0.5)


def test_t_full_igual_t_max_vira_degrau():
    assert peso_cobertura(np.array([60.0, 61.0]), 60, 60).tolist() == [1.0, 0.0]


def test_hospitais_no_raio_conta_o_proprio_e_vizinhos():
    g = fazer_gold(
        municipios=[("A", "A", 10, 1.0, 0, 0), ("B", "B", 10, 1.0, 0, 0), ("C", "C", 10, 1.0, 0, 0)],
        deficit=[],
        tempos={("A", "B"): 40.0, ("A", "C"): 90.0, ("B", "C"): 50.0},
        estabelecimentos=[("1", "A", 10), ("2", "A", 0), ("3", "C", 5)],
    )
    n = hospitais_no_raio(g, 60)
    assert n.to_dict() == {"A": 2, "B": 3, "C": 1}
