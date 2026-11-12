import pytest

from hospital_siting.gold.build import GoldCheckError, checks_gold, data_base_efetiva, tabelas_gold
from hospital_siting.schemas.silver import TIPOS_LEITO

SSA, FSA, SFX = "2927408", "2910800", "2930709"


def test_data_base_auto_is_latest_sinapi_month_with_indices(cfg_fixture):
    t = tabelas_gold(cfg_fixture)
    assert data_base_efetiva(cfg_fixture, t["indice_correcao"], t["_custo_obra_silver"]) == "2026-09"


def test_tabelas_gold_from_fixture_silvers(cfg_fixture):
    t = tabelas_gold(cfg_fixture)
    dim = t["dim_municipio"].set_index("cod_ibge")
    assert len(dim) == 3
    assert set(t["deficit_leitos"].tipo_leito) <= set(TIPOS_LEITO)
    assert not dim.loc[SFX, "receita_disponivel"] and dim.loc[SSA, "receita_disponivel"]
    assert dim.loc[SSA, "receita_corrente"] == pytest.approx(108.15)  # 100 em 2024-12 → IPCA até 2026-09
    assert dim.loc[SSA, "nome_regiao_saude"] == "Salvador"
    assert dim.loc[SSA, "pib_per_capita"] == pytest.approx(1_081_500.0 / 1000)


def test_monetary_correction_applied(cfg_fixture):
    t = tabelas_gold(cfg_fixture)
    v = t["valor_medio_internacao"].set_index("tipo_leito")
    # (1000 + (3000-2000)) / 2 AIHs = 1000 em 2024-12 → ×1.0815
    assert v.loc["clinico", "valor_medio"] == pytest.approx(1081.50)
    assert v.loc["clinico", "unidade"] == "aih"
    assert v.loc["clinico", "permanencia_media_dias"] == pytest.approx(5.5)
    # UTI adulto: 2000 / 4 diárias = 500 → ×1.0815
    assert v.loc["uti_adulto", "valor_medio"] == pytest.approx(540.75)
    assert v.loc["uti_adulto", "unidade"] == "diaria"
    obra = t["custo_obra_m2"].iloc[0]
    assert obra.valor_m2 == pytest.approx(2000.0) and obra.data_base == "2026-09"
    eq = t["equipamento_ambiente"].iloc[0]
    assert eq.preco_ref == pytest.approx(10000.0 * 108.15 / 105.0)


def test_deficit_uses_2sfca_and_excludes_fora_do_escopo(cfg_fixture):
    t = tabelas_gold(cfg_fixture)
    d = t["deficit_leitos"].set_index(["cod_ibge", "tipo_leito"])
    # 10 UTI SUS em Salvador, alcançáveis por SSA e FSA (60 min ≤ 120) → 5 cada; SFX (200 min) não alcança
    assert d.loc[(SSA, "uti_adulto"), "oferta_acessivel_sus"] == pytest.approx(5.0)
    assert d.loc[(SFX, "uti_adulto"), "oferta_acessivel_sus"] == pytest.approx(0.0)
    assert d.loc[(SFX, "uti_adulto"), "deficit"] == pytest.approx(4.0)  # 2000 hab × 2/1000
    assert d.loc[(SSA, "uti_adulto"), "existente_local_sus"] == 10
    assert (t["deficit_leitos"].t_oferta_min == 120).all()
    assert "fora_do_escopo" not in set(t["deficit_leitos"].tipo_leito)
    assert len(t["deficit_leitos"]) == 3 * len(TIPOS_LEITO)


def test_estabelecimentos_and_leitos(cfg_fixture):
    t = tabelas_gold(cfg_fixture)
    e = t["estabelecimentos_hospitalares"].iloc[0]
    assert e.leitos_sus == 30 and e.leitos_total == 30
    le = t["leitos_existentes"].set_index(["cod_ibge", "tipo_leito"])
    assert le.loc[(SSA, "clinico"), "qtd_sus"] == 15


def test_fluxo_internacoes_by_year(cfg_fixture):
    f = tabelas_gold(cfg_fixture)["fluxo_internacoes"]
    assert set(f.ano) == {2024} and f.internacoes.sum() == 2


def test_checks_pass_on_fixture(cfg_fixture):
    checks_gold(cfg_fixture, tabelas_gold(cfg_fixture))


def test_checks_fail_on_wrong_count(cfg_fixture):
    t = tabelas_gold(cfg_fixture)
    t["dim_municipio"] = t["dim_municipio"].iloc[:2]
    with pytest.raises(GoldCheckError):
        checks_gold(cfg_fixture, t)


def test_checks_fail_on_orphan(cfg_fixture):
    t = tabelas_gold(cfg_fixture)
    t["leitos_existentes"].loc[0, "cod_ibge"] = "2999999"
    with pytest.raises(GoldCheckError):
        checks_gold(cfg_fixture, t)


def test_checks_fail_on_incomplete_matrix(cfg_fixture):
    t = tabelas_gold(cfg_fixture)
    t["matriz_tempo_viagem"] = t["matriz_tempo_viagem"].iloc[1:]
    with pytest.raises(GoldCheckError):
        checks_gold(cfg_fixture, t)


def test_custo_obra_uma_linha_por_padrao_mes_mais_recente(cfg_fixture):
    import pandas as pd

    from hospital_siting.core.storage import silver_path, write_parquet

    write_parquet(
        pd.DataFrame(
            {
                "fonte": ["SINAPI", "SINAPI"],
                "padrao": ["média UF"] * 2,
                "valor_m2": [1000.0, 2000.0],
                "mes": ["2024-12", "2026-09"],
            }
        ),
        silver_path(cfg_fixture, "custo_obra_m2"),
    )
    obra = tabelas_gold(cfg_fixture)["custo_obra_m2"]
    assert len(obra) == 1 and obra.iloc[0].mes_origem == "2026-09" and obra.iloc[0].valor_m2 == pytest.approx(2000.0)


def test_fluxo_internacoes_informa_meses_por_ano(cfg_fixture):
    f = tabelas_gold(cfg_fixture)["fluxo_internacoes"]
    assert (f.n_competencias == 1).all()  # fixture: só 2024-12
