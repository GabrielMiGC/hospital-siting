from pathlib import Path

import pandas as pd
import pytest

from hospital_siting.core.ids import build_ibge6_map
from hospital_siting.schemas.silver import SIH_AGG
from hospital_siting.sih.transform import agregar_rd

FIX = Path(__file__).parents[1] / "fixtures" / "sih"

RD_FIX = pd.read_csv(
    FIX / "rd_fix.csv",
    dtype={"MUNIC_RES": str, "MUNIC_MOV": str, "ESPEC": str, "COD_IDADE": str},
)
MAPA_ESPEC_FIX = pd.read_csv(FIX / "mapa_espec_fix.csv", dtype=str)
MAPA6 = build_ibge6_map(["2927408", "2910800", "2930709"])


def test_agregar_rd_groups_and_sums():
    out, _ = agregar_rd(RD_FIX, MAPA6, MAPA_ESPEC_FIX, "2026-06")
    r = out.query("cod_ibge_residencia=='2930709' and cod_ibge_ocorrencia=='2910800' and tipo_leito=='clinico'")
    assert r.internacoes.item() == 2 and r.valor_total.item() == pytest.approx(1500.0)
    SIH_AGG.validate(out)


def test_agregar_rd_discards_other_uf_and_invalid_with_counts():
    # RD_FIX: 1 AIH com MUNIC_RES 261160 (PE) e 1 com 290000 (código BA fora do mapa)
    out, desc = agregar_rd(RD_FIX, MAPA6, MAPA_ESPEC_FIX, "2026-06")
    assert desc == {"residencia_fora_uf": 1, "codigo_invalido": 1}
    assert out.cod_ibge_residencia.str.startswith("29").all()


def test_uti_faixa_by_age():
    out, _ = agregar_rd(RD_FIX, MAPA6, MAPA_ESPEC_FIX, "2026-06")
    assert set(out[out.diarias_uti > 0].faixa_uti) == {"adulto", "neo_ped"}


def test_faixa_nenhuma_sem_diarias_de_uti():
    out, _ = agregar_rd(RD_FIX, MAPA6, MAPA_ESPEC_FIX, "2026-06")
    sem_uti = out[out.diarias_uti == 0]
    assert len(sem_uti) > 0 and (sem_uti.faixa_uti == "nenhuma").all()
    assert "nenhuma" not in set(out[out.diarias_uti > 0].faixa_uti)


def test_idade_em_meses_e_anos_menor_que_18_e_neo_ped():
    # F: 3 anos (COD_IDADE 4); G: 6 meses (COD_IDADE 3). Ambos com UTI, mesmo grupo.
    out, _ = agregar_rd(RD_FIX, MAPA6, MAPA_ESPEC_FIX, "2026-06")
    r = out.query("cod_ibge_residencia=='2910800' and cod_ibge_ocorrencia=='2910800' and tipo_leito=='pediatrico'")
    assert r.faixa_uti.item() == "neo_ped"
    assert r.internacoes.item() == 2
    assert r.valor_total.item() == pytest.approx(7500.0)
    assert r.diarias_uti.item() == 13
    assert r.valor_uti.item() == pytest.approx(5200.0)


def test_idade_18_anos_com_uti_e_adulto():
    # E: 58 anos (UTI); K: exatamente 18 anos (UTI). Ambos com ESPEC 03, mesmo grupo.
    out, _ = agregar_rd(RD_FIX, MAPA6, MAPA_ESPEC_FIX, "2026-06")
    r = out.query("cod_ibge_residencia=='2927408' and cod_ibge_ocorrencia=='2927408' and tipo_leito=='clinico'")
    assert r.faixa_uti.item() == "adulto"
    assert r.internacoes.item() == 2
    assert r.valor_total.item() == pytest.approx(5500.0)
    assert r.diarias_uti.item() == 8


def test_espec_mapeada_e_fora_do_mapa_vira_fora_do_escopo():
    out, _ = agregar_rd(RD_FIX, MAPA6, MAPA_ESPEC_FIX, "2026-06")
    assert set(out.tipo_leito) == {"clinico", "cirurgico", "obstetrico", "pediatrico", "fora_do_escopo"}
    fora = out[out.tipo_leito == "fora_do_escopo"]
    # H: ESPEC "99", ausente do mapa; não é descarte, só fica fora do escopo
    assert fora.internacoes.sum() == 1 and fora.valor_total.item() == pytest.approx(300.0)
    assert out.query("tipo_leito=='cirurgico'").internacoes.item() == 1
    assert out.query("tipo_leito=='obstetrico'").internacoes.item() == 1


def test_conserva_aihs_validas():
    out, desc = agregar_rd(RD_FIX, MAPA6, MAPA_ESPEC_FIX, "2026-06")
    assert out.internacoes.sum() == len(RD_FIX) - sum(desc.values()) == 9
    assert (out.competencia == "2026-06").all()
