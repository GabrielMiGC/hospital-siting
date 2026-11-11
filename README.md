# hospital-siting

Onde construir hospitais gerais na Bahia, e de que porte, dado um orçamento?

Este repositório contém a **Fase 1: a base de dados**. É um pipeline reproduzível que coleta, limpa, valida e carrega
no PostgreSQL/PostGIS tudo o que o otimizador da Fase 2 consome:

- demografia e PIB (IBGE);
- rede hospitalar e leitos (CNES/DATASUS);
- internações (SIH/SUS);
- receitas municipais (SICONFI);
- índices de correção (IPCA, INCC);
- custos de obra, equipamentos e salários;
- tempo de viagem por estrada entre todos os municípios (OSRM + OpenStreetMap).

A página [docs/como-funciona](docs/como-funciona/) resume em menos de 3 minutos os passos seguidos, as decisões
tomadas e os porquês. Ela é gerada a partir dos metadados do próprio pipeline.

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

## Como reproduzir

```bash
uv sync
docker compose up -d
uv run python -m hospital_siting.cli run all --uf BA
```

Orquestração com Airflow:

```bash
docker compose -f docker-compose.yml -f docker-compose.airflow.yml up -d
```

Testes (o CI roda lint primeiro, depois os testes sem rede):

```bash
uv run ruff check . && uv run pytest -m "not online"
```

## Avaliado e descartado

| Opção | Por que não |
|---|---|
| Apache Spark / PySpark | O volume (CNES e 36 meses de SIH da Bahia) cabe em memória. DuckDB entrega SQL colunar local, sem o custo operacional de um cluster. |
| Great Expectations | Configuração pesada (contextos, stores, data docs) para o tamanho do projeto. Pandera valida no próprio código, junto das transformações. |
| Google Maps Distance Matrix | Cerca de 174 mil pares de municípios custariam centenas de dólares, e os termos proíbem armazenar os resultados. OSRM é gratuito, local e reproduzível. |
| SomaSUS (raspagem) | A API exige login gov.br. Usamos a lista pública RENEM (FNS) como referência de preços de equipamentos. |

## Limitações conhecidas

- População tratada como concentrada na sede municipal.
- Tempo de viagem supõe estrada livre. O fator de correção é aplicado na Fase 2.
- Fluxo de pacientes entre estados é ignorado.
- Parâmetros financeiros (participação municipal, aporte estadual, ocupação, encargos de 70%) são hipóteses.
- Custeio não pessoal (0,25 × pessoal) e área por leito (80 m²) têm fontes frágeis. Ver [`seeds/README.md`](seeds/README.md).
- Necessidade de leitos: Cenário 2 é o ponto médio entre os cenários P25 e P75 da Portaria 1.631/2015, configurável.
- O módulo IBGE contém um shim de compatibilidade entre geobr 0.2 e DuckDB 2 (`ibge/fetch.py`).
- As fontes têm anos de referência diferentes. Todos ficam registrados em `meta.fontes`, e os valores monetários são
  corrigidos para uma data-base única.
