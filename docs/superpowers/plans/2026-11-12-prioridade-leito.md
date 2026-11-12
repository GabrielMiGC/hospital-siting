# Prioridade por tipo de leito: plano de implementação

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** o objetivo do otimizador passa a ponderar o déficit atendido por tipo de leito, com os pesos ajustáveis na API e na interface. O padrão é neutro (todos 1).

**Architecture:** um dict `pesos_leito` em `Parametros` multiplica o termo de cobertura do objetivo. As restrições não mudam. A API expõe seis campos planos `peso_<tipo>`. A interface ganha seis sliders. As justificativas e a página explicam a ponderação.

**Tech Stack:** Python 3.12, PuLP + HiGHS, FastAPI/pydantic, JS puro + Leaflet, pytest.

**Spec:** `docs/superpowers/specs/2026-11-12-prioridade-leito-design.md`

## Global Constraints

- O padrão é `1.0` para os 6 tipos de `TIPOS_LEITO`. Com o padrão, o resultado tem que ser idêntico ao atual.
- Pesos ≥ 0. A API aceita a faixa 0–10, e o slider vai de 0 a 5 com passo 0,5.
- Relatórios (`deficit_coberto`, `deficit_por_tipo`, KPIs) continuam em leitos reais.
- Textos em português. `uv run pytest -m "not online"` verde. `uv run ruff check` e `ruff format --check` limpos.
- Tempo de solução na gold real ≤ 10 s com os pesos padrão.

## Review Focus

- Peso 0 em um tipo: o tipo não pesa no objetivo, mas o modelo não pode quebrar. O hospital ainda pode aparecer por outros tipos (teste em Task 1).
- Chave de tipo inexistente ou peso negativo: `ValueError` em `Parametros` e 422 na API (testes nas Tasks 1 e 3).
- Pesos neutros passados explicitamente, iguais ao padrão, dão o mesmo resultado e o mesmo texto (Task 2).
- "Restaurar padrões" na interface volta todos os pesos a 1 (os pesos entram em `CAMPOS`, Task 4).
- Cache da API: pesos diferentes geram chaves diferentes. A chave é `model_dump_json`, então isso já vale com campos planos (teste na Task 3).

---

### Task 1: pesos em `Parametros` e no objetivo

**Files:** Modify `src/hospital_siting/produto/otimizador.py`. Test: `tests/produto/test_otimizador.py`

**Interfaces:**
- Produces: `Parametros.pesos_leito: dict[str, float]` (padrão: todos 1.0); `peso_tipo(p: Parametros, tipo: str) -> float`; `pesos_neutros(p: Parametros) -> bool`; `HospitalIndicado.deficit_ponderado: float`; `Resultado.deficit_ponderado: float`.

- [ ] Testes:
  - `test_peso_de_uti_troca_h1_espalhados_por_h2`: A (clínico 10 + UTI adulto 10), D e E (clínico 10 cada), a 400 min uns dos outros, `orcamento=7e6`, portes H1 e H2. Com o padrão, o resultado é `[(A,H1),(D,H1),(E,H1)]`. Com `pesos_leito={"uti_adulto": 3}`, é `[(A,H2)]`, com `deficit_ponderado == approx(40)` e `deficit_coberto == approx(20)`.
  - `test_pesos_invalidos_sao_rejeitados`: `Parametros(orcamento=1e6, pesos_leito={"xyz": 1})` e `{"clinico": -1}` levantam `ValueError`.
  - `test_peso_zero_nao_quebra`: o caso de UTI com `pesos_leito={"uti_adulto": 0}` resolve e devolve 3×H1.
- [ ] Rodar os testes: FAIL.
- [ ] Implementar: validação em `__post_init__`, completando as chaves ausentes com 1. Objetivo `Σ π_t·w·u`. `deficit_ponderado` preenchido em `montar_hospitais` e somado em `otimizar`.
- [ ] Rodar `tests/produto`: PASS. Os testes antigos continuam passando sem mudança. Commit `feat(otimizador): prioridade por tipo de leito no objetivo`.

### Task 2: justificativas e descartes

**Files:** Modify `src/hospital_siting/produto/explicacao.py`. Test: `tests/produto/test_otimizador.py`

- [ ] Testes:
  - `test_justificativa_cita_prioridade_so_quando_ha`: no caso de UTI com peso 3, `"prioridade" in justificativa` e `"3×" in justificativa`, e `"ponderad" in res.mensagem`. Com o padrão, `"prioridade" not in` em nenhum dos dois.
  - Com `pesos_leito` explícito todo 1, a justificativa é igual à do padrão.
- [ ] Implementar: `_justificativa` acrescenta "com a prioridade escolhida (UTI adulto 3×), vale N leitos ponderados" quando `not pesos_neutros(p)`. `mensagem_geral` acrescenta "(N leitos ponderados pela prioridade escolhida)". Em `descartes`, `pot` vira o potencial ponderado (Σ π_t·min(L, demanda)), e `deficit_potencial` continua em leitos reais.
- [ ] Testes PASS. Commit `feat(explicacao): justificativas citam a prioridade por tipo de leito`.

### Task 3: API

**Files:** Modify `src/hospital_siting/api/esquemas.py`. Test: `tests/api/test_api.py`

- [ ] Testes:
  - `test_parametros_expoe_pesos_por_tipo`: `padroes["peso_uti_adulto"] == 1` e `limites["peso_uti_adulto"] == {"min": 0, "max": 10}` para os 6 tipos.
  - `test_otimizar_rejeita_entrada_invalida_com_422` ganha o caso `{"orcamento": 1e8, "peso_uti_adulto": -1}`.
  - `test_pesos_viram_dict_em_parametros`: `OtimizarEntrada(orcamento=1e8, peso_uti_adulto=3).parametros().pesos_leito["uti_adulto"] == 3`.
- [ ] Implementar seis campos `peso_<tipo>: float = Field(1.0, ge=0, le=10)` e montar o dict em `parametros()`.
- [ ] Testes PASS. Commit `feat(api): pesos por tipo de leito na entrada do otimizador`.

### Task 4: interface

**Files:** Modify `src/hospital_siting/web/index.html`, `src/hospital_siting/web/app.js`

- [ ] Em `index.html`: novo `<details class="premissas">` "Prioridade por tipo de leito" com a nota "Todos em 1× = todo leito de déficit vale igual. Mais peso é uma escolha de política, não um dado." e seis sliders (`id=peso_<tipo>`, min 0, max 5, step 0.5, value 1).
- [ ] Em `app.js`: `FORMATO["peso_<tipo>"] = (v) => \`${(+v).toFixed(1).replace(".", ",").replace(",0", "")}×\`` para os seis. Os sliders já entram em `CAMPOS` e em "Restaurar padrões".
- [ ] Verificar no navegador: a API local com a gold e o slider UTI adulto em 3× mudam as indicações, e "Restaurar padrões" volta tudo a 1×. Commit `feat(web): sliders de prioridade por tipo de leito`.

### Task 5: página como-funciona, achados e gold real

**Files:** Modify `src/hospital_siting/produto/pagina.py`, `docs/bugs-encontrados.md`, `tests/produto/test_pagina.py`, `tests/produto/test_gold_real.py`

- [ ] Teste `test_secao_fase2_explica_prioridade`: a seção contém "prioridade por tipo de leito" e "todos 1".
- [ ] Seção 4 da página: fórmula com π_t, padrão neutro, efeito em λ (unidade ponderada) e a nota de política pública. Ajustar o achado "favorece pequenos". Regenerar `docs/como-funciona` com `cli docs`.
- [ ] Teste db `test_prioridade_uti_na_bahia`: em R$ 1 bi com UTI adulto e neo/ped em 3×, o status tem solução e `tempo_s <= 12`. Registrar os portes antes/depois em `docs/bugs-encontrados.md`.
- [ ] `uv run pytest -m "not online"`, ruff. Commit `docs: prioridade por tipo de leito na página e nos achados`.
