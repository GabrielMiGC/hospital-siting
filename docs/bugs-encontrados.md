# Bugs encontrados

Registro dos defeitos achados durante a construção da base de dados (Fase 1) e do produto (Fase 2): o que aparecia, por que acontecia, como foi corrigido e qual teste impede a volta. Os mais instrutivos vieram de fontes públicas que não se comportam como a documentação diz.

Cada correção entrou com um teste que falhava antes dela (RED → GREEN).

## Resumo

| # | Área | Bug | Commit |
|---|---|---|---|
| 1 | core | DBF do DATASUS sem terminador de cabeçalho derrubava a leitura | [f1b8dc4] |
| 2 | custos | RAIS 2024 mudou de layout e de extensão | [c723c64] |
| 3 | custos | Fontes de custo planejadas indisponíveis (SomaSUS com login, planilhas SINAPI sem API) | [d774521] |
| 4 | custos | `concat` com quadro vazio trocava o dtype de `valor_m2` | [5527c75] |
| 5 | rotas | Preparo do OSRM dependia de bash/WSL no Windows | [9190792] |
| 6 | rotas | Airflow em contêiner não alcançava o OSRM em `localhost` | [41913c8] |
| 7 | gold | Chave duplicada em `custo_obra_m2` | [a3577be] |
| 8 | indices | INCC com overflow herdado da hiperinflação | [8abae29] |
| 9 | sih | Anos parciais pareciam anos com menos internações | [25bd8ba] |
| 10 | core | Cache de séries mensais congelava os dados | [25bd8ba] |
| 11 | custos | Salário de contrato de 20 h comparado com o de 40 h | [25bd8ba] |
| 12 | custos | Lista RENEM sem mês de referência | [25bd8ba] |
| 13 | custos | Descrição do CBO repetia o código | [de8d661] |
| 14 | meta | `meta.execucoes` no banco ficava uma execução atrasada | [fix/meta-execucoes] |
| 15 | otimizador | Modelo mal escalado: HiGHS gastava segundos só lidando com coeficientes de 1e-5 a 1e9 | feat/fase2 |
| 16 | otimizador | Formulação par a par levava 10–20 s na Bahia | feat/fase2 |
| 17 | explicação | Relatório perdia a cobertura de municípios atendidos por dois hospitais | feat/fase2 |
| 18 | otimizador | PuLP 4 mudou a API (variáveis e retorno do `solve`) | feat/fase2 |
| 19 | interface | Tiles da CARTO passaram a exigir chave de API | feat/fase2 |
| 20 | interface | Mapa abria em zoom 12, fora da Bahia | feat/fase2 |
| 21 | deploy | Compose de deploy recriaria o PostGIS de desenvolvimento | feat/fase2 |
| 22 | deploy | Imagem da API com 2 GB por carregar o pipeline inteiro | feat/fase2 |

## Detalhes

### 1. DBF do DATASUS sem terminador de cabeçalho
- **Sintoma:** `dbfread` falhava ao abrir arquivos do CNES e do SIH já descompactados.
- **Causa:** os DBF do DATASUS não gravam o byte `0x0D` que fecha o cabeçalho, exigido pela especificação e pela biblioteca.
- **Correção:** `read_dbf` tenta o `dbfread` e, se falhar, usa um leitor próprio que confia no tamanho de cabeçalho declarado. Nesse caminho os campos vêm como texto, e os transforms já convertem os tipos.

### 2. RAIS 2024 com layout novo
- **Sintoma:** a leitura dos microdados não encontrava as colunas e os valores saíam errados.
- **Causa:** em 2024 o MTE trocou o separador `;` por `,`, passou a usar ponto decimal, renomeou colunas (`CBO 2002 Ocupação - Código`, `Município - Código`, `Vl Rem Dezembro Nom`), mudou a extensão para `.COMT` e passou a entregar `.7z`.
- **Correção:** o leitor aceita os dois layouts por aliases de coluna, lê em blocos de 500 mil linhas filtrando UF e CBO, e apaga o texto extraído (cerca de 10 GB) depois de gravar a bronze.

### 3. Fontes de custo indisponíveis
- **Sintoma:** as fontes previstas no plano não podiam ser coletadas por um pipeline.
- **Causa:** o SomaSUS exige login gov.br (OAuth), as planilhas do SINAPI da Caixa não têm download estruturado e o CUB do Sinduscon-BA também não.
- **Correção:** SINAPI pela tabela 2296 do SIDRA/IBGE (com API oficial), equipamentos pela lista pública RENEM e CUB opcional por seed. A limitação ficou explícita: o SINAPI é custo médio residencial, e o padrão gravado diz "NÃO é custo hospitalar".

### 4. `concat` com quadro vazio
- **Sintoma:** `valor_m2` virava `object` quando o CUB estava ausente, e a validação Pandera falhava.
- **Causa:** `pd.concat` com um DataFrame vazio sem tipos rebaixa o dtype das colunas.
- **Correção:** só entram no `concat` os quadros não vazios.

### 5. OSRM no Windows
- **Sintoma:** o preparo da malha viária falhava no Windows.
- **Causa:** o `prepare.sh` era chamado com `bash`, que no Windows aponta para o WSL, e a máquina não tinha distribuição instalada.
- **Correção:** os passos `osrm-extract`, `osrm-partition` e `osrm-customize` viraram comandos `docker run` montados em Python, iguais em qualquer sistema.

### 6. Airflow sem acesso ao OSRM
- **Sintoma:** a DAG de rotas não conectava ao serviço de roteamento.
- **Causa:** dentro do contêiner do Airflow, `localhost` é o próprio contêiner.
- **Correção:** URL configurável por `HS_OSRM_URL`, com `localhost` como padrão fora do contêiner.

### 7. Chave duplicada em `custo_obra_m2`
- **Sintoma:** a carga da gold violava a chave primária.
- **Causa:** a série do SINAPI trazia vários meses por padrão, e a gold espera um valor por padrão.
- **Correção:** a gold mantém o mês mais recente de cada padrão, corrigido para a data-base, e guarda o mês de origem em `mes_origem`.

### 8. INCC com overflow
- **Sintoma:** a carga de `indice_correcao` estourava `numeric(14,6)`.
- **Causa:** o número-índice encadeado desde o início da série atravessa a hiperinflação e chega à ordem de 10¹⁸.
- **Correção:** a série é encadeada a partir de 1995-01 (pós-Real), preservando as variações mensais. Valores anteriores a 1995 não são usados pelo modelo.

### 9. Anos parciais no fluxo de internações
- **Sintoma:** o ano corrente parecia ter muito menos internações que os anteriores.
- **Causa:** a gold agrega por ano, e o ano corrente só tem os meses já publicados pelo SIH.
- **Correção:** coluna `n_competencias` em `fluxo_internacoes`, para a Fase 2 anualizar (contrato 1.1.0).
- **Teste:** `test_fluxo_internacoes_informa_meses_por_ano`.

### 10. Cache congelando séries mensais
- **Sintoma:** reexecuções nunca traziam o IPCA, o INCC ou o SINAPI do mês novo.
- **Causa:** o cache em raw era idempotente por URL, e essas URLs não mudam de um mês para o outro.
- **Correção:** `fetch_to_raw(..., max_idade_dias=30)` nas séries móveis (IPCA, INCC, SIDRA de população e PIB, SINAPI, RENEM). Arquivos de competência fechada continuam em cache permanente.
- **Teste:** `test_fetch_to_raw_refaz_quando_cache_velho`.

### 11. Salário por contrato, não por jornada
- **Sintoma:** médicos ganhavam menos que o esperado (médico clínico com cerca de R$ 8 mil).
- **Causa:** a mediana misturava contratos de 20, 24 e 40 horas.
- **Correção:** a remuneração é normalizada para 40 h semanais com `Qtd Hora Contr`, e contratos sem horas são descartados. Médicos subiram entre 21% e 87%, e a enfermagem quase não mudou.
- **Teste:** `test_salario_normalizado_para_40h`.

### 12. RENEM sem mês de referência
- **Sintoma:** preços de equipamentos eram corrigidos a partir do mês do SINAPI, não do mês da própria lista.
- **Causa:** a lista não tem coluna de data; a data aparece só no nome da aba (`Renem 03_03_26`).
- **Correção:** `mes_referencia` extrai o mês da aba, com o mês do SINAPI como reserva.
- **Teste:** `test_renem_mes_referencia_da_aba`.

### 13. Descrição do CBO igual ao código
- **Sintoma:** `gold.salario_ocupacao.descricao` mostrava `225125` em vez de "Medico clinico".
- **Causa:** os microdados da RAIS 2024 trazem só o código da ocupação, e o código servia de reserva para a descrição.
- **Correção:** o pipeline baixa a tabela oficial de ocupações do DATASUS (`TAB_SIH.zip`, `DBF/CBO.dbf`) e falha se algum CBO da seed de equipe ficar sem título. O schema silver passou a recusar descrições formadas só por dígitos.
- **Testes:** `test_descricoes_cbo_da_tabela_datasus`, `test_salarios_falha_sem_descricao_do_cbo`, `test_schema_rejeita_descricao_igual_ao_codigo`.

### 14. `meta.execucoes` atrasada
- **Sintoma:** depois de rodar a gold, a tabela `meta.execucoes` no PostGIS não mostrava essa execução, só a anterior.
- **Causa:** a gold carrega o schema `meta` a partir de `data/meta/execucoes.jsonl` e só depois registra a própria execução no arquivo.
- **Correção:** a gold monta o registro antes da carga e o insere em `meta.execucoes` na mesma transação dos dados. O jsonl só recebe o "ok" depois do commit, e uma falha passa a ser registrada como "fail". A verificação do contrato foi para antes da carga, para que um contrato divergente nem chegue a tocar nos dados.
- **Teste:** `test_run_gold_registra_a_propria_execucao_no_banco`.

## Fase 2 (produto)

### 15. Modelo mal escalado
- **Sintoma:** o HiGHS avisava "Problem is badly scaled" e passava 4 s só no presolve.
- **Causa:** custos e receitas entravam em reais (até 2·10⁹) na mesma matriz que pesos de cobertura (até 10⁻⁵).
- **Correção:** todo valor monetário entra no modelo em R$ milhões; a resposta volta em reais.

### 16. Formulação par a par lenta
- **Sintoma:** 10 a 21 s por otimização com a gold da Bahia (165 candidatos × 4 portes), longe de um slider ao vivo.
- **Causa:** cada par município–hospital tinha uma binária de adesão e uma restrição `z ≤ w·D·x` por tipo de leito (9 mil binárias, 36 mil linhas).
  O log do HiGHS mostrou que a solução a 3% do limite aparecia em 2 s e o resto era gasto fechando o gap.
- **Correção:** o atendimento virou `u_ijt` limitado pelo déficit de cada município e pela capacidade de cada hospital, sem ligação par a par.
  A adesão binária ao consórcio ficou só onde a receita decide a viabilidade (quando a sede sozinha não paga o porte). Gap padrão de 1% e limite de 10 s.
  Resultado: 4–9 s localmente, com cobertura igual ou maior (R$ 3 bi: 3.033 leitos contra 2.948). O teste `test_receita_de_um_municipio_nao_sustenta_dois_consorcios` garante que a receita de um município não conta duas vezes.
- **Ainda longe do "~1 s" da spec.** A API compensa com cache e pré-cálculo dos orçamentos do slider, e a interface mostra o tempo e o gap de cada resposta.

### 17. Cobertura sumindo do relatório
- **Sintoma:** depois da reformulação, o déficit coberto caiu de 1.078 para 908 leitos (R$ 1 bi), o que é impossível para um modelo mais relaxado.
- **Causa:** a explicação só somava a cobertura vinda de municípios do consórcio; com a nova formulação um município pode ser atendido por dois hospitais e é sócio de um só.
- **Correção:** cada hospital soma tudo o que atende; os não sócios aparecem como "atendidos" (linha tracejada no mapa) e não contribuem para o consórcio.
- **Teste:** `test_municipio_atendido_por_dois_hospitais_conta_inteiro_no_relatorio`.

### 18. PuLP 4
- **Sintoma:** `LpVariable(..., cat=...)` dava `TypeError`.
- **Causa:** o PuLP 4.0 (núcleo em Rust) cria variáveis por `prob.add_variable` e devolve estatísticas do `solve` em vez de um código de status.
- **Correção:** o otimizador usa a API nova e lê status e gap de `LpSolveStats`.

### 19. Tiles com chave de API
- **Sintoma:** o mapa mostrava "API KEY REQUIRED".
- **Causa:** os tiles públicos da CARTO passaram a exigir chave.
- **Correção:** o mapa não usa fundo; a malha do IBGE já desenha o estado e o deploy não depende de terceiros.

### 20. Mapa fora de enquadramento
- **Sintoma:** a interface abria em zoom 12 num ponto qualquer.
- **Causa:** o Leaflet mediu o contêiner antes do layout em grid terminar e calculou o enquadramento com tamanho zero.
- **Correção:** `invalidateSize()` antes do `fitBounds`, com folga para os painéis flutuantes.

### 21. Compose de deploy contra o PostGIS local
- **Sintoma (evitado antes de rodar):** subir `docker-compose.deploy.yml` na máquina de desenvolvimento recriaria o contêiner `hs-postgis`.
- **Causa:** os dois arquivos ficam na mesma pasta, então teriam o mesmo nome de projeto e o mesmo serviço `postgis`.
- **Correção:** projeto `hospital-siting-deploy` com volume próprio. O healthcheck consulta `gold.dim_municipio` pela rede, porque durante a restauração o Postgres só escuta no socket e `pg_isready` daria "pronto" cedo demais.

### 22. Imagem de 2 GB
- **Sintoma:** a imagem da API tinha 2,04 GB.
- **Causa:** todas as dependências do pipeline (geopandas, duckdb, pyarrow, datasus…) estavam no núcleo do pacote.
- **Correção:** o pipeline virou o extra `[pipeline]`, instalado pelo Airflow e pelo CI. A imagem da API caiu para 857 MB.

## Achados de modelagem da Fase 2 (não são bugs)
- **O consórcio com 20% da receita nunca é o gargalo na Bahia.** A contribuição da própria sede de um município de 30 mil habitantes já paga a operação de um H1. No orçamento de R$ 1 bi o consórcio mais apertado cobre 167% do custo. A restrição só passa a decidir abaixo de ~5%, e com 1% já descarta candidatos. O slider de receita municipal deixa isso visível.
- **O objetivo favorece hospitais pequenos.** Por leito, um H1 sai mais barato de construir e operar, e o objetivo conta todo leito de déficit igual. Até R$ 1 bi o modelo espalha H1. A UTI só entra quando o orçamento cresce ou quando o usuário restringe os portes. Uma prioridade por tipo de leito seria uma decisão de política pública; não foi inventada.
- **Custo de pessoal subestimado sem ajuste.** As normas cobrem só enfermagem, UTI, centro cirúrgico e PS. O fator "equipe fora das normas" (padrão +100%) cobre médicos de enfermaria, apoio e administração. Mesmo assim a operação fica em ~R$ 0,4–0,6 mi por leito/ano.
- **SINAPI residencial × hospitalar.** O fator hospitalar (padrão 2,5×) é premissa sem fonte primária, ajustável na interface.

## Limitações conhecidas da Fase 2
- A participação de cada município no consórcio é ponderada pelo peso de cobertura (proxy da população atendida).
- Os descartes ("por que não…") vêm de uma avaliação isolada de cada candidato, não de uma reotimização sem ele.
- O snapshot `dist/gold_snapshot.sql.gz` da Fase 1 foi mantido; o deploy usa `dist/gold_snapshot_fase2.sql.gz`, que inclui os equipamentos de ortopedia, hemodinâmica e neurocirurgia.

## Limitações conhecidas da Fase 1 (não corrigidas)
- O CNES não registra quantos estabelecimentos foram descartados na transformação.
- A permanência de enfermaria inclui os dias de UTI da mesma AIH.
- `parse_brl` é ambíguo para números com ponto decimal e sem separador de milhar.
- `ano_pib` quebra a conversão para inteiro se algum município ficar sem PIB.
- O SIH conta também AIHs de continuação (IDENT=5).

[f1b8dc4]: https://github.com/GabrielMiGC/hospital-siting/commit/f1b8dc4
[c723c64]: https://github.com/GabrielMiGC/hospital-siting/commit/c723c64
[d774521]: https://github.com/GabrielMiGC/hospital-siting/commit/d774521
[5527c75]: https://github.com/GabrielMiGC/hospital-siting/commit/5527c75
[9190792]: https://github.com/GabrielMiGC/hospital-siting/commit/9190792
[41913c8]: https://github.com/GabrielMiGC/hospital-siting/commit/41913c8
[a3577be]: https://github.com/GabrielMiGC/hospital-siting/commit/a3577be
[8abae29]: https://github.com/GabrielMiGC/hospital-siting/commit/8abae29
[25bd8ba]: https://github.com/GabrielMiGC/hospital-siting/commit/25bd8ba
[de8d661]: https://github.com/GabrielMiGC/hospital-siting/commit/de8d661
[fix/meta-execucoes]: https://github.com/GabrielMiGC/hospital-siting/tree/fix/meta-execucoes
