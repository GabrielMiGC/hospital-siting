import pandas as pd
import pytest

from hospital_siting.cnes.transform import estabelecimentos, leitos
from hospital_siting.core.ids import build_ibge6_map
from hospital_siting.schemas.silver import CNES_ESTABELECIMENTO, CNES_LEITOS, TIPOS_LEITO

COMP = "2026-09"
MAPA6 = build_ibge6_map(["2927408", "2910800", "2930709"])

# ST: uma linha por estabelecimento. Hospitais: 05, 07, 15, 62. Fora do escopo: 01 (posto), 22 (consultório).
ST_FIX = pd.DataFrame(
    {
        "CNES": ["2000001", "2000002", "2000003", "2000004", "2000005", "2000006"],
        "CODUFMUN": ["292740", "291080", "293070", "292740", "292740", "291080"],
        "TP_UNID": ["05", "07", "15", "62", "01", "22"],
        "NAT_JUR": ["1015", "2011", "3069", "4014", "1015", "2011"],
    }
)

# LT: uma linha por (CNES, CODLEITO). CODLEITO "99" não está no seed. CODUFMUN "290000" não está no mapa.
# QT_SUS vem como str em uma linha (formato DBF pode trazer numéricos como texto) e excede QT_EXIST (4 < 6).
LT_FIX = pd.DataFrame(
    {
        "CNES": ["2000001", "2000001", "2000002", "2000002", "2000003", "2000007"],
        "CODUFMUN": ["292740", "292740", "291080", "291080", "293070", "290000"],
        "CODLEITO": ["03", "02", "05", "99", "01", "03"],
        "TP_LEITO": ["1", "2", "3", "4", "1", "1"],
        "QT_EXIST": [10, 5, 8, 3, 4, 7],
        "QT_CONTR": [0, 0, 0, 0, 0, 0],
        "QT_SUS": [6, 5, 4, 1, "6", 7],
        "QT_NSUS": [4, 0, 4, 2, 0, 0],
    }
)

MAPA_LEITOS_FIX = pd.DataFrame(
    {
        "cod_leito": ["01", "02", "03", "04", "05", "06"],
        "descricao": [
            "Clínico",
            "Cirúrgico",
            "Obstétrico",
            "Pediátrico",
            "UTI adulto",
            "UTI neonatal/pediátrica",
        ],
        "tipo_leito": list(TIPOS_LEITO),
    }
)


def test_estabelecimentos_keeps_only_hospital_types():
    out = estabelecimentos(ST_FIX, MAPA6, "2026-09")
    assert set(out.tipo_unidade) <= {"05", "07", "15", "62"}
    assert set(out.cnes) == {"2000001", "2000002", "2000003", "2000004"}
    CNES_ESTABELECIMENTO.validate(out)


def test_leitos_maps_types_and_flags_unknown(cfg_tmp):
    out = leitos(LT_FIX, MAPA6, MAPA_LEITOS_FIX, "2026-09")
    assert set(out.tipo_leito) <= set(TIPOS_LEITO) | {"fora_do_escopo"}
    assert (out.qtd_sus <= out.qtd_total).all()
    # LT_FIX contém o código "99", que não está no seed
    assert (out[out.cod_leito == "99"].tipo_leito == "fora_do_escopo").all()
    CNES_LEITOS.validate(out)


def test_leitos_drops_unmapped_municipio():
    # LT_FIX contém CODUFMUN "290000"
    assert leitos(LT_FIX, MAPA6, MAPA_LEITOS_FIX, "2026-09").cod_ibge.notna().all()


@pytest.mark.parametrize(
    ("nat_jur", "esperado"),
    [
        ("1015", "publica"),
        ("1244", "publica"),
        ("2011", "privada"),
        ("2305", "privada"),
        ("3069", "filantropica"),
        ("3999", "filantropica"),
        ("4014", "outra"),
        ("9999", "outra"),
    ],
)
def test_natureza_a_partir_de_nat_jur(nat_jur, esperado):
    st = pd.DataFrame({"CNES": ["2000001"], "CODUFMUN": ["292740"], "TP_UNID": ["05"], "NAT_JUR": [nat_jur]})
    out = estabelecimentos(st, MAPA6, COMP)
    assert out.natureza.tolist() == [esperado]
    CNES_ESTABELECIMENTO.validate(out)


def test_estabelecimentos_leitos_total_soma_qtd_total_por_cnes():
    lt_out = leitos(LT_FIX, MAPA6, MAPA_LEITOS_FIX, COMP)
    out = estabelecimentos(ST_FIX, MAPA6, COMP, leitos=lt_out)
    # 2000001: 10 + 5; 2000002: 8 + 3 (inclui o código fora_do_escopo); 2000003: 4; 2000004: sem leitos -> 0
    assert dict(zip(out.cnes, out.leitos_total, strict=True)) == {
        "2000001": 15,
        "2000002": 11,
        "2000003": 4,
        "2000004": 0,
    }
    # o soma por cnes da saída de leitos() bate com leitos_total
    esperado = lt_out.groupby("cnes")["qtd_total"].sum().reindex(out.cnes, fill_value=0)
    assert out.set_index("cnes")["leitos_total"].tolist() == esperado.tolist()
    CNES_ESTABELECIMENTO.validate(out)
    # sem o argumento leitos, leitos_total é 0 para todos
    assert (estabelecimentos(ST_FIX, MAPA6, COMP).leitos_total == 0).all()


def test_leitos_qtd_sus_limitado_a_qtd_total():
    out = leitos(LT_FIX, MAPA6, MAPA_LEITOS_FIX, COMP)
    # QT_SUS "6" > QT_EXIST 4: qtd_sus cai para 4
    linha = out[out.cnes == "2000003"]
    assert linha.qtd_total.tolist() == [4]
    assert linha.qtd_sus.tolist() == [4]
    # QT_SUS 6 <= QT_EXIST 10: valor preservado
    preservada = out[(out.cnes == "2000001") & (out.cod_leito == "03")]
    assert preservada.qtd_sus.tolist() == [6]
    assert (out.qtd_sus <= out.qtd_total).all()
