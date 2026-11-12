from dataclasses import replace
from pathlib import Path

import pytest

from hospital_siting.core.config import load_config

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture
def cfg_tmp(tmp_path, monkeypatch):
    """Config real do repositório, com data_dir isolado num diretório temporário."""
    monkeypatch.delenv("HS_DATA_DIR", raising=False)
    return replace(load_config(), data_dir=tmp_path)


@pytest.fixture
def cfg_repo(monkeypatch):
    """Config do repositório sem alterações (seeds reais)."""
    monkeypatch.delenv("HS_DATA_DIR", raising=False)
    return load_config()
