import pandas as pd

from hospital_siting.core.storage import (
    bronze_path,
    fetch_to_raw,
    read_parquet,
    save_raw,
    silver_path,
    write_parquet,
)


def test_save_raw_is_idempotent(cfg_tmp):
    a = save_raw(cfg_tmp, "ibge", "2022", "x.csv", b"abc", "http://u")
    b = save_raw(cfg_tmp, "ibge", "2022", "x.csv", b"abc", "http://u")
    assert a.novo and not b.novo and a.sha256 == b.sha256
    assert a.path.read_bytes() == b"abc"
    assert len((cfg_tmp.data_dir / "raw/ibge/manifest.jsonl").read_text().splitlines()) == 1


def test_save_raw_new_content_is_new_entry(cfg_tmp):
    save_raw(cfg_tmp, "ibge", "2022", "x.csv", b"abc", "http://u")
    c = save_raw(cfg_tmp, "ibge", "2022", "x.csv", b"abcd", "http://u")
    assert c.novo
    assert len((cfg_tmp.data_dir / "raw/ibge/manifest.jsonl").read_text().splitlines()) == 2


def test_fetch_to_raw_skips_request_when_cached(cfg_tmp, respx_mock):
    route = respx_mock.get("http://u/x.csv").respond(200, content=b"abc")
    first = fetch_to_raw(cfg_tmp, "ibge", "2022", "http://u/x.csv", "x.csv")
    second = fetch_to_raw(cfg_tmp, "ibge", "2022", "http://u/x.csv", "x.csv")
    assert route.call_count == 1
    assert first.novo and not second.novo and second.path.read_bytes() == b"abc"


def test_parquet_roundtrip_and_paths(cfg_tmp):
    p = silver_path(cfg_tmp, "municipio")
    assert p == cfg_tmp.data_dir / "silver/municipio.parquet" and p.parent.is_dir()
    assert bronze_path(cfg_tmp, "cnes", "lt_2609").parent.is_dir()
    df = pd.DataFrame({"a": [1, 2]})
    write_parquet(df, p)
    assert read_parquet(p).equals(df)
