# Fase 2 — Produto: custos, otimizador, API e interface

> Data: 2026-11-11 · Complementa `2026-11-11-hospital-siting-design.md` (§9 e §12) · Contrato consumido: `contracts/gold_schema.sql` v1.1.0

## 1. Intenção

Transformar a camada gold da Fase 1 numa ferramenta que um avaliador abre, mexe no orçamento e entende em segundos
**onde** construir hospitais gerais na Bahia, **de que porte** e **por quê**. O otimizador é a vitrine; cada número
que ele mostra precisa ser rastreável até uma tabela gold ou até uma premissa declarada (e ajustável) na tela.

## 2. Objetivos, não-objetivos, anti-objetivos

- **Objetivos:** modelo de custos por porte H1–H4; otimizador MILP (PuLP + HiGHS) que resolve a Bahia em poucos
  segundos; API FastAPI; interface de mapa com sliders; justificativa em linguagem humana; deploy por Docker Compose.
- **Não-objetivos:** hospitais especializados; recalcular o 2SFCA ao vivo; autenticação; múltiplas UFs na interface.
- **Anti-objetivos:** caixa-preta; premissa escondida; o modelo sempre escolher Salvador/Feira (os já bem servidos);
  apresentar o resultado como recomendação oficial.

## 3. Modelo de custos (`hospital_siting.produto.custos`)

Tudo na data-base da gold (2026-09). Função pura `custo_porte(gold, porte, premissas) -> CustoPorte` com detalhamento.

**Obra** = Σ `area_m2_ref` do arquétipo × `valor_m2` (SINAPI) × `fator_hospitalar`.
- O SINAPI é custo médio **residencial**. `fator_hospitalar` padrão **2,5** (faixa exibida 2,0–3,5).
  *Minha decisão:* hospitais exigem instalações de gases medicinais, climatização com filtragem, geradores, reforço
  estrutural e blindagem radiológica; a literatura de orçamentação costuma pôr o m² hospitalar entre 2 e 3,5 vezes o
  residencial. Não há fonte primária verificada: vai como premissa ajustável na interface e em `bugs-encontrados.md`.

**Equipamentos** = Σ itens de `equipamento_ambiente` dos ambientes que o porte tem:
- `por_leito` × leitos do tipo do ambiente (Internação = leitos gerais; UTI adulto = `uti_adulto`; UTI neonatal =
  `uti_neo_ped`); `por_sala` × nº de salas; `por_hospital` × 1.
- Ambientes por porte (cumulativo, spec §9): H1 = Pronto-socorro, Internação, Centro cirúrgico, Imagem (raio-X,
  ultrassom); H2 += UTI adulto, tomógrafo, **Ortopedia** (arco cirúrgico); H3 += UTI neonatal, ressonância,
  **Hemodinâmica** (cardiologia); H4 += **Neurocirurgia** (neuronavegador, microscópio cirúrgico).
- Ortopedia, Hemodinâmica e Neurocirurgia não existiam no seed. *Minha decisão:* acrescentar essas linhas a
  `seeds/equipamentos_ambiente.csv` com o código RENEM (preço vem da lista oficial pelo pipeline da Fase 1, corrigido
  pelo IPCA), em vez de valores soltos no código. Mudança aditiva de dados, sem mudança de contrato.
- Salas cirúrgicas = ⌈leitos cirúrgicos / 15⌉ (RDC 50/2002: uma sala para cada 15 leitos cirúrgicos). Sala de
  emergência do PS = 1. Item sem preço conta zero e é reportado como cobertura de preços.

**Operação (12 meses)** = pessoal assistencial normatizado × (1 + `fator_pessoal_nao_normatizado`) × (1 + custeio).
- Postos por regra de `dimensionamento_equipe_param`: `razao` × unidades (leitos do setor, salas). Nas UTI vale o
  "ou fração" (mínimo 1 por turno). Horas semanais = postos × turnos/dia × 8 h × dias de cobertura;
  FTE = horas / 40 × (1 + IST 15%) (IST = índice de segurança técnica para férias e ausências, usado pelo COFEN).
  O salário da gold já está normalizado para 40 h (bug 11 da Fase 1).
- Custo anual por FTE = `salario_medio` × 12 × (1 + `encargos_pct`) (encargos de 70% incluem 13º, férias, FGTS, INSS).
- Setores → tipos: enfermarias → clínico/cirúrgico/obstétrico/pediátrico; UTI adulto → `uti_adulto`; UTI neonatal →
  `uti_neo_ped` (as regras de UTI pediátrica são idênticas e não são somadas para não contar duas vezes);
  PS observação → leitos de observação = ⌈10% dos leitos⌉ (premissa); PS reanimação → 2 leitos (premissa).
- **Lacuna da Fase 1:** as normas não cobrem médicos de enfermaria, cirurgiões, apoio e administração.
  *Minha decisão:* `fator_pessoal_nao_normatizado` padrão **1,0** (o pessoal fora das normas custa o mesmo que o
  normatizado), ajustável. Sem ele o hospital sairia irrealisticamente barato. A interface mostra o custo por
  leito/ano para comparação.
- Custeio não pessoal = pessoal × `custeio_nao_pessoal_pct_pessoal` do porte (0,25).

## 4. Dados de entrada do otimizador (`hospital_siting.produto.dados`)

`Gold` (dataclass) carregada uma vez do PostGIS (ou construída em memória nos testes): municípios (pop, receita,
nome, coordenadas da sede), déficit positivo por tipo, matriz de tempos (só pares ≤ `t_max`), contagem de
estabelecimentos hospitalares e leitos SUS por município, tabelas de custo. Geometrias simplificadas
(`ST_SimplifyPreserveTopology`) servidas separadamente como GeoJSON.

## 5. Otimizador (`hospital_siting.produto.otimizador`)

Índices: municípios demanda *i*, candidatos *j*, portes *p*, tipos de leito *t*.

- **Peso de cobertura** w_ij = 1 se τ_ij ≤ t_full; (t_max − τ)/(t_max − t_full) até t_max; 0 depois. τ = minutos OSRM ×
  `fator_osrm`.
- **Variáveis:** y_jp ∈ {0,1} (abre porte p em j); x_ij ∈ {0,1} (i entra no consórcio de j, só se w_ij > 0);
  z_ijt ≥ 0 (leitos de déficit do tipo t de i cobertos por j).
- **Restrições:**
  - Σ_p y_jp ≤ 1 (um hospital por município); Σ_j x_ij ≤ 1 (um consórcio por município); x_ij ≤ Σ_p y_jp; x_jj ≥ Σ_p y_jp (a sede pertence ao próprio consórcio).
  - z_ijt ≤ w_ij · D_it · x_ij (cobertura gradual, só déficit positivo).
  - Σ_i z_ijt ≤ Σ_p L_pt · y_jp (capacidade: um porte só cobre os tipos que oferece, até o nº de leitos).
  - Orçamento: Σ C_p · y_jp ≤ B, C_p = obra + equipamentos + 12 meses de operação.
  - **Viabilidade (consórcio, a partir do 2º ano):** Σ_i X · R_i · w_ij · x_ij + SUS_p · y_jp + aporte_p · y_jp ≥ O_p · y_jp,
    com O_p = custo anual de operação; R_i = receita corrente (0 se indisponível); a participação de i é proporcional
    à população atendida, aproximada pelo peso w_ij; SUS_p = receita SUS estimada pela fórmula da spec com
    `valor_medio_internacao`; aporte_p = `pct_estado` × O_p (Policlínicas da BA: Estado 40%) + `aporte_por_leito` × leitos
    (padrão 0).
- **Objetivo:** max Σ z_ijt − λ · Σ_jp H_j · y_jp, onde H_j = nº de estabelecimentos hospitalares a até `t_conc`
  (60 min) da sede de j e λ = `peso_concentracao` em leitos-equivalentes por hospital existente (padrão 1,0); um termo
  ε·custo desempata a favor da solução mais barata.
- **Candidatos:** municípios com população ≥ `pop_min_candidato` (padrão 20 mil; ~165 na BA). *Minha decisão* para
  caber no tempo de resposta e porque hospital de 50+ leitos em município de 5 mil habitantes não é realista; ajustável.
- **Solver:** HiGHS via PuLP, `timeLimit` padrão 20 s, gap relativo 0,5%; status e gap voltam na resposta.

**Explicação** (`hospital_siting.produto.explicacao`): por hospital, municípios do consórcio, população atendida
(Σ pop·w) e a até 90 min, déficit coberto por tipo, custos detalhados, viabilidade (contribuição municipal, SUS,
Estado, % do custo anual coberto), hospitais existentes no raio. Para os 3 melhores candidatos não escolhidos (pela
avaliação isolada), o motivo: consórcio inviável (cobriria só N%), penalidade de concentração, ou orçamento. Texto
curto em português.

## 6. API (`hospital_siting.api`)

FastAPI, Gold carregada no `lifespan`. Rotas:
- `GET /api/saude` · `GET /api/parametros` (padrões e limites) · `GET /api/portes` (custo detalhado H1–H4)
- `GET /api/municipios` (GeoJSON simplificado + população, déficit por tipo, hospitais existentes)
- `POST /api/otimizar` (orçamento + parâmetros → hospitais, justificativa, descartados, totais, status do solver)
- `/` serve a interface estática (`src/hospital_siting/web/`).
Validação com Pydantic (limites dos sliders). Cache LRU por parâmetros.

## 7. Interface (`src/hospital_siting/web/`)

HTML + CSS + JS sem build, Leaflet 1.9.4 por CDN, tiles CARTO claros. Mapa ao centro; **uma** barra lateral com
orçamento (slider logarítmico R$ 50 mi – R$ 5 bi), portes permitidos, X%, tempo 100%/máximo, ocupação, peso da
concentração, fator hospitalar; seção separada de filtros do mapa (camada: déficit total, déficit UTI, população,
hospitais existentes). Caixa de explicação pequena e um painel por hospital. Debounce de 400 ms nos sliders.
Rodapé com link para "como funciona" e aviso de apoio à decisão.

## 8. Documentação, testes, deploy

- `{{FASE2}}` da página "como funciona": tabela de custos por porte, formulação resumida, premissas da Fase 2 e um
  exemplo resolvido (gerado por `python -m hospital_siting.cli docs`, que usa a gold se estiver acessível).
- Testes: custos (contas à mão), cobertura gradual, otimizador com casos pequenos de solução conhecida
  (orçamento só para um hospital → município central; consórcio inviável → descartado; concentração muda a escolha;
  orçamento para dois → dois consórcios disjuntos; porte sem UTI não cobre UTI), API com `TestClient` e Gold falsa.
  Teste `db` opcional contra a gold real.
- Deploy: `Dockerfile` (API + web), `docker-compose.deploy.yml` (PostGIS restaurado do `gold_snapshot.sql.gz` + API).
  Sem domínio próprio: Dokploy gera o endereço. O snapshot não está no git (`dist/`); o compose aceita o caminho do
  snapshot por variável e o README explica como enviá-lo ao servidor.

## 9. Decisões minhas (revisar)

1. `fator_hospitalar` 2,5 sobre o SINAPI. 2. `fator_pessoal_nao_normatizado` 1,0. 3. Salas cirúrgicas pela RDC 50
(15 leitos cirúrgicos/sala). 4. Equipamentos de ortopedia, hemodinâmica e neurocirurgia acrescentados ao seed com
código RENEM. 5. Aporte estadual = 40% do custo anual (consorcio_param), mais um aporte por leito opcional.
6. Participação municipal ponderada pelo peso de cobertura. 7. Candidatos com ≥ 20 mil habitantes.
8. Penalidade em leitos-equivalentes por hospital existente a até 60 min. 9. Leaflet sem build, servido pela API.
10. IST de 15% e turnos de 8 h na conversão de postos em FTE.
