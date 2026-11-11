"""Adaptadores para os formatos reais encontrados na Task 15 (SIDRA 2296 e RAIS .txt)."""

import pandas as pd
import pytest

from hospital_siting.custos.rais import ler_vinculos
from hospital_siting.custos.sinapi import de_sidra
from hospital_siting.schemas.silver import CUSTO_OBRA_M2


def test_sinapi_de_sidra_usa_variavel_48_e_mes():
    linhas = pd.DataFrame({
        "V": ["1877.90", "1084.53", "1860.00", "..."],
        "D1C": ["29"] * 4,
        "D2C": ["48", "2119", "48", "48"],
        "D3C": ["202609", "202609", "202608", "202607"],
    })
    out = de_sidra(linhas)
    assert out.mes.tolist() == ["2026-08", "2026-09"]
    assert out.valor_m2.tolist() == [1860.0, 1877.9]
    assert set(out.fonte) == {"SINAPI"} and out.padrao.str.contains("SINAPI").all()
    CUSTO_OBRA_M2.validate(out)


def test_ler_vinculos_filtra_uf_e_cbo_em_blocos(tmp_path):
    txt = tmp_path / "RAIS_VINC_PUB_NORDESTE.txt"
    cab = "Bairros SP;CBO Ocupação 2002;Município;Vl Remun Dezembro Nom;Outra"
    linhas = [
        "0;223505;292740;4500,00;x",
        "0;223505;261160;9999,00;x",
        "0;999999;292740;1000,00;x",
        "0;322205;291080;2200,50;x",
    ]
    txt.write_bytes(("\n".join([cab, *linhas]) + "\n").encode("latin-1"))
    out = ler_vinculos(txt, "29", ["223505", "322205"], chunksize=2)
    assert len(out) == 2
    assert set(out["CBO Ocupação 2002"]) == {"223505", "322205"}
    assert list(out.columns) == ["CBO Ocupação 2002", "Município", "Vl Remun Dezembro Nom"]


def test_ler_vinculos_sem_colunas_falha(tmp_path):
    txt = tmp_path / "x.txt"
    txt.write_bytes(b"A;B\n1;2\n")
    with pytest.raises(ValueError):
        ler_vinculos(txt, "29", ["223505"])


def test_ler_vinculos_layout_2024_virgula_e_ponto_decimal(tmp_path):
    arq = tmp_path / "RAIS_VINC_PUB_NORDESTE.COMT"
    cab = '"Bairros SP - Código","CBO 2002 Ocupação - Código","Município - Código","Vl Rem Dezembro Nom"'
    linhas = ['999997,223505,292740,4500.50', '999997,223505,261160,9999.00', '999997,322205,291080,2200.00']
    arq.write_bytes(("\n".join([cab, *linhas]) + "\n").encode("latin-1"))
    out = ler_vinculos(arq, "29", ["223505", "322205"])
    assert list(out.columns) == ["CBO Ocupação 2002", "Município", "Vl Remun Dezembro Nom"]
    assert sorted(out["Vl Remun Dezembro Nom"].tolist()) == [2200.0, 4500.5]
