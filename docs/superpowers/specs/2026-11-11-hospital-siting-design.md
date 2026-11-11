# Hospital Siting — Documento de Design

> Data: 2026-11-11 · Status: rascunho para aprovação
> Nome de trabalho do repositório: `hospital-siting` (pode ser renomeado).

## 1. Intenção e porquê

Sistema de apoio à decisão que, a partir de um **orçamento total**, indica **onde construir um ou mais hospitais gerais** num estado brasileiro (começando pela **Bahia**, 417 municípios) e **de que porte**. O orçamento cobre construção, equipamentos e **12 meses de operação com equipe completa**.

O projeto existe como **peça de portfólio para vagas de Engenharia de Dados** (pleno, ou júnior com potencial claro de promoção) em empresas médias e grandes.

**Momento de sucesso:** o avaliador abre a interface, mexe no mapa e nos sliders de orçamento, vê o resultado aparecer, lê uma explicação curta de *por que* aquele resultado é o melhor e conclui: *"que projeto incrível"* e *"esse candidato identifica problemas e encontra sozinho formas de resolvê-los"*.

Consequência de design: o **pipeline de dados é a estrela técnica**, e o otimizador e o mapa são a vitrine. Decisões, descartes e limitações precisam estar **visíveis**, e não escondidos.

## 2. Fases e divisão de trabalho

| Fase | O que entrega | Quem constrói |
|---|---|---|
| **Fase 1 — Base de dados** (este documento detalha) | Pipeline reproduzível que coleta, limpa, valida e carrega no Postgres/PostGIS todos os dados que o modelo precisa, mais a página "como funciona" (esqueleto) e o README | Claude (orquestrando agentes: ver §13) |
| **Fase 2 — Produto** | Modelo de custos por porte, otimizador, API, interface, deploy | Fable 5.2, a partir desta spec + base local pronta |

Este documento define a Fase 1 por completo e o **contrato** que a Fase 2 consome (as tabelas finais da §8 e o modelo da §9). A §9 está aqui para que a base suporte o modelo; a implementação dele é da Fase 2.

## 3. Objetivos, não-objetivos, anti-objetivos

**Objetivos**
- Base local completa e validada, reconstruível do zero com um comando.
- Pipeline parametrizado por UF desde o início (Bahia é só o primeiro valor).
- Linhagem: todo número final rastreável até a fonte, a data de coleta e a regra de limpeza aplicada.
- Contrato de dados estável para a Fase 2.

**Não-objetivos (agora)**
- Hospitais especializados (maternidade, oncologia, trauma isolado).
- Outros estados além da Bahia (o código suporta, mas não coletamos).
- Fluxo de pacientes entre estados (efeito de fronteira com PE, MG etc.).
- População intramunicipal (grade estatística, setores censitários).
- Atualização agendada/contínua: a base é um snapshot reproduzível.

**Anti-objetivos (falharia mesmo funcionando)**
- Ferramenta escolhida para o currículo e não para o problema.
- Resultado "caixa-preta" sem explicação.
- Passos manuais não documentados. Dados curados à mão são permitidos **só** como arquivos seed versionados, com fonte citada linha a linha.
- Apresentar o resultado como recomendação oficial de política pública: é apoio à decisão.
- Modelo que sempre escolhe as cidades mais ricas ou já bem servidas.

## 4. Stack (decidida)

| Área | Escolha |
|---|---|
| Extração via API | Python (requests/httpx; `sidrapy` ou chamadas diretas à API SIDRA) |
| Arquivos DATASUS | Python com `datasus-dbc` (`.dbc` → `.dbf`) |
| Raspagem | Python (SomaSUS) |
| Armazenamento bruto | `data/raw/` (originais intocados) → `data/bronze/` (Parquet, só convertido) |
| Transformação | **DuckDB** |
| Qualidade de dados | **Pandera** |
| Banco final | **PostgreSQL + PostGIS** (contêiner com volume próprio) |
| Orquestração | **Apache Airflow** local em contêiner (DAGs) |
| Geoprocessamento | `geobr`, GeoPandas/Shapely, PostGIS |
| Tempo de viagem | **OSRM** local em contêiner, recorte Nordeste do OpenStreetMap (Geofabrik) |
| Otimização (Fase 2) | PuLP + solver HiGHS |
| API (Fase 2) | FastAPI |
| Interface (Fase 2) | Livre para o Fable (ver §12) |
| Ambiente | Docker Compose |
| Versionamento | GitHub |
| CI | GitHub Actions enxuto: **lint primeiro**, depois testes |
| Hospedagem (Fase 2) | Servidor KVM2 via Dokploy (Miranda Labs), link pela landing page no GitHub Pages ou endereço direto gerado pelo Dokploy (sem domínio próprio) |

**Avaliado e descartado (vai para o README com o porquê):**
- **Apache Spark / PySpark:** o volume é pequeno (CNES-BA alguns MB/mês; 3 anos de SIH-BA ≈ poucos milhões de linhas), cabe em memória. Spark traria custo operacional sem ganho. DuckDB resolve com SQL colunar local e escala até dezenas de GB num único nó.
- **Great Expectations:** configuração pesada (contextos, stores, data docs) para o tamanho do projeto. Pandera expressa as validações no próprio código Python, junto das transformações.
- **Google Maps Distance Matrix:** ~174 mil pares de municípios custariam centenas de dólares, e os termos de uso proíbem armazenar os resultados. OSRM é gratuito, local e reproduzível.

## 5. Arquitetura de dados

```
fontes ──► data/raw/<fonte>/<ano-ou-competência>/   (arquivo original, imutável, + manifest com hash)
             │
             ▼
           data/bronze/<fonte>/*.parquet            (conversão de formato, sem regra de negócio)
             │  DuckDB + validação Pandera
             ▼
           data/silver/*.parquet                    (limpo, tipado, chaves padronizadas: cod_ibge 7 dígitos)
             │  DuckDB + validação Pandera
             ▼
           PostgreSQL/PostGIS, schema `gold`        (tabelas do contrato §8)
           PostgreSQL, schema `meta`                (linhagem, execuções, resultados de validação)
```

- `data/` fica **fora do git** (`.gitignore`). Os seeds curados à mão ficam em `seeds/` **dentro** do git.
- Toda configuração em `config/` (YAML): UF alvo, anos de referência, data-base monetária, parâmetros padrão.
- Chave universal de município: **código IBGE de 7 dígitos**. O DATASUS usa 6 dígitos (sem o verificador), então a conversão é uma regra explícita, testada.
- Valores monetários na camada gold estão todos na **mesma data-base** (configurável; padrão = mês mais recente do SINAPI coletado). Correção de obra pelo INCC e do resto pelo IPCA. As séries de índice também são coletadas.
- Cada execução registra em `meta.execucoes` e cada arquivo coletado em `meta.fontes` (URL, data de coleta, ano/competência de referência, hash, nº de linhas).

## 6. Fontes de dados

| # | Dado | Fonte | Acesso | Recorte |
|---|---|---|---|---|
| F1 | População municipal | IBGE: Censo 2022 + estimativa anual mais recente | API SIDRA | UF |
| F2 | PIB municipal | IBGE: PIB dos Municípios (ano mais recente publicado) | API SIDRA | UF |
| F3 | Malhas municipais e sedes | IBGE via `geobr` | pacote | UF |
| F4 | Regiões e macrorregiões de saúde | `geobr` (regiões de saúde) e/ou SESAB (PDR) | pacote / download | UF |
| F5 | Estabelecimentos, leitos por tipo, equipamentos, profissionais | **CNES** (DATASUS FTP: arquivos ST, LT, EQ, PF) | `.dbc` | UF, competência mais recente |
| F6 | Internações por município de residência e de ocorrência, valores pagos | **SIH/SUS** (arquivos RD) | `.dbc` | UF, últimos 3 anos completos |
| F7 | Receita municipal | **SICONFI** (Tesouro Nacional), DCA/FINBRA | API | UF, último exercício fechado |
| F8 | Necessidade de leitos por tipo | **Portaria GM/MS 1.631/2015** | seed curado à mão | nacional |
| F9 | Custo de obra por m² | **SINAPI** (Caixa) e **CUB-BA** (Sinduscon-BA) | planilhas | UF |
| F10 | Equipamentos por ambiente e preços de referência | **SomaSUS** (raspagem) + RENEM/SIGEM, Banco de Preços em Saúde quando necessário | raspagem / download | nacional |
| F11 | Dimensionamento de equipe | RDC ANVISA 7/2010, Resolução COFEN 543/2017 e normas correlatas | seed curado à mão | nacional |
| F12 | Salários por ocupação | RAIS (por CBO, UF) + piso da enfermagem (Lei 14.434/2022) | microdados / Base dos Dados | UF |
| F13 | Valores da tabela SUS | **SIGTAP** | download | nacional |
| F14 | Índices de correção | INCC (FGV) e IPCA (IBGE/SIDRA) | API / download | nacional |
| F15 | Malha viária | OpenStreetMap, recorte Nordeste (Geofabrik) | download `.osm.pbf` | região |
| F16 | Regras do consórcio de Policlínicas da Bahia (proporção estado × municípios) | SESAB / legislação estadual | seed curado à mão | UF |

Regras de coleta:
- **Raspagem educada:** respeitar `robots.txt` e os termos do site, user-agent genérico identificando o projeto (sem dados pessoais), limite de taxa, cache em `raw/` para nunca baixar duas vezes.
- Cada coletor é **idempotente**: se o arquivo com o mesmo hash já existe em `raw/`, pula.
- Seeds manuais (`seeds/*.csv`) têm sempre as colunas `fonte`, `documento`, `pagina_ou_artigo` e `observacao`.

## 7. Matriz de tempo de viagem

- OSRM com perfil `car` sobre um recorte **BA + buffer de 50 km** extraído do arquivo Nordeste do OSM com `osmium` (as estradas fora da BA servem só para roteamento).
- Origem/destino = **sede municipal** de cada município da UF (ponto do IBGE).
- Saída: `gold.matriz_tempo_viagem` (origem, destino, minutos_osrm, km) para todos os pares ordenados.
- O OSRM supõe estrada livre. O **fator de correção** (padrão 1,0, configurável) é aplicado na Fase 2, não na base, para manter o dado bruto intacto.
- Pares sem rota (ilhas sem balsa no OSM etc.) ficam registrados e listados num relatório de validação, sem serem descartados em silêncio.
- O OSRM roda **só localmente**, e o servidor recebe apenas a matriz.

## 8. Contrato da camada gold (o que a Fase 2 consome)

Esquema `gold` no PostGIS. Nomes e colunas mínimas; o builder pode acrescentar colunas.

| Tabela | Grão | Conteúdo mínimo |
|---|---|---|
| `dim_municipio` | município | cod_ibge, nome, uf, populacao, ano_populacao, pib, pib_per_capita, ano_pib, receita_corrente, exercicio_receita, cod_regiao_saude, cod_macrorregiao, geom_sede (POINT), geom_limite (MULTIPOLYGON) |
| `leitos_existentes` | município × tipo de leito | cod_ibge, tipo_leito, qtd_total, qtd_sus, competencia_cnes |
| `estabelecimentos_hospitalares` | estabelecimento | cnes, cod_ibge, tipo, natureza (pública/privada/filantrópica), leitos_total, geom (se houver) |
| `necessidade_leitos_param` | tipo de leito | tipo_leito, leitos_por_mil_hab, fonte |
| `deficit_leitos` | município × tipo de leito | cod_ibge, tipo_leito, necessidade, existente_sus, deficit (pode ser negativo = superávit) |
| `fluxo_internacoes` | residência × ocorrência × ano | cod_ibge_residencia, cod_ibge_ocorrencia, ano, internacoes, valor_total |
| `valor_medio_internacao` | tipo de leito (ou especialidade) | tipo_leito, valor_medio_aih, permanencia_media_dias, fonte_periodo |
| `matriz_tempo_viagem` | par origem × destino | origem, destino, minutos_osrm, km |
| `custo_obra_m2` | referência | fonte (SINAPI/CUB), padrao, valor_m2, data_base |
| `equipamento_ambiente` | ambiente × equipamento | ambiente, equipamento, quantidade_ref, preco_ref, fonte, data_base |
| `dimensionamento_equipe_param` | regra | setor, categoria (CBO), regra (ex.: profissionais por leito/turno), fonte |
| `salario_ocupacao` | CBO × UF | cbo, descricao, salario_medio, encargos_pct, ano |
| `indice_correcao` | índice × mês | indice, mes, valor |
| `consorcio_param` | regra | parametro, valor, fonte |
| `custeio_param` | porte | porte, custeio_nao_pessoal_pct_pessoal, fonte |

Esquema `meta`: `fontes`, `execucoes`, `validacoes` (resultado de cada checagem Pandera, para a página "como funciona" mostrar).

**Tipos de leito** padronizados (alinhados à Portaria 1.631 e aos códigos CNES): clínico, cirúrgico, obstétrico, pediátrico, UTI adulto, UTI neonatal/pediátrica. O mapeamento de códigos CNES → tipo padronizado é um seed versionado.

### 8.1 Regras de cálculo e convenções do contrato

**Déficit de leitos (acessibilidade, método 2SFCA).** A necessidade é calculada **por município**: população × leitos_por_mil / 1000, por tipo. A oferta existente **não** é só a do próprio município. Os leitos SUS de cada estabelecimento são distribuídos entre os municípios a até **T_oferta minutos** (padrão 120, configurável), proporcionalmente à população, pelo método *two-step floating catchment area* (2SFCA), padrão em estudos de acesso a saúde. Assim, um município sem hospital mas vizinho de um bom hospital não aparece com déficit inflado. `deficit_leitos` traz: necessidade, existente_local_sus, oferta_acessivel_sus e deficit (= necessidade − oferta_acessivel; negativo = superávit). O déficit é calculado na Fase 1 com o T_oferta padrão, e a função 2SFCA fica no pacote para a Fase 2 poder recalcular com outro T.

**Mapeamento CNES → tipo de leito.** Seed `seeds/mapa_leitos_cnes.csv` com uma linha por código CNES. Leitos complementares de UTI (todos os níveis) vão para UTI adulto ou neonatal/pediátrica. Leitos fora dos 6 tipos (psiquiátricos, crônicos, reabilitação, hospital-dia etc.) recebem tipo `fora_do_escopo`: ficam em `leitos_existentes`, mas não entram no déficit. Isso é documentado como limitação.

**SIH (`fluxo_internacoes` e `valor_medio_internacao`).**
- `fluxo_internacoes` é **agregado enxuto**, sem entrar no objetivo do modelo. Serve para validar o déficit (polos que recebem pacientes de fora devem ter superávit ou estar perto disso) e para visualização. Grão: residência × ocorrência × ano × tipo de leito derivado.
- O tipo de leito da AIH é derivado da **especialidade do leito da AIH (campo ESPEC)** via seed `seeds/mapa_espec_sih.csv` (clínico, cirúrgico, obstétrico, pediátrico).
- A UTI é tratada à parte: valor e diárias de UTI da AIH viram as linhas `uti_adulto` / `uti_neo_ped` (pela idade do paciente) em `valor_medio_internacao`, com valor por **diária**.
- Os demais tipos têm valor médio **por AIH** e permanência média em dias. Receita estimada = leitos × ocupação × 365 / permanência × valor_médio_AIH (UTI: leitos × ocupação × 365 × valor_diária).

**Dados de custo: formato estruturado, não texto livre.**
- `dimensionamento_equipe_param`: setor, cbo, `unidade` ∈ {por_leito, por_sala, por_unidade_fixa}, `razao` (profissionais por unidade por turno), `turnos_dia`, `cobertura_dias` (padrão 7), fonte.
- `equipamento_ambiente`: ambiente, equipamento, `unidade` ∈ {por_leito, por_sala, por_hospital}, quantidade_ref, preco_ref, fonte, data_base.
- Nova tabela `custeio_param`: custeio não pessoal (insumos, manutenção, utilidades, serviços) como **percentual do custo de pessoal** por porte, a partir de referências públicas (PNGC/ApuraSUS ou literatura), seed com fonte.
- **Fallback do SomaSUS:** se a raspagem for inviável ou proibida, usar RENEM/SIGEM + Banco de Preços em Saúde. Em último caso, um seed manual com os ~50 equipamentos de maior custo por porte. A cobertura mínima aceitável é ter todos os equipamentos dos ambientes obrigatórios de cada porte (UTI, centro cirúrgico, imagem, PS) com preço. A cobertura alcançada vai para `meta.validacoes`.

**Valores ausentes (política de nulos).**
- `dim_municipio` tem **sempre** todos os municípios da UF (BA = 417). Nenhum aviso remove município.
- Campo ausente fica `NULL` + coluna booleana de disponibilidade (ex.: `receita_disponivel`). Convenção para a Fase 2: um município sem receita continua sendo demanda e candidato, mas contribui **0** ao consórcio (conservador).
- Pares sem rota: `minutos_osrm = NULL`, tratados como fora de alcance.
- Município sem dado CNES é tratado como zero leitos, após checagem de que não é falha de coleta (validação compara com o total de estabelecimentos da UF).

**Datas e correção monetária.**
- Todos os valores monetários da gold estão na data-base. **INCC** só para custo de obra (SINAPI, CUB). **IPCA** para todo o resto (equipamentos, salários RAIS, valores SIH, SIGTAP, receita municipal).
- Séries anuais (RAIS, SICONFI) são corrigidas a partir do mês de dezembro do respectivo ano.
- SIH: **36 competências completas** terminando na última competência publicada no momento da coleta. Cada AIH é corrigida pelo IPCA do mês da competência.
- A data-base efetiva fica registrada em `meta.execucoes`.

**Penalidade por concentração.** É calculada no nível de **município**, pela sede e pela matriz de tempo: nº de estabelecimentos hospitalares e de leitos SUS a até T minutos. Por isso não é preciso geocodificar estabelecimentos. As coordenadas de estabelecimento, se vierem no cadastro do CNES, são carregadas como dado opcional para o mapa, sem obrigação de cobertura.

**Contrato versionado.** O DDL da gold fica em `contracts/gold_schema.sql`, com versão semântica em `contracts/VERSION`. Um teste de contrato no CI compara o banco carregado com o DDL. Na Fase 1, mudanças aditivas (colunas novas) são permitidas, com bump de versão menor. Mudança de tipo ou remoção exige bump maior e nota no CHANGELOG.

**Testes e ambiente.**
- O CI **não acessa a rede**. Usa fixtures mínimas em `tests/fixtures/`, com amostras reais reduzidas (ex.: 5 municípios, poucas AIHs, matriz 5×5).
- Testes de integração com as fontes reais rodam localmente, sob demanda (marcador `pytest -m online`).
- Máquina local verificada: 15,7 GB de RAM, i5-13450HX, ~99 GB livres em D:, Docker 29.8, Codex CLI e agy instalados. Para caber na RAM, o OSRM usa um **recorte da Bahia + buffer de 50 km** extraído do arquivo Nordeste com `osmium`, e não o Nordeste inteiro. Airflow e OSRM não precisam rodar ao mesmo tempo (o DAG `rotas` sobe o OSRM, gera a matriz e o derruba).
- A matriz contém **só municípios da UF** (n² = 417²), em coerência com a exclusão do efeito de fronteira (§3).

## 9. Modelo de decisão (implementação na Fase 2; a base deve suportar)

**Entrada:** orçamento total (R$, na data-base) + parâmetros ajustáveis.

**Decisão:** quantos hospitais, de que porte e em quais municípios. O orçamento **pode ser dividido** entre vários hospitais.

**Catálogo de portes (cumulativos: cada nível inclui o anterior):**

| Porte | Leitos (ilustrativo) | Acrescenta |
|---|---|---|
| H1 Pequeno | ~50 | PS 24h, clínica médica, pediatria, parto de baixo risco, cirurgia geral simples, raio-X, ultrassom, laboratório |
| H2 Médio | ~120 | UTI adulto (~10), ortopedia/traumatologia, centro cirúrgico maior, tomografia |
| H3 Grande | ~250 | UTI ampliada + UTI neonatal, cardiologia com hemodinâmica, cirurgia cardiovascular, ressonância |
| H4 Alta complexidade | ~400 | Neurocirurgia, unidade de AVC, hemodinâmica 24h |

Os leitos por tipo, a área, os equipamentos, a equipe e o custo (faixa mín./méd./máx.) de cada porte são definidos na Fase 2 a partir das tabelas gold. O catálogo inicial (leitos por tipo) fica em `seeds/arquetipos.csv` para ser refinado.

**Custo de cada porte:** construção (área × custo/m²) + equipamentos + 12 meses de operação (equipe × salário × encargos + custeio não pessoal). A soma dos custos dos hospitais escolhidos deve caber no orçamento.

**Demanda:** déficit de leitos **por tipo**, por município (`gold.deficit_leitos`). Um porte só cobre os tipos de leito que oferece. Por isso uma região sem UTI exige pelo menos um H2.

**Cobertura gradual:** um município é atendido por um hospital se a viagem for ≤ **3h** (parâmetro). O peso da cobertura é 100% até **30 min** e cai linearmente até 0 em 3h (ambos ajustáveis).

**Viabilidade (filtro), modelo de consórcio:** um hospital só pode ser instalado se o consórcio formado pela sede + municípios atendidos sustentar a operação a partir do 2º ano:

`Σ (X% × receita_corrente_i × participação_i) + aporte_estadual + receita_SUS_estimada ≥ custo_anual_operação`

- **X = 20%** (padrão, ajustável). Referência a citar: LC 141/2012 exige ≥ 15% da receita própria em saúde em toda a rede, então 20% para um único hospital é deliberadamente agressivo.
- **participação_i** proporcional à população do município i atendida por aquele hospital.
- Um município pertence a **no máximo um** consórcio (não conta a mesma receita duas vezes).
- **aporte_estadual** = valor fixo por leito, configurável (sem número oficial; ver F16 para referência das Policlínicas).
- **receita_SUS_estimada** = leitos × taxa de ocupação (padrão 80%, ajustável) × 365 / permanência média × valor médio de internação.

**Objetivo:** maximizar o **déficit de leitos coberto**, ponderado pela cobertura gradual, menos uma **penalidade explícita** (peso ajustável) para municípios que já concentram hospitais num raio de tempo de viagem.

**Explicação:** cada resultado traz justificativa em linguagem humana, por exemplo: *"cobre 340 mil pessoas a até 90 min; Jequié descartada porque o consórcio cobriria só 70% do custo anual; Feira de Santana penalizada por já ter 12 hospitais num raio de 60 min"*.

**Desempenho esperado:** o modelo para a Bahia (417 candidatos × 4 portes) deve resolver em ~1 s, permitindo chamar o otimizador ao vivo a partir do slider.

## 10. Qualidade de dados (Pandera)

Validações mínimas (cada uma vira uma linha em `meta.validacoes`):
- `dim_municipio` tem exatamente o nº oficial de municípios da UF (BA = 417); cod_ibge único, 7 dígitos, prefixo da UF.
- População > 0; PIB > 0; receita > 0 (municípios sem receita no SICONFI são listados, não inventados).
- Nenhum cod_ibge órfão em tabelas fato (todos existem em `dim_municipio`).
- Conversão 6 → 7 dígitos sem colisão.
- Leitos ≥ 0; soma de leitos SUS ≤ total.
- Matriz de tempo: diagonal = 0; nº de pares = n²; pares sem rota reportados.
- Valores monetários com data-base preenchida e igual à configurada.
- Seeds com coluna `fonte` não vazia.
- Geometrias válidas (`ST_IsValid`) e SRID consistente.

Falha de validação **para** o DAG na camada correspondente. Avisos (ex.: municípios sem receita) seguem, mas aparecem no relatório.

## 11. Orquestração e infraestrutura

- DAGs no Airflow, um por domínio (`ibge`, `cnes`, `sih`, `siconfi`, `custos`, `rotas`) mais um DAG `gold` que depende dos demais. Tarefas idempotentes, reexecutáveis por competência/ano.
- A lógica fica em um pacote Python (`src/hospital_siting/...`), e os DAGs só chamam funções. Assim tudo é testável sem Airflow e roda também por CLI (`python -m hospital_siting.cli run --uf BA`).
- `docker-compose.yml` local: postgres+postgis, airflow (versão leve: LocalExecutor), osrm (sob demanda, perfil separado do compose).
- **Deploy (Fase 2):** o servidor KVM2 recebe só o schema `gold` (dump) + API + interface. Airflow e OSRM nunca rodam no servidor.

## 12. Interface e documentação (orientação para a Fase 2)

- **Interface:** mapa centralizado; **uma** barra lateral com os parâmetros (orçamento, portes permitidos, X%, tempo máximo etc.) e uma seção separada para os filtros do mapa; **caixa de explicação pequena**. O visual fica a critério criativo do Fable, que pode usar um framework se CSS puro não bastar.
- **Página "como funciona"** (HTML + CSS, página única, leitura em < 3 min): problema, passos seguidos, decisões com o porquê, descartes, limitações, como o resultado é calculado. A Fase 1 entrega um esqueleto alimentado por `meta.fontes`/`meta.validacoes` (contagens, datas, checagens que passaram).
- **README:** como reproduzir, arquitetura, seção "avaliado e descartado" (§4) e limitações (§14).

## 13. Execução da Fase 1 com agentes

Claude orquestra, define os testes e integra. A implementação pesada é delegada:
- **Codex CLI** com modelos **5.6** (economia de cota).
- **agy** (Antigravity CLI) preferindo **Sonnet** e **Gemini** (Opus/Sonnet 5.5 compartilham cota; usar Sonnet).
- **Haiku 5.5** implementa os testes especificados por Claude.

Limites para trabalho em paralelo:
- Cada agente trabalha em **seu próprio git worktree e branch**, com **um módulo/diretório designado** (ex.: `src/hospital_siting/ingest/cnes/` + `tests/ingest/cnes/`).
- Proibido editar fora do diretório designado. Arquivos compartilhados (`pyproject.toml`, `config/`, `docker-compose.yml`, contratos de schema) só são alterados por Claude.
- Interfaces entre módulos (assinaturas, schemas Pandera, layout de Parquet) são definidas por Claude **antes** do disparo dos agentes.
- Claude revisa e faz o merge de cada branch, e o CI (lint → testes) precisa passar.
- Os comandos exatos de cada CLI (flags de modelo, sandbox, diretório) são definidos e testados no plano.

## 14. Limitações conhecidas (vão para README e página)

- População tratada como concentrada na sede municipal.
- Tempo de viagem em estrada livre (fator de correção configurável).
- Fronteira estadual ignorada.
- Parâmetros financeiros (X%, aporte estadual, ocupação) são hipóteses, não dados oficiais.
- Custos de referência nacionais/estaduais, não orçamentos de engenharia.
- Snapshot temporal: anos de referência diferentes entre fontes, registrados em metadados.

## 15. Decisões tomadas por Claude (revisar)

1. Cobertura gradual (100% até 30 min, zero em 3h).
2. Déficit por tipo de leito via Portaria 1.631/2015.
3. Catálogo de 4 portes cumulativos (H1–H4), números ilustrativos.
4. Camada `silver` em Parquet antes do Postgres (gold é o único schema de negócio no banco).
5. SIH: últimos 3 anos completos; CNES: competência mais recente.
6. Data-base monetária = mês mais recente do SINAPI; INCC para obra, IPCA para o resto.
7. Taxa de ocupação padrão 80% para receita SUS.
8. Participação no consórcio proporcional à população atendida; cada município em no máximo um consórcio.
9. Lógica em pacote Python e DAGs finos; CLI equivalente.
10. OSRM em perfil separado do compose; fator de correção aplicado só na Fase 2.
11. `data/` fora do git; seeds dentro.
12. Déficit pelo método 2SFCA, com T_oferta padrão de 120 min.
13. SIH como agregado enxuto (validação/visualização), tipo de leito via ESPEC, UTI por diária.
14. Custeio não pessoal como % do custo de pessoal; fallback do SomaSUS definido.
15. Política de nulos: 417 municípios sempre; ausente = NULL + flag; sem receita contribui 0.
16. INCC só para obra, IPCA para o resto; SIH com 36 competências.
17. Penalidade no nível de município (sem geocodificar estabelecimentos).
18. Contrato gold versionado com teste no CI; CI sem rede, com fixtures.
19. OSRM com recorte BA + 50 km para caber em 16 GB de RAM.

## 16. Deixado para o builder

- Estrutura interna de pastas do pacote, nomes de funções, bibliotecas auxiliares (httpx vs requests, etc.).
- Versões exatas das ferramentas (fixadas no `pyproject.toml`/imagens).
- Linter (sugestão: ruff) e formato dos relatórios de validação.
- Se o snapshot gold é publicado como artefato de release no GitHub.

## 17. A verificar no início da Fase 1

- Disponibilidade e termos de uso do SomaSUS para raspagem.
- Proporções de custeio estado × municípios das Policlínicas/consórcios da Bahia.
- Fonte mais atual das regiões de saúde da BA (`geobr` vs PDR SESAB).
- Ano mais recente publicado do PIB municipal e exercício mais recente fechado no SICONFI.
- Disponibilidade e flags atuais do Codex CLI e do agy no terminal do usuário.
