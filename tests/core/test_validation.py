import json

import pandas as pd
import pandera.errors
import pytest

from hospital_siting.core.meta import record_run
from hospital_siting.core.validation import validate, warn_if
from hospital_siting.schemas.silver import MUNICIPIO


def _linhas(cfg, nome):
    return [json.loads(x) for x in (cfg.data_dir / f"meta/{nome}.jsonl").read_text().splitlines()]


def test_validate_records_fail_and_raises(cfg_tmp):
    bad = pd.DataFrame(
        {"cod_ibge": ["123"], "nome": ["x"], "uf": ["BA"], "populacao": pd.array([0], dtype="Int64"),
         "ano_populacao": [2022], "pib": [1.0], "ano_pib": [2021]}
    )
    with pytest.raises(pandera.errors.SchemaErrors):
        validate(cfg_tmp, MUNICIPIO, bad, "municipio")
    assert _linhas(cfg_tmp, "validacoes")[-1]["status"] == "fail"


def test_validate_records_pass(cfg_tmp):
    ok = pd.DataFrame(
        {"cod_ibge": ["2927408"], "nome": ["Salvador"], "uf": ["BA"], "populacao": pd.array([2417678], dtype="Int64"),
         "ano_populacao": [2022], "pib": [1.0], "ano_pib": [2021]}
    )
    validate(cfg_tmp, MUNICIPIO, ok, "municipio")
    assert _linhas(cfg_tmp, "validacoes")[-1]["status"] == "pass"


def test_warn_if_and_record_run(cfg_tmp):
    warn_if(cfg_tmp, True, "receita_municipal", "sem_receita", "2930709")
    warn_if(cfg_tmp, False, "receita_municipal", "outro", "")
    v = _linhas(cfg_tmp, "validacoes")
    assert len(v) == 1 and v[0]["status"] == "warn" and v[0]["detalhe"] == "2930709"
    record_run(cfg_tmp, "ibge", "ok", {"linhas": 417})
    assert _linhas(cfg_tmp, "execucoes")[0]["extra"] == {"linhas": 417}
