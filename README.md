# hospital-siting

Onde construir hospitais gerais na Bahia, e de que porte, dado um orçamento?

Você escolhe o orçamento (obra + equipamentos + 12 meses de operação) e o otimizador indica municípios e portes (H1 a H4,
de 50 a 400 leitos) que cobrem o maior déficit de leitos SUS. A conta inclui tempo de viagem por estrada e um consórcio
de municípios capaz de pagar a operação. Cada indicação vem com a justificativa: déficit coberto, população atendida,
custos e viabilidade.

O projeto tem duas fases:

- **Fase 1, base de dados:** pipeline reproduzível que coleta, limpa, valida e carrega no PostgreSQL/PostGIS demografia
  e PIB (IBGE), rede hospitalar e leitos (CNES), internações (SIH/SUS), receitas municipais (SICONFI), índices (IPCA,
  INCC), custos de obra, equipamentos e salários, e tempo de viagem entre todos os municípios (OSRM + OpenStreetMap).
- **Fase 2, produto:** modelo de custos por porte, otimizador MILP (PuLP + HiGHS), API FastAPI e interface de mapa.

A página [docs/como-funciona](docs/como-funciona/) resume em menos de 3 minutos os passos, as decisões e os porquês.
Ela é gerada a partir dos metadados do pipeline e da própria gold.

Os defeitos encontrados, com causa, correção e teste de regressão, estão em
[docs/bugs-encontrados.md](docs/bugs-encontrados.md). Lá também estão os achados de modelagem da Fase 2, por exemplo:
com 20% da receita municipal, o consórcio nunca é o gargalo na Bahia.

## Arquitetura

```
fontes ─► data/raw/<fonte>/      originais intocados + manifest (sha256, URL, data de coleta)
        ─► data/bronze/           Parquet, só conversão de formato
        ─► data/silver/           limpo, tipado, validado com Pandera (contratos em src/hospital_siting/schemas)
        ─► PostGIS schema gold    contrato versionado em contracts/ (DDL + teste de contrato)
           PostGIS schema meta    linhagem: fontes, execuções, validações
```

- Cada domínio (`ibge`, `cnes`, `sih`, `siconfi`, `indices`, `custos`, `rotas`) separa I/O (`fetch.py`), transformação
  pura (`transform.py`) e orquestração (`pipeline.py` → `run(cfg)`).
- Airflow e CLI chamam a mesma função `run(cfg)`.
- Coletores idempotentes: reexecutar não baixa nada de novo nem duplica linhas.
- O pipeline é parametrizado por UF em `config/settings.yaml`. A Bahia é o primeiro estado.
- Parâmetros curados à mão ficam em [`seeds/`](seeds/), com fonte citada linha a linha.

## Fase 2: como o resultado é calculado

```
gold (PostGIS) ─► produto/custos.py       custo por porte: obra (SINAPI × fator hospitalar), equipamentos (RENEM),
                                           12 meses de operação (equipe das normas → FTE × salário RAIS × encargos)
               ─► produto/otimizador.py   MILP: max déficit coberto − penalidade de concentração
                                           s.a. orçamento, capacidade por tipo de leito, cobertura gradual por tempo,
                                           viabilidade do consórcio (20% receita + SUS + Estado ≥ custo anual)
               ─► produto/explicacao.py   justificativa por hospital e "por que não" para os candidatos descartados
               ─► api/app.py (FastAPI)  ─► web/ (Leaflet, sem build)
```

| Peça | Escolha |
|---|---|
| Custos | Por arquétipo H1–H4 da gold; premissas frágeis (fator hospitalar 2,5×, equipe fora das normas +100%) são sliders |
| Cobertura | 100% até 30 min, linear até zero em 3 h, pela matriz OSRM |
| Consórcio | Cada município em no máximo um; Estado com 40% (regra das Policlínicas da BA) |
| Solver | HiGHS via PuLP 4, gap de 1%, limite de 10 s; 4–9 s na Bahia (165 candidatos × 4 portes) |
| API | `POST /api/otimizar`, `GET /api/portes`, `GET /api/municipios`, `GET /api/parametros`; cache e pré-cálculo dos orçamentos do slider |

A formulação completa está no topo de [`otimizador.py`](src/hospital_siting/produto/otimizador.py) e no design em
[`docs/superpowers/specs/2026-11-11-fase2-produto-design.md`](docs/superpowers/specs/2026-11-11-fase2-produto-design.md).

## Como reproduzir

```bash
uv sync --all-extras
docker compose up -d
uv run python -m hospital_siting.cli run all --uf BA
```

API e interface contra a gold local (http://localhost:8000):

```bash
uv run uvicorn hospital_siting.api.app:app --port 8000
```

Regerar a página "como funciona" com a seção da Fase 2 calculada da gold:

```bash
uv run python -m hospital_siting.cli docs
```

## Deploy (KVM2 via Dokploy)

O servidor recebe só a gold pronta (snapshot) + API/interface. Airflow e OSRM nunca rodam lá.

```bash
docker exec hs-postgis pg_dump -U postgres -d hospital_siting -n gold -n meta --no-owner | gzip -9 > dist/gold_snapshot_fase2.sql.gz
```

Publique o dump como asset de uma release do GitHub (a `v0.2.0` traz o atual). O compose de deploy baixa o asset no
primeiro boot, confere o sha256 e só então o PostGIS o restaura; o servidor não precisa de SSH nem de cópia manual.

No Dokploy: aplicação do tipo Compose apontando para este repositório e `docker-compose.deploy.yml`. Variável
obrigatória: `POSTGRES_PASSWORD`. Em Domains, gere o domínio gratuito do Dokploy para o serviço `api`, porta 8000. Para
trocar a gold, publique uma release nova, defina `HS_SNAPSHOT_URL` e `HS_SNAPSHOT_SHA256`, apague o volume `gold` e
reimplante.

Teste local do mesmo compose (http://localhost:8080):

```bash
POSTGRES_PASSWORD=troque docker compose -f docker-compose.deploy.yml -f docker-compose.local.yml up -d --build
```

Orquestração com Airflow:

```bash
docker compose -f docker-compose.yml -f docker-compose.airflow.yml up -d
```

Testes (o CI roda lint primeiro, depois os testes sem rede):

```bash
uv run ruff check . && uv run pytest -m "not online"   # inclui casos pequenos do otimizador com solução conhecida
```

## Avaliado e descartado

| Opção | Por que não |
|---|---|
| Apache Spark / PySpark | O volume (CNES e 36 meses de SIH da Bahia) cabe em memória. DuckDB entrega SQL colunar local, sem o custo operacional de um cluster. |
| Great Expectations | Configuração pesada (contextos, stores, data docs) para o tamanho do projeto. Pandera valida no próprio código, junto das transformações. |
| Google Maps Distance Matrix | Cerca de 174 mil pares de municípios custariam centenas de dólares, e os termos proíbem armazenar os resultados. OSRM é gratuito, local e reproduzível. |
| SomaSUS (raspagem) | A API exige login gov.br. Usamos a lista pública RENEM (FNS) como referência de preços de equipamentos. |
| Solver comercial (Gurobi, CPLEX) | Licença incompatível com um projeto aberto e com o deploy num servidor pequeno. O HiGHS resolve a Bahia com gap de 1% em segundos. |
| Framework de front-end (React, Vue) | Uma página com mapa e sliders não justifica build. Leaflet + JS puro é servido pela própria API. |
| Mapa de fundo (tiles) | A malha do IBGE já desenha o estado, e tiles de terceiros exigem chave ou têm limites de uso. |

## Limitações conhecidas

- População tratada como concentrada na sede municipal.
- Tempo de viagem supõe estrada livre. O fator de correção é aplicado na Fase 2.
- Fluxo de pacientes entre estados é ignorado.
- Parâmetros financeiros (participação municipal, aporte estadual, ocupação, encargos de 70%) são hipóteses.
- Custeio não pessoal (0,25 × pessoal) e área por leito (80 m²) têm fontes frágeis. Ver [`seeds/README.md`](seeds/README.md).
- Necessidade de leitos: Cenário 2 é o ponto médio entre os cenários P25 e P75 da Portaria 1.631/2015, configurável.
- O módulo IBGE contém um shim de compatibilidade entre geobr 0.2 e DuckDB 2 (`ibge/fetch.py`).
- Fase 2: com 20% da receita municipal o consórcio nunca limita a escolha na Bahia; o objetivo conta todo leito igual e
  por isso favorece hospitais pequenos; o tempo de solução (4–9 s) está acima do ~1 s pretendido (mitigado com cache).
- As fontes têm anos de referência diferentes. Todos ficam registrados em `meta.fontes`, e os valores monetários são
  corrigidos para uma data-base única.
