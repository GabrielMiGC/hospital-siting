"""Pipeline bronze/silver do domínio IBGE."""

from __future__ import annotations

from hospital_siting.core.config import Config
from hospital_siting.core.meta import record_run, record_validation
from hospital_siting.core.storage import bronze_path, silver_path, write_parquet
from hospital_siting.core.validation import validate
from hospital_siting.ibge.fetch import geometrias, sidra
from hospital_siting.ibge.transform import geo_to_municipio_geo, regioes, sidra_to_municipio
from hospital_siting.schemas.silver import MUNICIPIO, REGIAO_SAUDE


def run(cfg: Config) -> None:
    """Materializa população, PIB, geometrias e regiões de saúde."""
    try:
        pop_raw, pib_raw = sidra(cfg)
        limites, sedes, regioes_raw, macros = geometrias(cfg)

        for nome, frame in (
            ("populacao_sidra", pop_raw),
            ("pib_sidra", pib_raw),
            ("limites", limites),
            ("sedes", sedes),
            ("regioes_saude", regioes_raw),
            ("macrorregioes_saude", macros),
        ):
            write_parquet(frame, bronze_path(cfg, "ibge", nome))

        municipio = validate(
            cfg,
            MUNICIPIO,
            sidra_to_municipio(pop_raw, pib_raw, cfg.cod_uf),
            "municipio",
        )
        municipio_geo = geo_to_municipio_geo(limites, sedes)
        record_validation(
            cfg,
            "municipio_geo",
            "schema:municipio_geo",
            "pass",
            f"{len(municipio_geo)} linhas",
        )
        regiao_saude = validate(
            cfg,
            REGIAO_SAUDE,
            regioes(sedes, regioes_raw, macros),
            "regiao_saude",
        )

        write_parquet(municipio, silver_path(cfg, "municipio"))
        write_parquet(municipio_geo, silver_path(cfg, "municipio_geo"))
        write_parquet(regiao_saude, silver_path(cfg, "regiao_saude"))
        record_run(
            cfg,
            "ibge",
            "pass",
            {
                "municipios": len(municipio),
                "geometrias": len(municipio_geo),
                "regioes": len(regiao_saude),
            },
        )
    except Exception as exc:
        record_run(cfg, "ibge", "fail", {"erro": str(exc)})
        raise
