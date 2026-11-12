import pandas as pd
import pytest

from hospital_siting.core.ids import build_ibge6_map, to_ibge7


def test_build_ibge6_map_and_convert():
    m = build_ibge6_map(["2927408", "2910800"])
    assert m == {"292740": "2927408", "291080": "2910800"}
    out = to_ibge7(pd.Series(["292740", "290000", "260000"]), m)
    assert out.tolist()[0] == "2927408" and out.isna().tolist()[1:] == [True, True]


def test_to_ibge7_accepts_ints_and_7_digits():
    m = build_ibge6_map(["2927408"])
    out = to_ibge7(pd.Series([292740, "2927408", None]), m)
    assert out.tolist()[:2] == ["2927408", "2927408"] and pd.isna(out.iloc[2])


def test_build_ibge6_map_collision():
    with pytest.raises(ValueError):
        build_ibge6_map(["2927408", "2927409"])
