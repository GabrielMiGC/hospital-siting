import pytest

from hospital_siting.schemas.silver import TIPOS_LEITO
from hospital_siting.seeds import SEEDS, load, necessidade


@pytest.mark.parametrize("nome", SEEDS)
def test_seed_has_provenance(nome, cfg_repo):
    df = load(cfg_repo, nome)
    assert len(df) > 0
    for col in ("fonte", "documento", "pagina_ou_artigo"):
        assert df[col].fillna("").str.strip().ne("").all(), col


def test_necessidade_cobre_todos_os_tipos_em_cada_cenario(cfg_repo):
    df = load(cfg_repo, "necessidade_leitos")
    for cen, g in df.groupby("cenario"):
        assert sorted(g.tipo_leito) == sorted(TIPOS_LEITO), cen
    assert (df.leitos_por_mil_hab > 0).all()


def test_necessidade_usa_cenario_configurado(cfg_repo):
    nec = necessidade(cfg_repo)
    assert len(nec) == len(TIPOS_LEITO) and set(nec.cenario.astype(int)) == {2}


def test_arquetipos_cumulativos(cfg_repo):
    a = (
        load(cfg_repo, "arquetipos")
        .pivot_table(index="porte", columns="tipo_leito", values="leitos", aggfunc="sum")
        .fillna(0)
    )
    assert a.loc[["H1", "H2", "H3", "H4"]].sum(axis=1).is_monotonic_increasing
    assert a.loc["H1", ["uti_adulto", "uti_neo_ped"]].sum() == 0 and a.loc["H2", "uti_adulto"] > 0


def test_mapas_apontam_tipos_validos(cfg_repo):
    validos = set(TIPOS_LEITO) | {"fora_do_escopo"}
    cnes = load(cfg_repo, "mapa_leitos_cnes")
    sih = load(cfg_repo, "mapa_espec_sih")
    assert set(cnes.tipo_leito) <= validos and set(sih.tipo_leito) <= validos
    assert cnes.cod_leito.str.fullmatch(r"\d{2}").all() and cnes.cod_leito.is_unique
    assert sih.espec.str.fullmatch(r"\d{2}").all() and sih.espec.is_unique


def test_equipe_unidades_validas(cfg_repo):
    eq = load(cfg_repo, "dimensionamento_equipe")
    assert set(eq.unidade) <= {"por_leito", "por_sala", "por_unidade_fixa"}
    assert eq.cbo.str.fullmatch(r"\d{6}").all() and (eq.razao > 0).all()
