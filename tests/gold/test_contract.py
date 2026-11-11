import pytest
from sqlalchemy import create_engine, text

from hospital_siting.gold.build import tabelas_gold
from hospital_siting.gold.contract import aplicar_ddl, verificar
from hospital_siting.gold.load import carregar

pytestmark = pytest.mark.db

ADMIN_DSN = "postgresql+psycopg://postgres:postgres@localhost:5432/postgres"
TEST_DSN = "postgresql+psycopg://postgres:postgres@localhost:5432/hs_test"


@pytest.fixture(scope="module")
def engine():
    try:
        admin = create_engine(ADMIN_DSN, isolation_level="AUTOCOMMIT")
        with admin.connect() as c:
            if not c.execute(text("select 1 from pg_database where datname='hs_test'")).scalar():
                c.execute(text("create database hs_test"))
        admin.dispose()
    except Exception as e:  # noqa: BLE001
        pytest.skip(f"PostgreSQL indisponível: {e}")
    eng = create_engine(TEST_DSN)
    aplicar_ddl(eng)
    yield eng
    eng.dispose()


def test_reload_is_idempotent(cfg_fixture, engine):
    t = tabelas_gold(cfg_fixture)
    carregar(cfg_fixture, t, engine)
    carregar(cfg_fixture, t, engine)
    with engine.connect() as c:
        assert c.execute(text("select count(*) from gold.dim_municipio")).scalar() == 3
        assert c.execute(text("select count(*) from gold.matriz_tempo_viagem")).scalar() == 9
        srid = c.execute(text("select distinct st_srid(geom_limite) from gold.dim_municipio")).scalar()
        assert srid == 4674
        assert c.execute(text("select geometrytype(geom_limite) from gold.dim_municipio limit 1")).scalar() == (
            "MULTIPOLYGON"
        )


def test_contract_matches_ddl(cfg_fixture, engine):
    carregar(cfg_fixture, tabelas_gold(cfg_fixture), engine)
    assert verificar(engine) == []
