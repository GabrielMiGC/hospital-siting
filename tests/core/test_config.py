import pytest

from hospital_siting.core.config import load_config


def test_load_config_defaults(monkeypatch):
    monkeypatch.delenv("HS_DATA_DIR", raising=False)
    cfg = load_config()
    assert cfg.uf == "BA" and cfg.cod_uf == "29" and cfg.n_municipios == 417
    assert cfg.params["pct_receita_municipal"] == 0.20
    assert cfg.params["t_oferta_min"] == 120


def test_env_overrides_data_dir(tmp_path, monkeypatch):
    monkeypatch.setenv("HS_DATA_DIR", str(tmp_path))
    assert load_config().data_dir == tmp_path


def test_unknown_uf_raises():
    with pytest.raises(KeyError):
        load_config(uf="XX")
