from hospital_siting.core.meta import record_run, record_validation
from hospital_siting.core.storage import save_raw
from hospital_siting.docs_page import render


def test_render_includes_sources_and_checks(cfg_tmp, tmp_path):
    save_raw(cfg_tmp, "ibge", "2025", "pop.json", b"[]", "https://apisidra.ibge.gov.br/values/t/6579")
    record_validation(cfg_tmp, "municipio", "schema:municipio", "pass", "417 linhas")
    record_validation(cfg_tmp, "receita_municipal", "sem_receita", "warn", "2930709")
    record_run(cfg_tmp, "gold", "ok", {"data_base": "2026-09", "municipios": 417})
    html = render(cfg_tmp, tmp_path / "index.html").read_text(encoding="utf-8")
    assert "Avaliado e descartado" in html and "Spark" in html and "Great Expectations" in html
    assert "municipio" in html and "pass" in html and "warn" in html
    assert "apisidra.ibge.gov.br" in html
    assert "2026-09" in html
    assert "<script" not in html.lower()


def test_render_without_metadata(cfg_tmp, tmp_path):
    html = render(cfg_tmp, tmp_path / "index.html").read_text(encoding="utf-8")
    assert "Ainda não executado" in html
