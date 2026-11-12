# Fase 2 — Produto: plano de implementação

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** custos por porte, otimizador MILP, API FastAPI, interface de mapa e deploy, consumindo a gold da Fase 1.

**Architecture:** novo pacote `hospital_siting.produto` com funções puras sobre um dataclass `Gold` (carregado do
PostGIS ou montado em memória nos testes); `hospital_siting.api` expõe FastAPI e serve `hospital_siting/web/`
estático. Nenhuma escrita na gold.

**Tech Stack:** Python 3.12, uv, pandas/numpy, PuLP + highspy (HiGHS), FastAPI + uvicorn, Pydantic 2, SQLAlchemy,
Leaflet 1.9.4 (CDN), Docker Compose.

**Spec:** `docs/superpowers/specs/2026-11-11-fase2-produto-design.md` (e §9/§12 de `2026-11-11-hospital-siting-design.md`)

## Global Constraints

- Tudo em português (código de domínio, mensagens, docs). Conventional commits na branch `feat/fase2`; sem push/merge.
- Valores monetários na data-base da gold (`meta.execucoes.extra.data_base`, hoje 2026-09).
- CI sem rede: testes usam `Gold` em memória; teste contra o banco real com marcador `db`.
- Cobertura: 100% até `t_full`=30 min, linear até 0 em `t_max`=180 min; X=20%; ocupação 80%.
- Lint `ruff check .` limpo (linha 120).

## Review Focus

1. Orçamento menor que o hospital mais barato → resposta válida com zero hospitais e mensagem clara (teste em Task 3 e Task 4).
2. Município sem receita (`receita_disponivel=false`) → contribui 0 ao consórcio, continua demanda (Task 3).
3. Pares sem rota (`minutos_osrm` NULL) → fora de alcance, nunca peso 1 (Task 2).
4. Nenhum porte permitido / parâmetros fora do limite → 422 da API, não 500 (Task 4).
5. Solver no limite de tempo → resposta traz status e gap, não exceção (Task 3).

---

### Task 1: Modelo de custos por porte

**Files:** Create `src/hospital_siting/produto/{__init__,dados,custos}.py`; Modify `seeds/equipamentos_ambiente.csv`
(+ Ortopedia 253, Hemodinâmica 282 e 10543, Neurocirurgia 1543 e 390, todas `por_hospital`=1); Test `tests/produto/test_custos.py`, `tests/produto/conftest.py`.

**Interfaces — Produces:**
- `Gold` dataclass (`dados.py`): `municipios: DataFrame[cod_ibge,nome,populacao,receita_corrente,receita_disponivel,lat,lon]`,
  `deficit: DataFrame[cod_ibge,tipo_leito,deficit]`, `tempos: DataFrame[origem,destino,minutos]`,
  `estabelecimentos: DataFrame[cnes,cod_ibge,leitos_sus]`, `arquetipos`, `custo_obra_m2: float`, `equipamentos`,
  `equipe`, `salarios`, `custeio: dict[str,float]`, `valor_internacao`, `consorcio: dict[str,float]`, `data_base: str`.
- `Premissas` dataclass (`custos.py`) com `fator_hospitalar=2.5`, `fator_pessoal_nao_normatizado=1.0`, `ist=0.15`,
  `horas_turno=8`, `leitos_cirurgicos_por_sala=15`, `pct_obs_ps=0.10`, `leitos_reanimacao=2`, `ocupacao=0.8`.
- `AMBIENTES_POR_PORTE: dict[str, set[str]]`, `ESPECIALIDADES: dict[str, list[str]]`.
- `custo_porte(gold, porte, premissas) -> CustoPorte` (`leitos`, `leitos_por_tipo`, `area_m2`, `obra`, `equipamentos`,
  `pessoal_anual`, `custeio_anual`, `operacao_anual`, `total` = obra+equip+operacao_anual, `fte`, `salas_cirurgicas`,
  `itens_sem_preco`, `receita_sus_anual`).
- `receita_sus_anual(gold, leitos_por_tipo, ocupacao) -> float`.

- [ ] Fixture `gold_mini()` em `tests/produto/conftest.py`: 1 porte "H1" (clinico 10, area 800), "H2" (+ uti_adulto 10, area +800), SINAPI 1000, equipamentos simples, salário 1000, encargos 0.7, custeio 0.25.
- [ ] Testes: `test_obra_usa_fator_hospitalar` (800 m² × 1000 × 2,5 = 2.000.000); `test_equipamento_por_leito_so_no_ambiente_do_porte` (UTI só em H2); `test_fte_uti_aplica_minimo_por_turno` (razão 0,1 × 5 leitos → 1 posto); `test_operacao_anual_inclui_encargos_custeio_e_nao_normatizado`; `test_receita_sus_aih_e_diaria` (10 leitos clínicos, 0,8, perm 5, valor 100 → 58.400; UTI 10 leitos × 0,8 × 365 × 500 = 1.460.000); `test_custo_portes_reais_crescem` (seeds reais via fixture db opcional: H1<H2<H3<H4).
- [ ] Rodar → FAIL; implementar; rodar → PASS. Rodar `cli run custos` e `cli run gold` para levar os itens novos à gold.
- [ ] Commit `feat(produto): modelo de custos por porte`.

### Task 2: Cobertura gradual e carga da gold

**Files:** Modify `produto/dados.py` (`carregar_gold(dsn) -> Gold`, `geojson_municipios(dsn, tolerancia=0.01) -> dict`); Create `produto/cobertura.py`; Test `tests/produto/test_cobertura.py`, `tests/produto/test_dados_db.py` (marcador `db`).

**Produces:** `peso_cobertura(minutos: ndarray, t_full, t_max, fator_osrm=1.0) -> ndarray` (NaN → 0); `hospitais_no_raio(gold, t_min) -> Series[cod_ibge→n]`.

- [ ] Testes: `test_peso_100_ate_t_full`, `test_peso_linear` (105 min → 0,5 com 30/180), `test_peso_zero_apos_t_max_e_nan`, `test_fator_osrm_alonga_tempo`, `test_hospitais_no_raio_conta_o_proprio`; db: `test_carregar_gold_real` (417 municípios, data_base "2026-09").
- [ ] FAIL → implementar → PASS → commit `feat(produto): cobertura gradual e leitura da gold`.

### Task 3: Otimizador + explicação

**Files:** Create `produto/otimizador.py`, `produto/explicacao.py`; Modify `pyproject.toml` (pulp, highspy); Test `tests/produto/test_otimizador.py`.

**Produces:** `Parametros` dataclass (orcamento, portes, pct_receita=0.20, t_full=30, t_max=180, fator_osrm=1.0, ocupacao=0.8, peso_concentracao=1.0, t_conc=60, aporte_por_leito=0.0, pop_min_candidato=20000, premissas: Premissas, time_limit=20, gap=0.005); `otimizar(gold, params) -> Resultado` (`hospitais: list[HospitalIndicado]`, `descartados: list[Descarte]`, `deficit_coberto`, `custo_total`, `status`, `gap`, `tempo_s`, `mensagem`). Formulação exata da spec §5.

- [ ] Gold de teste em linha (A–B–C–D, tempos 0/20/60/200 min) com casos: `test_um_hospital_vai_para_o_centro`; `test_consorcio_inviavel_descarta` (receitas zero → nenhum hospital, descarte com motivo "consórcio"); `test_concentracao_muda_escolha` (empate quebrado por H_j); `test_orcamento_para_dois_consorcios_disjuntos`; `test_porte_sem_uti_nao_cobre_uti`; `test_orcamento_insuficiente_zero_hospitais`; `test_municipio_sem_receita_contribui_zero`; `test_status_e_gap_presentes`.
- [ ] FAIL → implementar → PASS; medir tempo com a gold real (meta: < 5 s) → commit `feat(produto): otimizador MILP com consórcio e penalidade`.

### Task 4: API FastAPI

**Files:** Create `src/hospital_siting/api/{__init__,app,esquemas}.py`; Test `tests/api/test_api.py`.

**Produces:** `criar_app(gold: Gold | None = None, geojson: dict | None = None) -> FastAPI`; rotas da spec §6; `OtimizarEntrada` (orcamento 1e6–5e10, portes ⊂ {H1..H4} não vazio, limites dos sliders).

- [ ] Testes com `TestClient` e `gold_mini`: saúde, portes, parâmetros, otimizar 200 com hospitais, 422 para portes vazio e orçamento negativo, `/` serve HTML.
- [ ] FAIL → implementar → PASS → commit `feat(api): rotas de otimização`.

### Task 5: Interface

**Files:** Create `src/hospital_siting/web/{index.html,app.js,style.css}`.
- [ ] Mapa Leaflet, barra lateral (parâmetros + filtros), caixa de explicação, cartões por hospital; verificar no navegador contra a gold real (`uvicorn hospital_siting.api.app:app`).
- [ ] Commit `feat(web): interface de mapa`.

### Task 6: Docs, deploy, CI

**Files:** Modify `docs_page.py` (`render(cfg, out, fase2_html=None)`), `cli.py` (comando `docs`), `README.md`, `docs/bugs-encontrados.md`, `.github/workflows/ci.yml` se preciso; Create `Dockerfile`, `docker-compose.deploy.yml`, `.dockerignore`.
- [ ] Teste `test_render_preenche_fase2`; FAIL → PASS.
- [ ] Build da imagem e `docker compose -f docker-compose.deploy.yml up` local; checar `/api/saude`.
- [ ] Commits `docs: ...`, `build: ...`.
