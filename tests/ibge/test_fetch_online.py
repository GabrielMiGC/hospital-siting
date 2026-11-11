import pytest
from hospital_siting.ibge.pipeline import run

from hospital_siting.core.storage import read_parquet, silver_path


@pytest.mark.online
def test_run_ba_has_417(cfg_repo):
    run(cfg_repo)
    assert len(read_parquet(silver_path(cfg_repo, "municipio"))) == 417
