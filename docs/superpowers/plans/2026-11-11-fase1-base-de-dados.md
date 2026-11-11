# Fase 1 — Base de Dados: Plano de Implementação

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Pipeline reproduzível que coleta, limpa, valida e carrega no PostgreSQL/PostGIS (schema `gold`) todos os dados que o modelo da Fase 2 consome, para a Bahia, parametrizado por UF.

**Architecture:** Pacote Python `hospital_siting` com um subpacote por domínio de fonte. Cada domínio separa I/O (`fetch.py`), transformação pura DataFrame→DataFrame (`transform.py`) e cola (`pipeline.py` com `run(cfg)`). Fluxo: `data/raw` (original + manifest) → `data/bronze` (Parquet) → `data/silver` (Parquet validado com Pandera) → Postgres `gold` + `meta`. Airflow e CLI chamam as mesmas funções `run(cfg)`.

**Tech Stack:** Python 3.12, uv, DuckDB, pandas, pyarrow, GeoPandas, geobr, Pandera, httpx, BeautifulSoup, datasus-dbc + dbfread, SQLAlchemy + psycopg + GeoAlchemy2, Typer, PostgreSQL 16 + PostGIS 3, OSRM, osmium, Apache Airflow (LocalExecutor), Docker Compose, ruff, pytest, respx, GitHub Actions.

**Spec:** `docs/superpowers/specs/2026-11-11-hospital-siting-design.md` (seções citadas como §N).

## Global Constraints

- Chave de município: código IBGE **7 dígitos**, `str`. DATASUS (6 dígitos) é convertido por lookup construído da lista IBGE da UF (nunca por cálculo de dígito verificador).
- SRID de todas as geometrias: **4674** (SIRGAS 2000).
- UF alvo vem de `config/settings.yaml` (`uf: BA`, `cod_uf: "29"`, `n_municipios: 417`). Nenhum módulo escreve "BA" ou "29" literal fora de config e fixtures.
- `data/` fora do git; `seeds/` e `contracts/` dentro.
- Coletores idempotentes: arquivo com mesmo sha256 já presente em `data/raw` → não baixa de novo.
- Silver guarda valores **nominais** com a sua data (competência/ano). Correção monetária (INCC para obra; IPCA para o resto; séries anuais a partir de dezembro do ano) só acontece no build da gold (Task 12).
- Testes de CI não acessam a rede. Testes que acessam fontes reais levam `@pytest.mark.online` e ficam fora do CI.
- Funções em `transform.py` são puras (sem I/O, sem rede, sem leitura de config global).
- Raspagem: respeitar `robots.txt`, user-agent `hospital-siting/0.1 (projeto de portfolio)` sem dados pessoais, ≥ 1 s entre requisições.
- Seeds manuais têm sempre as colunas `fonte, documento, pagina_ou_artigo, observacao`.
- CI: **lint (ruff) primeiro**, depois pytest.

## Review Focus

1. **Marcadores de ausência do IBGE/SIDRA** (`-`, `..`, `...`, `X`) devem virar `NULL`, nunca 0 nem erro → teste em Task 3.
2. **Códigos DATASUS inválidos/ignorados ou de outra UF** (ex.: `290000`, residência em PE) devem ser descartados com contagem registrada, sem colisão nem órfão → teste em Task 5.
3. **Reexecução** do pipeline não duplica arquivos raw nem linhas na gold → testes em Task 2 (`save_raw`) e Task 12 (reload).
4. **Encoding de DBF** (latin-1) com acentos ("São Félix") → teste em Task 2 (`read_dbf`).
5. **Números em formato brasileiro** (`1.234,56`, `R$ 2.345,00`, vazio) em planilhas SINAPI/CUB/SICONFI → teste em Task 2 (`parse_brl`).

---

## Execução com agentes (§13 da spec)

**Papéis**
- **Claude (orquestrador):** Tasks 1, 2, 10, 12, 14, 15; revisa e faz merge de todas; único dono de arquivos compartilhados.
- **Haiku 5.5 (testes):** em cada task delegada, escreve primeiro os testes listados no passo "Write the failing test" (e fixtures), no worktree da task, e commita. Disparado via ferramenta Agent com `model: haiku`.
- **Implementadores** (fazem os testes passarem):

| Task | Domínio | Agente | Comando |
|---|---|---|---|
| 3 | IBGE | Codex | A |
| 4 | CNES | Codex | A |
| 5 | SIH | agy Sonnet | B (`claude-sonnet-5-5-medium`) |
| 6 | SICONFI | agy Gemini | B (`gemini-3.8-flash-high`) |
| 7 | Índices + SIGTAP | agy Gemini | B (`gemini-4-argon-medium`) |
| 8 | Custos (SINAPI, CUB, SomaSUS, RAIS) | Codex | A |
| 9 | Rotas (OSRM) | agy Sonnet | B (`claude-sonnet-5-5-medium`) |
| 11 | 2SFCA + déficit | Codex | A |
| 13 | Airflow | agy Sonnet | B (`claude-sonnet-5-5-medium`) |

**Comando A (Codex):**
```bash
codex exec -m gpt-5.6-sol -s workspace-write -c sandbox_workspace_write.network_access=true \
  -C "D:/dev/hospital-siting-wt/<task>" -o "D:/dev/hospital-siting-wt/_logs/<task>.md" - < prompt-<task>.md
```

**Comando B (agy)**, executado com cwd no worktree:
```bash
cd "D:/dev/hospital-siting-wt/<task>" && agy -p "$(cat prompt-<task>.md)" --model <modelo> --mode accept-edits --sandbox > "../_logs/<task>.md"
```

**Isolamento**
- Worktree por task: `git worktree add D:/dev/hospital-siting-wt/<task> -b feat/<task> main` (feito por Claude, que também roda `uv sync` no worktree antes do disparo).
- Cada prompt contém: o texto integral da task deste plano, a seção Global Constraints, a lista **exata** de caminhos permitidos (os do bloco Files da task) e as regras:
  - não editar nada fora dos caminhos permitidos; em especial **nunca** `pyproject.toml`, `uv.lock`, `config/`, `contracts/`, `src/hospital_siting/core/`, `src/hospital_siting/schemas/`, `docker-compose.yml`;
  - se precisar de dependência nova ou mudança em arquivo compartilhado, **parar e relatar** no log final;
  - não fazer merge, rebase nem push; commitar só no próprio branch;
  - pronto = `uv run ruff check <caminhos>` e `uv run pytest <dir de testes da task> -m "not online"` passando.
- Máximo de **4 agentes simultâneos**.
- Claude revisa o diff (`git diff main...feat/<task> --stat` deve conter só caminhos permitidos), roda o CI local e faz merge em `main`.

**Ondas**
- Onda 0 (sequencial, Claude): Tasks 1 → 2 → 10.
- Onda 1 (paralelo): Tasks 3, 4, 5, 6, 7, 8, 9. Task 11 também pode começar (não depende de dados reais).
- Onda 2 (Claude): Task 12, depois Task 13 (agy) e Task 14.
- Onda 3 (Claude): Task 15 (execução real ponta a ponta).

---

### Task 1: Esqueleto do projeto, ambiente e CI

**Files:**
- Create: `pyproject.toml`, `.python-version` (3.12), `.gitignore`, `ruff.toml`, `README.md` (stub), `config/settings.yaml`, `docker-compose.yml`, `.env.example`, `.github/workflows/ci.yml`, `src/hospital_siting/__init__.py`, `src/hospital_siting/core/config.py`, `src/hospital_siting/cli.py`
- Test: `tests/core/test_config.py`

**Interfaces:**
- Produces:
  - `hospital_siting.core.config.Config` (dataclass frozen): `uf: str`, `cod_uf: str`, `n_municipios: int`, `data_base: str` (`"YYYY-MM"` ou `"auto"`), `data_dir: Path`, `seeds_dir: Path`, `pg_dsn: str`, `params: dict[str, Any]`.
  - `load_config(path: Path | None = None, uf: str | None = None) -> Config`: lê `config/settings.yaml`; `HS_DATA_DIR` e `HS_PG_DSN` do ambiente sobrescrevem; `uf` sobrescreve a UF ativa, buscando em `ufs:` no YAML.
  - CLI Typer: `python -m hospital_siting.cli run <dominio> [--uf BA]`, com `dominio` ∈ {ibge, cnes, sih, siconfi, indices, custos, rotas, gold, all}. Cada domínio importa `hospital_siting.<pacote>.pipeline.run(cfg)`.

`config/settings.yaml` contém: `uf: BA`; `ufs: {BA: {cod_uf: "29", n_municipios: 417}}`; `data_base: auto`; `sih_competencias: 36`; e `params:` com `t_oferta_min: 120`, `t_max_min: 180`, `t_full_min: 30`, `pct_receita_municipal: 0.20`, `ocupacao: 0.80`, `fator_osrm: 1.0`, `osm_buffer_km: 50`.

`pyproject.toml` já declara **todas** as dependências do Tech Stack (os agentes não podem adicionar), mais os grupos dev (ruff, pytest, respx) e o marcador `online` registrado. `docker-compose.yml` sobe só `postgis/postgis:16-3.4`, com volume nomeado `pgdata`, porta 5432 e init script `docker/postgres/init.sql`, que cria os schemas `gold` e `meta` e a extensão `postgis`.

`ci.yml` tem o job `lint` (`uv run ruff check .`) e o job `test` (`needs: lint`, `uv run pytest -m "not online"`).

- [ ] **Step 1: Write the failing test**

```python
def test_load_config_defaults(tmp_path, monkeypatch):
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
```

- [ ] **Step 2: Run** `uv run pytest tests/core/test_config.py -v`. Expected: FAIL (module not found).
- [ ] **Step 3: Implement** os arquivos listados.
- [ ] **Step 4: Run** `uv run ruff check . && uv run pytest -v`. Expected: PASS. Then `docker compose up -d` and `docker compose exec postgis psql -U postgres -c "\dn"`, expected to list `gold` and `meta`.
- [ ] **Step 5: Commit** `chore: esqueleto do projeto, config, compose e CI`.

---

### Task 2: Núcleo compartilhado e contratos

**Files:**
- Create: `src/hospital_siting/core/storage.py`, `core/ids.py`, `core/parsing.py`, `core/meta.py`, `core/validation.py`, `src/hospital_siting/schemas/silver.py`, `contracts/gold_schema.sql`, `contracts/VERSION` (`1.0.0`), `CHANGELOG.md`
- Test: `tests/core/test_storage.py`, `test_ids.py`, `test_parsing.py`, `test_validation.py`, `tests/schemas/test_silver.py`

**Interfaces:**
- Produces:
  - `core.storage`:
    - `RawFile` (dataclass): `fonte, ref, path: Path, sha256: str, url: str, coletado_em: datetime, novo: bool`.
    - `save_raw(cfg, fonte: str, ref: str, filename: str, content: bytes, url: str) -> RawFile`: grava em `data/raw/<fonte>/<ref>/<filename>` e acrescenta uma linha a `data/raw/<fonte>/manifest.jsonl`. Se o mesmo sha256 já existir, não regrava e devolve `novo=False`.
    - `fetch_to_raw(cfg, fonte, ref, url, filename, client: httpx.Client | None = None) -> RawFile`: se o arquivo já está no manifest, não faz requisição.
    - `bronze_path(cfg, fonte, nome) -> Path` e `silver_path(cfg, nome) -> Path`: criam os diretórios.
    - `write_parquet(df, path)` e `read_parquet(path)`: GeoParquet quando `df` é GeoDataFrame.
  - `core.ids`:
    - `build_ibge6_map(cod7: Iterable[str]) -> dict[str, str]`: levanta `ValueError` em colisão.
    - `to_ibge7(cod6: pd.Series, mapa: dict) -> pd.Series`: inválidos viram `NA`.
  - `core.parsing`:
    - `parse_brl(s: str | float | None) -> float | None`.
    - `parse_ibge_number(s) -> float | None`: `-`, `..`, `...`, `X` e vazio viram `None`.
    - `read_dbf(path: Path, encoding: str = "latin-1") -> pd.DataFrame`.
    - `decompress_dbc(src: Path, dst_dir: Path) -> Path`: usa `datasus_dbc`.
  - `core.meta`:
    - `record_validation(cfg, dataset: str, check: str, status: Literal["pass","warn","fail"], detalhe: str = "") -> None`: anexa a `data/meta/validacoes.jsonl`.
    - `record_run(cfg, dominio: str, status: str, extra: dict) -> None`: anexa a `data/meta/execucoes.jsonl`.
  - `core.validation`:
    - `validate(cfg, schema: pandera.DataFrameSchema, df, dataset: str) -> pd.DataFrame`: chama `schema.validate(df, lazy=True)` e registra `pass` ou `fail`. Em `fail`, registra o detalhe e relança `pandera.errors.SchemaErrors`.
    - `warn_if(cfg, cond: bool, dataset, check, detalhe)`.
  - `schemas.silver`: um `DataFrameSchema` por dataset silver, com as colunas abaixo. É o contrato entre a Onda 1 e a Task 12.

| Schema (`silver/<nome>.parquet`) | Colunas (tipo) e checks |
|---|---|
| `MUNICIPIO` | cod_ibge (str, 7 díg., único), nome (str), uf (str), populacao (Int64 > 0), ano_populacao (int), pib (float > 0, nullable), ano_pib (int) |
| `MUNICIPIO_GEO` | cod_ibge (str, único), geom_sede (Point), geom_limite (MultiPolygon); CRS 4674 |
| `REGIAO_SAUDE` | cod_ibge (único), cod_regiao_saude (str), nome_regiao_saude (str), cod_macrorregiao (str, nullable) |
| `CNES_ESTABELECIMENTO` | cnes (str 7, único), cod_ibge, tipo_unidade (str), natureza (∈ publica, privada, filantropica, outra), leitos_total (int ≥ 0), lat/lon (float, nullable), competencia (str YYYY-MM) |
| `CNES_LEITOS` | cnes, cod_ibge, cod_leito (str), tipo_leito (∈ TIPOS_LEITO ∪ {fora_do_escopo}), qtd_total (int ≥ 0), qtd_sus (int ≥ 0, ≤ qtd_total), competencia |
| `SIH_AGG` | cod_ibge_residencia, cod_ibge_ocorrencia, competencia, tipo_leito, internacoes (int > 0), valor_total (float ≥ 0), dias_permanencia (int ≥ 0), diarias_uti (int ≥ 0), valor_uti (float ≥ 0), faixa_uti (∈ adulto, neo_ped, nenhuma) |
| `RECEITA_MUNICIPAL` | cod_ibge, exercicio (int), receita_corrente (float > 0) |
| `INDICE` | indice (∈ IPCA, INCC), mes (str YYYY-MM), valor (float > 0); único (indice, mes) |
| `SIGTAP_PROCEDIMENTO` | co_procedimento (str 10), no_procedimento, valor_sh, valor_sp (float ≥ 0), competencia |
| `CUSTO_OBRA_M2` | fonte (∈ SINAPI, CUB), padrao (str), valor_m2 (float > 0), mes (str YYYY-MM) |
| `EQUIPAMENTO_AMBIENTE` | ambiente, equipamento, unidade (∈ por_leito, por_sala, por_hospital), quantidade_ref (float > 0), preco_ref (float > 0, nullable), fonte, mes |
| `SALARIO_OCUPACAO` | cbo (str 6), descricao, salario_medio (float > 0), ano (int) |
| `MATRIZ_TEMPO` | origem, destino (str 7), minutos_osrm (float ≥ 0, nullable), km (float ≥ 0, nullable); único (origem, destino) |

  `TIPOS_LEITO = ("clinico", "cirurgico", "obstetrico", "pediatrico", "uti_adulto", "uti_neo_ped")`, exportado de `schemas.silver`.
  - `contracts/gold_schema.sql`: DDL das tabelas da §8 e §8.1 da spec, com estas convenções de tipo: códigos `text`, dinheiro `numeric(14,2)`, contagens `integer`, geometrias `geometry(Point|MultiPolygon, 4674)`. Inclui as tabelas `meta.fontes`, `meta.execucoes` e `meta.validacoes`. `deficit_leitos` traz `necessidade, existente_local_sus, oferta_acessivel_sus, deficit`. `dim_municipio` traz `receita_disponivel boolean`. `matriz_tempo_viagem.minutos_osrm` é nullable.

- [ ] **Step 1: Write the failing tests**

```python
def test_save_raw_is_idempotent(cfg_tmp):
    a = save_raw(cfg_tmp, "ibge", "2022", "x.csv", b"abc", "http://u")
    b = save_raw(cfg_tmp, "ibge", "2022", "x.csv", b"abc", "http://u")
    assert a.novo and not b.novo and a.sha256 == b.sha256
    assert len((cfg_tmp.data_dir / "raw/ibge/manifest.jsonl").read_text().splitlines()) == 1

def test_fetch_to_raw_skips_request_when_cached(cfg_tmp, respx_mock):
    route = respx_mock.get("http://u/x.csv").respond(200, content=b"abc")
    fetch_to_raw(cfg_tmp, "ibge", "2022", "http://u/x.csv", "x.csv")
    fetch_to_raw(cfg_tmp, "ibge", "2022", "http://u/x.csv", "x.csv")
    assert route.call_count == 1

def test_build_ibge6_map_and_convert():
    m = build_ibge6_map(["2927408", "2910800"])
    assert m == {"292740": "2927408", "291080": "2910800"}
    out = to_ibge7(pd.Series(["292740", "290000", "260000"]), m)
    assert out.tolist()[0] == "2927408" and out.isna().tolist()[1:] == [True, True]

def test_build_ibge6_map_collision():
    with pytest.raises(ValueError):
        build_ibge6_map(["2927408", "2927409"])

@pytest.mark.parametrize("s,exp", [("1.234,56", 1234.56), ("R$ 2.345,00", 2345.0), ("", None), (None, None), (12.5, 12.5)])
def test_parse_brl(s, exp):
    assert parse_brl(s) == exp

@pytest.mark.parametrize("s", ["-", "..", "...", "X", ""])
def test_parse_ibge_missing(s):
    assert parse_ibge_number(s) is None

def test_read_dbf_latin1(tmp_path):
    # fixture tests/fixtures/dbf/acentos.dbf: 1 linha, campo NOME="São Félix" gravado em latin-1
    assert read_dbf(FIXTURES / "dbf/acentos.dbf")["NOME"].iloc[0] == "São Félix"

def test_validate_records_fail_and_raises(cfg_tmp):
    bad = pd.DataFrame({"cod_ibge": ["123"], "nome": ["x"], "uf": ["BA"], "populacao": [0], "pib": [1.0], "ano_populacao": [2022], "ano_pib": [2021]})
    with pytest.raises(pandera.errors.SchemaErrors):
        validate(cfg_tmp, MUNICIPIO, bad, "municipio")
    assert '"status": "fail"' in (cfg_tmp.data_dir / "meta/validacoes.jsonl").read_text()

def test_cnes_leitos_sus_le_total():
    df = pd.DataFrame({..., "qtd_total": [5], "qtd_sus": [6], ...})
    with pytest.raises(pandera.errors.SchemaErrors):
        CNES_LEITOS.validate(df, lazy=True)
```

`cfg_tmp` é uma fixture em `tests/conftest.py`: um `Config` com `data_dir=tmp_path`. A fixture `acentos.dbf` é gerada uma vez com a biblioteca `dbf` e commitada.

- [ ] **Step 2: Run** `uv run pytest tests/core tests/schemas -v`. Expected: FAIL.
- [ ] **Step 3: Implement** os módulos, os schemas e o DDL. Aplicar o DDL: `docker compose exec -T postgis psql -U postgres < contracts/gold_schema.sql`.
- [ ] **Step 4: Run** `uv run ruff check . && uv run pytest -v`. Expected: PASS. O DDL aplica sem erro.
- [ ] **Step 5: Commit** `feat(core): armazenamento raw idempotente, ids, parsing, validação e contratos`.

---

### Task 3: Domínio IBGE (população, PIB, malhas, regiões de saúde)

**Files:**
- Create: `src/hospital_siting/ibge/{__init__,fetch,transform,pipeline}.py`
- Test: `tests/ibge/test_transform.py`, `tests/ibge/test_fetch_online.py`, `tests/fixtures/ibge/*`

**Interfaces:**
- Consumes: Task 2 (`fetch_to_raw`, `parse_ibge_number`, `validate`, schemas `MUNICIPIO`, `MUNICIPIO_GEO`, `REGIAO_SAUDE`).
- Produces:
  - `transform.sidra_to_municipio(pop_raw: pd.DataFrame, pib_raw: pd.DataFrame, cod_uf: str) -> pd.DataFrame` (schema `MUNICIPIO`).
  - `transform.geo_to_municipio_geo(limites: gpd.GeoDataFrame, sedes: gpd.GeoDataFrame) -> gpd.GeoDataFrame`.
  - `transform.regioes(df: pd.DataFrame) -> pd.DataFrame`.
  - `pipeline.run(cfg) -> None`: grava as silvers `municipio`, `municipio_geo` e `regiao_saude`.
- Fontes:
  - população: SIDRA, Censo 2022 (tabela 9514) + estimativa mais recente (tabela 6579, último ano). `populacao` = estimativa mais recente quando houver; senão, o Censo.
  - PIB: SIDRA, tabela 5938, último ano.
  - malhas e sedes: `geobr.read_municipality(code_muni=cfg.uf)` e `geobr.read_municipal_seat`.
  - regiões de saúde: `geobr.read_health_region` (reprojetar para 4674 se vier diferente).

- [ ] **Step 1: Write the failing tests** (Haiku), com fixtures CSV mínimas no formato da API SIDRA (3 municípios: `2927408` Salvador, `2910800` Feira de Santana, `2930709` São Félix):

```python
def test_sidra_to_municipio_shapes_and_types():
    out = sidra_to_municipio(POP_FIX, PIB_FIX, "29")
    assert set(out.cod_ibge) == {"2927408", "2910800", "2930709"}
    assert out.populacao.dtype == "Int64" and (out.populacao > 0).all()
    MUNICIPIO.validate(out)

def test_sidra_missing_marker_becomes_null():
    # na fixture, o PIB de São Félix vem como "..."
    out = sidra_to_municipio(POP_FIX, PIB_FIX, "29")
    assert pd.isna(out.set_index("cod_ibge").loc["2930709", "pib"])

def test_sidra_filters_other_uf():
    # a fixture contém 1 linha de 2611606 (Recife)
    assert not sidra_to_municipio(POP_FIX, PIB_FIX, "29").cod_ibge.str.startswith("26").any()

def test_geo_crs_4674_and_one_row_per_municipio():
    out = geo_to_municipio_geo(LIM_FIX, SEDE_FIX)
    assert out.crs.to_epsg() == 4674 and out.cod_ibge.is_unique

@pytest.mark.online
def test_run_ba_has_417(cfg_real):
    run(cfg_real)
    assert len(read_parquet(silver_path(cfg_real, "municipio"))) == 417
```

- [ ] **Step 2: Run** `uv run pytest tests/ibge -m "not online" -v`. Expected: FAIL.
- [ ] **Step 3: Implement** `fetch.py`, `transform.py` e `pipeline.py`, com os nomes acima.
- [ ] **Step 4: Run** `uv run ruff check src/hospital_siting/ibge tests/ibge && uv run pytest tests/ibge -m "not online" -v`. Expected: PASS. Depois, localmente: `uv run pytest tests/ibge -m online`. Expected: PASS (417).
- [ ] **Step 5: Commit** `feat(ibge): população, PIB, malhas e regiões de saúde`.

---

### Task 4: Domínio CNES (estabelecimentos e leitos)

**Files:**
- Create: `src/hospital_siting/cnes/{__init__,fetch,transform,pipeline}.py`
- Test: `tests/cnes/test_transform.py`, `tests/cnes/test_fetch_online.py`, `tests/fixtures/cnes/*`

**Interfaces:**
- Consumes: Task 2 (`fetch_to_raw`, `decompress_dbc`, `read_dbf`, `build_ibge6_map`, `to_ibge7`, `validate`); silver `municipio` (Task 3) para o mapa 6→7; seed `seeds/mapa_leitos_cnes.csv` (Task 10).
- Produces:
  - `transform.estabelecimentos(st: pd.DataFrame, mapa6: dict, competencia: str) -> pd.DataFrame` (schema `CNES_ESTABELECIMENTO`). Só tipos hospitalares: `TP_UNID` ∈ {05 Hospital Geral, 07 Hospital Especializado, 15 Unidade Mista, 62 Hospital-Dia}. Natureza: mapeada de `NAT_JUR`/`ESFERA_A` para publica, privada, filantropica ou outra.
  - `transform.leitos(lt: pd.DataFrame, mapa6: dict, mapa_leitos: pd.DataFrame, competencia: str) -> pd.DataFrame` (schema `CNES_LEITOS`): `qtd_total = QT_EXIST`, `qtd_sus = QT_SUS`; tipo pelo seed (código ausente do seed → `fora_do_escopo` + aviso).
  - `fetch.latest_competencia(client) -> str`: lista o FTP `ftp.datasus.gov.br/dissemin/publicos/CNES/200508_/Dados/{ST,LT}/` e escolhe o maior `YYMM` disponível para a UF.
  - `pipeline.run(cfg) -> None`: grava as silvers `cnes_estabelecimento` e `cnes_leitos`.

- [ ] **Step 1: Write the failing tests** (Haiku), com DataFrames mínimos imitando as colunas ST/LT:

```python
def test_estabelecimentos_keeps_only_hospital_types():
    out = estabelecimentos(ST_FIX, MAPA6, "2026-09")
    assert set(out.tipo_unidade) <= {"05", "07", "15", "62"}
    CNES_ESTABELECIMENTO.validate(out)

def test_leitos_maps_types_and_flags_unknown(cfg_tmp):
    out = leitos(LT_FIX, MAPA6, MAPA_LEITOS_FIX, "2026-09")
    assert set(out.tipo_leito) <= set(TIPOS_LEITO) | {"fora_do_escopo"}
    assert (out.qtd_sus <= out.qtd_total).all()
    # LT_FIX contém o código "99", que não está no seed
    assert (out[out.cod_leito == "99"].tipo_leito == "fora_do_escopo").all()

def test_leitos_drops_unmapped_municipio():
    # LT_FIX contém CODUFMUN "290000"
    assert leitos(LT_FIX, MAPA6, MAPA_LEITOS_FIX, "2026-09").cod_ibge.notna().all()
```

- [ ] **Step 2: Run** `uv run pytest tests/cnes -m "not online" -v`. Expected: FAIL.
- [ ] **Step 3: Implement.**
- [ ] **Step 4: Run** `uv run ruff check src/hospital_siting/cnes tests/cnes && uv run pytest tests/cnes -m "not online" -v`. Expected: PASS. Online local: a silver `cnes_leitos` da BA tem > 0 linhas, e a soma de qtd_total fica entre 20.000 e 60.000 (sanidade).
- [ ] **Step 5: Commit** `feat(cnes): estabelecimentos hospitalares e leitos por tipo`.

---

### Task 5: Domínio SIH (internações agregadas)

**Files:**
- Create: `src/hospital_siting/sih/{__init__,fetch,transform,pipeline}.py`
- Test: `tests/sih/test_transform.py`, `tests/sih/test_fetch_online.py`, `tests/fixtures/sih/*`

**Interfaces:**
- Consumes: Task 2; silver `municipio`; seed `seeds/mapa_espec_sih.csv` (Task 10).
- Produces:
  - `transform.agregar_rd(rd: pd.DataFrame, mapa6: dict, mapa_espec: pd.DataFrame, competencia: str) -> tuple[pd.DataFrame, dict]`: devolve o DataFrame no schema `SIH_AGG` e as contagens de descarte `{"residencia_fora_uf": n, "codigo_invalido": n}`. Colunas usadas do RD: `MUNIC_RES`, `MUNIC_MOV`, `ESPEC`, `VAL_TOT`, `DIAS_PERM`, `UTI_MES_TO`, `VAL_UTI`, `IDADE`, `COD_IDADE`. `faixa_uti` = `neo_ped` se idade < 18 anos, `adulto` se ≥ 18 e houver diárias de UTI, `nenhuma` caso contrário.
  - `fetch.competencias(n: int, client) -> list[str]`: as `n` últimas competências publicadas (`RD{UF}{YYMM}.dbc` em `.../SIHSUS/200801_/Dados/`).
  - `pipeline.run(cfg) -> None`: processa `cfg` com `sih_competencias` (36) e grava a silver `sih_agg`; registra os descartes via `record_validation(... "warn" ...)`.

- [ ] **Step 1: Write the failing tests** (Haiku):

```python
def test_agregar_rd_groups_and_sums():
    out, _ = agregar_rd(RD_FIX, MAPA6, MAPA_ESPEC_FIX, "2026-06")
    r = out.query("cod_ibge_residencia=='2930709' and cod_ibge_ocorrencia=='2910800' and tipo_leito=='clinico'")
    assert r.internacoes.item() == 2 and r.valor_total.item() == pytest.approx(1500.0)
    SIH_AGG.validate(out)

def test_agregar_rd_discards_other_uf_and_invalid_with_counts():
    # RD_FIX: 1 AIH com MUNIC_RES 261160 (PE) e 1 com 290000
    out, desc = agregar_rd(RD_FIX, MAPA6, MAPA_ESPEC_FIX, "2026-06")
    assert desc == {"residencia_fora_uf": 1, "codigo_invalido": 1}
    assert out.cod_ibge_residencia.str.startswith("29").all()

def test_uti_faixa_by_age():
    out, _ = agregar_rd(RD_FIX, MAPA6, MAPA_ESPEC_FIX, "2026-06")
    assert set(out[out.diarias_uti > 0].faixa_uti) == {"adulto", "neo_ped"}
```

- [ ] **Step 2: Run** `uv run pytest tests/sih -m "not online" -v`. Expected: FAIL.
- [ ] **Step 3: Implement.** O processamento é feito uma competência por vez (DBF → agregação → Parquet parcial em bronze); a concatenação final é feita com DuckDB, para não carregar 36 meses de microdados em memória.
- [ ] **Step 4: Run** `uv run ruff check src/hospital_siting/sih tests/sih && uv run pytest tests/sih -m "not online" -v`. Expected: PASS.
- [ ] **Step 5: Commit** `feat(sih): internações agregadas por residência, ocorrência e tipo de leito`.

---

### Task 6: Domínio SICONFI (receita municipal)

**Files:**
- Create: `src/hospital_siting/siconfi/{__init__,fetch,transform,pipeline}.py`
- Test: `tests/siconfi/test_transform.py`, `tests/siconfi/test_fetch_online.py`, `tests/fixtures/siconfi/*`

**Interfaces:**
- Consumes: Task 2; silver `municipio`.
- Produces:
  - `fetch.dca(cfg, exercicio: int, client) -> list[dict]`: API `https://apidatalake.tesouro.gov.br/ords/siconfi/tt/dca`, com `an_exercicio`, `id_ente` por município e anexo `DCA-Anexo I-C` (receitas). Paginação por `hasMore`/`offset`.
  - `fetch.ultimo_exercicio_fechado(client) -> int`: o maior exercício em que ≥ 80% dos municípios da UF entregaram a DCA.
  - `transform.receita_corrente(itens: pd.DataFrame, cod_uf: str) -> pd.DataFrame` (schema `RECEITA_MUNICIPAL`): conta "Receitas Correntes", coluna "Receitas Brutas Realizadas" (ou o equivalente líquido de deduções, documentado no código). Município sem a linha fica ausente.
  - `pipeline.run(cfg) -> None`: grava a silver `receita_municipal` e registra um aviso com a lista de municípios sem receita.

- [ ] **Step 1: Write the failing tests** (Haiku):

```python
def test_receita_corrente_picks_right_account():
    out = receita_corrente(DCA_FIX, "29")
    assert out.set_index("cod_ibge").loc["2927408", "receita_corrente"] == pytest.approx(9_876_543_210.12)
    RECEITA_MUNICIPAL.validate(out)

def test_receita_corrente_missing_municipio_absent():
    # DCA_FIX não traz São Félix
    assert "2930709" not in set(receita_corrente(DCA_FIX, "29").cod_ibge)
```

- [ ] **Step 2–4:** como nas tasks anteriores, em `tests/siconfi`.
- [ ] **Step 5: Commit** `feat(siconfi): receita corrente municipal`.

---

### Task 7: Índices de correção (IPCA, INCC) e SIGTAP

**Files:**
- Create: `src/hospital_siting/indices/{__init__,fetch,transform,pipeline}.py`, `src/hospital_siting/core/money.py` (exceção autorizada dentro de `core/`: este arquivo pertence a esta task)
- Test: `tests/indices/test_transform.py`, `tests/indices/test_money.py`, `tests/fixtures/indices/*`

**Interfaces:**
- Consumes: Task 2.
- Produces:
  - `transform.ipca(sidra_raw) -> pd.DataFrame` (schema `INDICE`): SIDRA tabela 1737, variável número-índice (2266).
  - `transform.incc(raw) -> pd.DataFrame`: INCC-M (FGV) a partir de série pública. Fonte primária: SGS do Banco Central, série 192 (INCC-M, variação % mensal), convertida em número-índice encadeado com base 100 no primeiro mês.
  - `transform.sigtap(raw_zip_tables) -> pd.DataFrame` (schema `SIGTAP_PROCEDIMENTO`): arquivo `tb_procedimento.txt` da competência mais recente (layout de largura fixa conforme `tb_procedimento_layout.txt`).
  - `core.money.fator(indices: pd.DataFrame, indice: str, mes_origem: str, mes_base: str) -> float`.
  - `core.money.corrigir(valores: pd.Series, meses: pd.Series, indices, indice: str, mes_base: str) -> pd.Series`.
  - `core.money.mes_de_ano(ano: int) -> str`: devolve `f"{ano}-12"` (séries anuais).
  - `pipeline.run(cfg) -> None`: grava as silvers `indice` e `sigtap_procedimento`.

- [ ] **Step 1: Write the failing tests** (Haiku):

```python
IDX = pd.DataFrame({"indice": ["IPCA"]*3, "mes": ["2024-12", "2025-12", "2026-09"], "valor": [100.0, 105.0, 108.15]})

def test_fator():
    assert fator(IDX, "IPCA", "2024-12", "2026-09") == pytest.approx(1.0815)

def test_corrigir_series():
    out = corrigir(pd.Series([1000.0, 1000.0]), pd.Series(["2024-12", "2025-12"]), IDX, "IPCA", "2026-09")
    assert out.round(2).tolist() == [1081.50, 1030.0]

def test_fator_missing_month_raises():
    with pytest.raises(KeyError):
        fator(IDX, "IPCA", "2019-01", "2026-09")

def test_incc_chained_index_from_monthly_pct():
    out = incc(INCC_PCT_FIX)  # variações 1.0%, 0.5%
    assert out.valor.round(4).tolist() == [100.0, 101.0, 101.505]
```

- [ ] **Step 2–4:** como antes, em `tests/indices`.
- [ ] **Step 5: Commit** `feat(indices): IPCA, INCC, SIGTAP e correção monetária`.

---

### Task 8: Domínio de custos (SINAPI, CUB-BA, SomaSUS, RAIS)

**Pré-condição (Claude, antes de disparar):** ler o `robots.txt` e os termos de uso do SomaSUS. Se a raspagem for proibida ou inviável, o prompt da task troca o SomaSUS pelo fallback da §8.1 (RENEM/SIGEM + Banco de Preços em Saúde) e o teste `test_somasus_*` é renomeado para a fonte usada.

**Files:**
- Create: `src/hospital_siting/custos/{__init__,sinapi,cub,somasus,rais,pipeline}.py`
- Test: `tests/custos/test_sinapi.py`, `test_cub.py`, `test_somasus.py`, `test_rais.py`, `tests/fixtures/custos/*`

**Interfaces:**
- Consumes: Task 2 (`fetch_to_raw`, `parse_brl`, `validate`).
- Produces:
  - `sinapi.custo_m2(xls: pd.DataFrame, uf: str, mes: str) -> pd.DataFrame` (schema `CUSTO_OBRA_M2`, fonte `SINAPI`): custo médio m² da UF da planilha de custos de composições/projetos de referência; `padrao` = nome do projeto de referência.
  - `cub.custo_m2(tabela: pd.DataFrame, mes: str) -> pd.DataFrame` (fonte `CUB`): padrões comerciais/hospitalares disponíveis no Sinduscon-BA. Se o site não oferecer download estruturado, um seed `seeds/cub_ba.csv` com valores transcritos e fonte (aviso registrado).
  - `somasus.parse_ambiente(html: str) -> pd.DataFrame` → colunas de `EQUIPAMENTO_AMBIENTE` sem `mes`. `somasus.crawl(cfg, ambientes: list[str], client) -> pd.DataFrame`: uma requisição por ambiente, ≥ 1 s entre elas, HTML salvo em raw.
  - `rais.salarios(rais_vinc: pd.DataFrame, cbos: list[str], cod_uf: str, ano: int) -> pd.DataFrame` (schema `SALARIO_OCUPACAO`): mediana da remuneração média de dezembro, filtrada pela UF e pelos CBOs do seed de equipe (Task 10). Acesso aos microdados via Base dos Dados (`basedosdados`, tabela `br_me_rais.microdados_vinculos`) ou FTP do MTE (`ftp.mtps.gov.br/pdet/microdados/RAIS/`); o fetch filtra a UF antes de salvar.
  - `pipeline.run(cfg) -> None`: grava as silvers `custo_obra_m2`, `equipamento_ambiente` e `salario_ocupacao`; registra em `meta.validacoes` a cobertura de preço por ambiente obrigatório (UTI, centro cirúrgico, imagem, PS).

- [ ] **Step 1: Write the failing tests** (Haiku):

```python
def test_sinapi_custo_m2_brl_parsing():
    out = custo_m2(SINAPI_FIX, "BA", "2026-09")
    assert out.valor_m2.gt(0).all() and set(out.fonte) == {"SINAPI"}
    CUSTO_OBRA_M2.validate(out)

def test_somasus_parse_ambiente():
    out = parse_ambiente(SOMASUS_HTML_FIX)  # HTML salvo de 1 ambiente com 3 equipamentos
    assert len(out) == 3 and set(out.unidade) <= {"por_leito", "por_sala", "por_hospital"}

def test_rais_salarios_median_and_filters():
    out = salarios(RAIS_FIX, ["223505"], "29", 2024)
    assert out.set_index("cbo").loc["223505", "salario_medio"] == pytest.approx(4500.0)
    assert set(out.cbo) == {"223505"}
```

- [ ] **Step 2–4:** como antes, em `tests/custos`.
- [ ] **Step 5: Commit** `feat(custos): SINAPI, CUB-BA, equipamentos e salários`.

---

### Task 9: Rotas (OSRM e matriz de tempo de viagem)

**Files:**
- Create: `docker-compose.osrm.yml`, `docker/osrm/prepare.sh`, `src/hospital_siting/rotas/{__init__,fetch,matriz,pipeline}.py`
- Test: `tests/rotas/test_matriz.py`, `tests/rotas/test_osrm_online.py`

**Interfaces:**
- Consumes: Task 2; silver `municipio_geo` (Task 3).
- Produces:
  - `fetch.baixar_pbf(cfg) -> Path`: `https://download.geofabrik.de/south-america/brazil/nordeste-latest.osm.pbf` via `fetch_to_raw`.
  - `prepare.sh <pbf> <poly> <out_dir>`: `osmium extract -p <poly>` (polígono da UF + buffer de `osm_buffer_km`), depois `osrm-extract -p /opt/car.lua`, `osrm-partition`, `osrm-customize` (MLD), usando as imagens `osrm/osrm-backend` e `stefda/osmium-tool` via `docker run`.
  - `matriz.poligono_buffer(limites: gpd.GeoDataFrame, km: float) -> shapely.Geometry`: união dos limites, buffer em projeção métrica (EPSG:5880) e reprojeção para 4326.
  - `matriz.tabela_osrm(coords: list[tuple[float, float]], base_url: str, bloco: int = 100, client=None) -> tuple[np.ndarray, np.ndarray]`: chama `/table/v1/driving/` em blocos origem × destino com `annotations=duration,distance`. Devolve (segundos, metros), com `nan` onde a resposta é `null`.
  - `matriz.para_long(cods: list[str], seg, met) -> pd.DataFrame` (schema `MATRIZ_TEMPO`): minutos = seg/60, km = met/1000, diagonal = 0.
  - `pipeline.run(cfg) -> None`: sobe o OSRM com `docker compose -f docker-compose.osrm.yml up -d`, espera o health check, gera a matriz, grava a silver `matriz_tempo`, derruba o contêiner e registra como aviso os pares sem rota.

- [ ] **Step 1: Write the failing tests** (Haiku):

```python
def test_tabela_osrm_blocks_and_nulls(respx_mock):
    # 3 coordenadas, bloco=2 → 4 requisições; uma resposta contém null
    ...
    seg, met = tabela_osrm(COORDS3, "http://osrm:5000", bloco=2)
    assert seg.shape == (3, 3) and np.isnan(seg[0, 2])

def test_para_long_shape_and_diagonal():
    out = para_long(["a"*7, "b"*7], np.array([[0, 600], [660, 0]]), np.array([[0, 10000], [11000, 0]]))
    assert len(out) == 4 and out.query("origem==destino").minutos_osrm.eq(0).all()
    assert out.query("origem=='aaaaaaa' and destino=='bbbbbbb'").minutos_osrm.item() == 10.0

def test_poligono_buffer_grows():
    p = poligono_buffer(LIM_FIX, 50)
    assert p.area > LIM_FIX.to_crs(4326).union_all().area
```

- [ ] **Step 2–4:** como antes, em `tests/rotas`. Online local: matriz da BA com 417² = 173.889 linhas; mediana de `minutos_osrm` entre 300 e 900 (sanidade); Salvador → Feira de Santana entre 80 e 150 min.
- [ ] **Step 5: Commit** `feat(rotas): OSRM local e matriz de tempo de viagem`.

---

### Task 10: Seeds curados à mão

**Files:**
- Create: `seeds/necessidade_leitos.csv`, `seeds/mapa_leitos_cnes.csv`, `seeds/mapa_espec_sih.csv`, `seeds/dimensionamento_equipe.csv`, `seeds/custeio.csv`, `seeds/consorcio.csv`, `seeds/arquetipos.csv`, `seeds/README.md`, `src/hospital_siting/seeds.py`
- Test: `tests/test_seeds.py`

**Interfaces:**
- Produces:
  - `seeds.load(cfg, nome: str) -> pd.DataFrame`: lê o CSV e valida as colunas obrigatórias de proveniência.
  - Colunas, além das 4 de proveniência:
    - `necessidade_leitos`: tipo_leito, leitos_por_mil_hab.
    - `mapa_leitos_cnes`: cod_leito, descricao, tipo_leito.
    - `mapa_espec_sih`: espec, descricao, tipo_leito.
    - `dimensionamento_equipe`: setor, cbo, unidade, razao, turnos_dia, cobertura_dias.
    - `custeio`: porte, custeio_nao_pessoal_pct_pessoal.
    - `consorcio`: parametro, valor.
    - `arquetipos`: porte (H1–H4), tipo_leito, leitos, area_m2_ref.

**Responsável: Claude**, com pesquisa nas fontes primárias (Portaria GM/MS 1.631/2015, tabelas de tipos de leito do CNES, tabela ESPEC do SIH, RDC 7/2010, COFEN 543/2017, referências PNGC/ApuraSUS, legislação dos consórcios de Policlínicas da BA). Linha sem fonte verificável não entra; o item fica listado em `seeds/README.md` como pendência.

- [ ] **Step 1: Write the failing test**

```python
@pytest.mark.parametrize("nome", SEEDS)
def test_seed_has_provenance(nome, cfg_repo):
    df = load(cfg_repo, nome)
    assert df["fonte"].str.strip().ne("").all()

def test_necessidade_cobre_todos_os_tipos(cfg_repo):
    assert set(load(cfg_repo, "necessidade_leitos").tipo_leito) == set(TIPOS_LEITO)

def test_arquetipos_cumulativos(cfg_repo):
    a = load(cfg_repo, "arquetipos").pivot_table(index="porte", columns="tipo_leito", values="leitos", aggfunc="sum").fillna(0)
    assert a.sum(axis=1).is_monotonic_increasing
    assert a.loc["H1", ["uti_adulto", "uti_neo_ped"]].sum() == 0 and a.loc["H2", "uti_adulto"] > 0

def test_mapas_apontam_tipos_validos(cfg_repo):
    validos = set(TIPOS_LEITO) | {"fora_do_escopo"}
    assert set(load(cfg_repo, "mapa_leitos_cnes").tipo_leito) <= validos
    assert set(load(cfg_repo, "mapa_espec_sih").tipo_leito) <= validos
```

- [ ] **Step 2: Run** `uv run pytest tests/test_seeds.py -v`. Expected: FAIL.
- [ ] **Step 3: Pesquisar e preencher** os seeds; implementar `seeds.load`.
- [ ] **Step 4: Run** `uv run ruff check . && uv run pytest tests/test_seeds.py -v`. Expected: PASS.
- [ ] **Step 5: Commit** `feat(seeds): parâmetros curados com proveniência`.

---

### Task 11: Acessibilidade 2SFCA e déficit de leitos

**Files:**
- Create: `src/hospital_siting/modelo/{__init__,acesso}.py`
- Test: `tests/modelo/test_acesso.py`

**Interfaces:**
- Consumes: `TIPOS_LEITO` (Task 2).
- Produces:
  - `acesso.two_step_fca(oferta: pd.DataFrame, demanda: pd.DataFrame, tempo: pd.DataFrame, t_max: float) -> pd.DataFrame`.
    - `oferta`: cod_ibge, tipo_leito, leitos.
    - `demanda`: cod_ibge, populacao.
    - `tempo`: origem, destino, minutos (NaN = inalcançável).
    - Retorna cod_ibge, tipo_leito, oferta_acessivel, para todos os municípios da demanda × tipos presentes na oferta.
  - `acesso.deficit(demanda, necessidade: pd.DataFrame, oferta_local: pd.DataFrame, oferta_acessivel: pd.DataFrame) -> pd.DataFrame`: colunas cod_ibge, tipo_leito, necessidade, existente_local_sus, oferta_acessivel_sus, deficit. `necessidade = populacao × leitos_por_mil_hab / 1000`; ausências viram 0.

Algoritmo (não determinado pela assinatura):

```
para cada tipo:
  R_j = S_j / Σ_{k : t_kj ≤ T} P_k                  (passo 1; a origem conta com t = 0)
  A_i = Σ_{j : t_ij ≤ T} R_j                        (passo 2)
  oferta_acessivel_i = A_i × P_i
```

- [ ] **Step 1: Write the failing tests** (Haiku):

```python
DEM = pd.DataFrame({"cod_ibge": ["A", "B", "C"], "populacao": [1000, 1000, 2000]})
OF = pd.DataFrame({"cod_ibge": ["A"], "tipo_leito": ["uti_adulto"], "leitos": [10]})
T = matriz({("A","B"): 60, ("A","C"): 200, ("B","C"): 100})  # helper simétrico, diagonal 0

def test_2sfca_example():
    out = two_step_fca(OF, DEM, T, 120).set_index("cod_ibge").oferta_acessivel
    assert out.to_dict() == pytest.approx({"A": 5.0, "B": 5.0, "C": 0.0})

def test_2sfca_conserves_supply_when_all_reachable():
    assert two_step_fca(OF, DEM, T, 300).oferta_acessivel.sum() == pytest.approx(10.0)

def test_2sfca_nan_time_is_unreachable():
    t = T.copy(); t.loc[(t.origem=="A") & (t.destino=="B"), "minutos"] = np.nan
    t.loc[(t.origem=="B") & (t.destino=="A"), "minutos"] = np.nan
    out = two_step_fca(OF, DEM, t, 120).set_index("cod_ibge").oferta_acessivel
    assert out["A"] == pytest.approx(10.0) and out["B"] == 0.0

def test_deficit_math():
    nec = pd.DataFrame({"tipo_leito": ["uti_adulto"], "leitos_por_mil_hab": [2.0]})
    acc = two_step_fca(OF, DEM, T, 120)
    out = deficit(DEM, nec, OF.rename(columns={"leitos": "existente_local_sus"}), acc).set_index("cod_ibge")
    assert out.loc["C", "necessidade"] == 4.0 and out.loc["C", "deficit"] == 4.0
    assert out.loc["A", "deficit"] == pytest.approx(-3.0)
```

- [ ] **Step 2–4:** como antes, em `tests/modelo`. Desempenho: com 417 municípios × 6 tipos e uma matriz sintética completa, `two_step_fca` roda em < 2 s (teste `test_2sfca_performance_417`).
- [ ] **Step 5: Commit** `feat(modelo): acessibilidade 2SFCA e déficit de leitos`.

---

### Task 12: Build da camada gold e teste de contrato

**Files:**
- Create: `src/hospital_siting/gold/{__init__,build,load,contract}.py`
- Test: `tests/gold/test_build.py`, `tests/gold/test_contract.py` (o de contrato usa Postgres: marcador `db`, que roda no CI via service container `postgis/postgis:16-3.4`)
- Modify: `.github/workflows/ci.yml` (adiciona o service postgis ao job `test`)

**Interfaces:**
- Consumes: todas as silvers (schemas da Task 2), os seeds (Task 10), `core.money` (Task 7), `modelo.acesso` (Task 11).
- Produces:
  - `build.data_base_efetiva(cfg, indices: pd.DataFrame, custo_obra: pd.DataFrame) -> str`: com `cfg.data_base == "auto"`, devolve o mês mais recente do SINAPI que também exista no IPCA e no INCC.
  - `build.tabelas_gold(cfg) -> dict[str, pd.DataFrame | gpd.GeoDataFrame]`: monta as tabelas da §8/§8.1:
    - correção monetária: SIH e SIGTAP por competência; RAIS e SICONFI pelo dezembro do ano; obra pelo INCC; equipamentos pelo IPCA;
    - `valor_medio_internacao` por tipo de leito: valor por AIH e permanência; UTI por diária, separada por `faixa_uti`;
    - déficit via `two_step_fca` com `t_oferta_min`;
    - `receita_disponivel`.
  - `build.checks_gold(cfg, t: dict) -> None`, via `record_validation`:
    - fail: `dim_municipio` com exatamente `cfg.n_municipios` linhas;
    - fail: nenhum cod_ibge órfão em nenhuma tabela;
    - fail: matriz com n² linhas e diagonal 0;
    - fail: data-base única em todas as tabelas monetárias;
    - fail: `ST_IsValid` (via shapely `is_valid`) em todas as geometrias;
    - warn: municípios sem receita;
    - warn: sanidade do fluxo SIH (polos com maior internação recebida devem ter déficit ≤ 0 ou próximo; lista os que não têm).
  - `load.carregar(cfg, t: dict, engine) -> None`: numa transação, `TRUNCATE` das tabelas gold e insert. `meta.*` recebe os jsonl de `data/meta` e o manifest de raw, convertido em `meta.fontes`.
  - `contract.verificar(engine) -> list[str]`: compara `information_schema.columns` e `geometry_columns` com o DDL de `contracts/gold_schema.sql` e devolve a lista de divergências (vazia = ok).
  - `pipeline.run(cfg)` (em `gold/__init__.py` exporta `run`): build → checks → carregar → verificar.
  - `build.GoldCheckError(Exception)`: levantada por `checks_gold` quando alguma checagem `fail` falha, depois de registrar todas.
  - Entrada de tempo para o 2SFCA: `matriz_tempo` renomeando `minutos_osrm → minutos`, **sem** aplicar `fator_osrm` (o fator é da Fase 2, §7 da spec).

- [ ] **Step 1: Write the failing tests**:

```python
def test_tabelas_gold_from_fixture_silvers(cfg_fixture):   # silvers mínimas de 3 municípios em tests/fixtures/silver/
    t = tabelas_gold(cfg_fixture)
    assert len(t["dim_municipio"]) == 3
    assert set(t["deficit_leitos"].tipo_leito) <= set(TIPOS_LEITO)
    assert t["dim_municipio"].set_index("cod_ibge").loc["2930709", "receita_disponivel"] == False

def test_monetary_correction_applied(cfg_fixture):
    t = tabelas_gold(cfg_fixture)
    # fixture: 1 AIH de R$1000 na competência 2024-12; IPCA 2024-12=100, base=108.15
    assert t["valor_medio_internacao"].query("tipo_leito=='clinico'").valor_medio_aih.item() == pytest.approx(1081.50)

def test_checks_fail_on_wrong_count(cfg_fixture):
    t = tabelas_gold(cfg_fixture); t["dim_municipio"] = t["dim_municipio"].iloc[:2]
    with pytest.raises(GoldCheckError):
        checks_gold(cfg_fixture, t)

@pytest.mark.db
def test_reload_is_idempotent(cfg_fixture, engine):
    t = tabelas_gold(cfg_fixture); carregar(cfg_fixture, t, engine); carregar(cfg_fixture, t, engine)
    with engine.connect() as c:
        assert c.execute(text("select count(*) from gold.dim_municipio")).scalar() == 3

@pytest.mark.db
def test_contract_matches_ddl(cfg_fixture, engine):
    carregar(cfg_fixture, tabelas_gold(cfg_fixture), engine)
    assert verificar(engine) == []
```

- [ ] **Step 2: Run** `uv run pytest tests/gold -v`. Expected: FAIL.
- [ ] **Step 3: Implement** (Claude).
- [ ] **Step 4: Run** `uv run ruff check . && uv run pytest -v`. Expected: PASS, including `-m db` with local compose up.
- [ ] **Step 5: Commit** `feat(gold): build, checagens, carga idempotente e teste de contrato`.

---

### Task 13: Orquestração com Airflow

**Files:**
- Create: `docker-compose.airflow.yml`, `docker/airflow/Dockerfile`, `airflow/dags/{ibge,cnes,sih,siconfi,indices,custos,rotas,gold}_dag.py`, `airflow/dags/_common.py`
- Test: `tests/airflow/test_dag_structure.py`

**Interfaces:**
- Consumes: `pipeline.run(cfg)` de cada domínio; `load_config`.
- Produces:
  - Imagem baseada em `apache/airflow:2.10-python3.12` com o pacote instalado em modo editável (volume `./src`). LocalExecutor. Metadata DB = database `airflow` no mesmo contêiner postgis (criada pelo init script do Airflow compose, não pelo de Task 1).
  - `_common.task_run(dominio: str) -> PythonOperator`: chama `run(load_config(uf=Variable.get("uf", "BA")))`.
  - DAGs com `schedule=None`, `catchup=False`, tag `hospital_siting`. `gold_dag` usa `ExternalTaskSensor` (ou `TriggerDagRunOperator` a partir de um DAG `all`) para esperar os outros 7. `rotas_dag` precisa de acesso ao Docker do host (socket montado) para subir o OSRM.

- [ ] **Step 1: Write the failing test** (Haiku), sem precisar do Airflow instalado. Faz parse estático com `ast`:

```python
def test_every_domain_has_dag():
    names = {p.stem for p in Path("airflow/dags").glob("*_dag.py")}
    assert names == {f"{d}_dag" for d in ["ibge","cnes","sih","siconfi","indices","custos","rotas","gold"]}

def test_dags_call_pipeline_run_only():
    for p in Path("airflow/dags").glob("*_dag.py"):
        src = p.read_text()
        assert "task_run(" in src and "import pandas" not in src  # DAGs finos
```

- [ ] **Step 2: Run** `uv run pytest tests/airflow -v`. Expected: FAIL.
- [ ] **Step 3: Implement.**
- [ ] **Step 4: Verify** `docker compose -f docker-compose.yml -f docker-compose.airflow.yml up -d`, depois `docker compose -f docker-compose.yml -f docker-compose.airflow.yml exec airflow-scheduler airflow dags list-import-errors`. Expected: `No data found`. Os 8 DAGs aparecem em `airflow dags list`.
- [ ] **Step 5: Commit** `feat(airflow): DAGs por domínio e DAG gold`.

---

### Task 14: README e esqueleto da página "como funciona"

**Files:**
- Modify: `README.md`
- Create: `docs/como-funciona/template.html`, `docs/como-funciona/style.css`, `src/hospital_siting/docs_page.py`
- Test: `tests/test_docs_page.py`

**Interfaces:**
- Consumes: tabelas `meta.fontes`, `meta.validacoes` e `meta.execucoes` (ou os jsonl em `data/meta`).
- Produces:
  - `docs_page.render(cfg, out: Path) -> Path`: preenche o template com as contagens de fontes, as datas de referência, as checagens (pass/warn/fail) e a data-base. Gera `docs/como-funciona/index.html` estático, sem JS obrigatório.
  - Seções fixas do template: Problema · Dados (tabela de fontes gerada) · Pipeline (diagrama raw→bronze→silver→gold) · Decisões e porquês · Avaliado e descartado (Spark, Great Expectations, Google Maps) · Limitações (§14 da spec) · Como o resultado é calculado (placeholder da Fase 2).
  - O README traz: como reproduzir (`uv sync`, `docker compose up -d`, `python -m hospital_siting.cli run all`), arquitetura, "avaliado e descartado" e limitações.

- [ ] **Step 1: Write the failing test**

```python
def test_render_includes_sources_and_checks(cfg_fixture, tmp_path):
    html = render(cfg_fixture, tmp_path / "index.html").read_text(encoding="utf-8")
    assert "Avaliado e descartado" in html and "Spark" in html
    assert "municipio" in html and "pass" in html
```

- [ ] **Step 2–4:** como antes.
- [ ] **Step 5: Commit** `docs: README e página como funciona (esqueleto gerado)`.

---

### Task 15: Execução real ponta a ponta (Claude)

- [ ] **Step 1:** `docker compose up -d`, depois `uv run python -m hospital_siting.cli run all --uf BA` (a ordem é: ibge → (cnes, sih, siconfi, indices, custos, rotas) → gold). Expected: termina sem `fail` em `data/meta/validacoes.jsonl`.
- [ ] **Step 2:** `uv run pytest -m online -v`. Expected: PASS.
- [ ] **Step 3:** consultas de sanidade em `psql`. Expected, conforme as faixas indicadas nas Tasks 4 e 9:
  - `select count(*) from gold.dim_municipio` = 417;
  - `select count(*) from gold.matriz_tempo_viagem` = 173889;
  - `select sum(deficit) from gold.deficit_leitos where tipo_leito='uti_adulto'`, com valor plausível e anotado no README.
- [ ] **Step 4:** reexecutar `run all`. Expected: nenhum download novo (manifest inalterado) e contagens da gold idênticas.
- [ ] **Step 5:** `uv run python -c "from hospital_siting.docs_page import render; ..."`, gerando `docs/como-funciona/index.html`. Conferir no navegador.
- [ ] **Step 6:** `pg_dump -n gold -n meta` em `dist/gold_snapshot.sql.gz` (artefato local para a Fase 2; fora do git).
- [ ] **Step 7: Commit** `chore: execução ponta a ponta da base da Bahia` (só docs e README atualizados; dados não são versionados).
