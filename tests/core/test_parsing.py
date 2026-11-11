from pathlib import Path

import pytest

from hospital_siting.core.parsing import parse_brl, parse_ibge_number, read_dbf

FIXTURES = Path(__file__).parents[1] / "fixtures"


@pytest.mark.parametrize(
    "s,exp",
    [("1.234,56", 1234.56), ("R$ 2.345,00", 2345.0), ("", None), (None, None), (12.5, 12.5), ("-12,5", -12.5)],
)
def test_parse_brl(s, exp):
    assert parse_brl(s) == exp


@pytest.mark.parametrize("s", ["-", "..", "...", "X", "", None])
def test_parse_ibge_missing(s):
    assert parse_ibge_number(s) is None


@pytest.mark.parametrize("s,exp", [("2417678", 2417678.0), ("12.5", 12.5), (7, 7.0)])
def test_parse_ibge_number_values(s, exp):
    assert parse_ibge_number(s) == exp


def test_read_dbf_latin1():
    df = read_dbf(FIXTURES / "dbf/acentos.dbf")
    assert df["NOME"].iloc[0] == "São Félix"
