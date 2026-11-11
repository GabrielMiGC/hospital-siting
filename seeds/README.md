# Seeds curados manualmente (Fase 1)

CSV em UTF-8, separador vírgula, ponto decimal. Toda linha tem `fonte`, `documento`, `pagina_ou_artigo` e `observacao`. Tipos de leito permitidos: `clinico`, `cirurgico`, `obstetrico`, `pediatrico`, `uti_adulto`, `uti_neo_ped` (e `fora_do_escopo` apenas nos mapeamentos). Pesquisa feita em 2026-11-11.

## Arquivos

| Arquivo | Linhas | O que é |
|---|---|---|
| `necessidade_leitos.csv` | 18 | Leitos por mil habitantes, 6 tipos × 3 cenários (coluna `cenario`). Equação do caderno "Parâmetros Assistenciais SUS" (Portaria GM/MS 1.631/2015, versão 2021): leitos = internações × TMP / (365 × ocupação). Cenário 1 = P25 das capitais (Cenário 1 do caderno); Cenário 3 = P75 (Cenário 3 do caderno); **Cenário 2 (padrão do pipeline) = ponto médio entre P25 e P75 de cada parâmetro**, porque o caderno não publica P50. Ocupação 0,72 nos três. A aritmética está em `observacao`. |
| `mapa_leitos_cnes.csv` | 73 | Códigos CODLEITO do CNES (arquivos LT) -> tipo de leito do modelo. Códigos atuais vêm da consulta oficial CnesWeb (DATASUS); 9 códigos históricos/descontinuados (39, 51, 52, 61, 62, 63, 64, 74, 77) vêm da tabela de domínio da wiki do CONASS. |
| `mapa_espec_sih.csv` | 41 | Campo ESPEC (especialidade do leito) da AIH/RD do SIH/SUS -> tipo de leito. Fonte: tabela TabWin `LEITOS.CNV` do DATASUS. |
| `dimensionamento_equipe.csv` | 29 | Profissionais por unidade e por turno: UTI adulto, neonatal e pediátrica (RDC 7/2010 com a RDC 26/2012), enfermarias clínica/cirúrgica/pediátrica/obstétrica (Parecer Normativo COFEN 1/2024), centro cirúrgico (CFM 2.174/2017 e Parecer COFEN 1/2024), pronto-socorro (CFM 2.077/2014). |
| `custeio.csv` | 4 | Custeio não pessoal / pessoal por porte. Valor único 0,25 (SES/DF, pessoal >80% do custo), repetido em H1-H4; corroborado por um estudo de caso de hospital SUS (0,19). |
| `consorcio.csv` | 3 | Financiamento das Policlínicas Regionais (Consórcios Interfederativos de Saúde, Bahia): Estado 40%, municípios 60%, rateio por população. |
| `arquetipos.csv` | 21 | Arquétipos H1-H4 (50/120/250/400 leitos). Leitos gerais repartidos pelas proporções do **Cenário 2** de `necessidade_leitos.csv`. |

## Decisões e avisos importantes

1. **Resolução COFEN 543/2017 está revogada** (Resolução COFEN 743/2024, de 12/03/2024). O dimensionamento de enfermagem das enfermarias usa o **Parecer Normativo COFEN nº 1/2024**, que mantém as horas de enfermagem por paciente (4, 6, 10, 10 e 18 h) e as proporções de enfermeiros (33%, 33%, 36%, 42%, 52%). O parecer é referencial, não coercitivo.
2. **RDC 7/2010, enfermeiro UTI**: o texto original dizia 1 enfermeiro para cada 8 leitos; a **RDC 26/2012** mudou para 1 para cada 10 leitos, com efeito imediato. Usado 0,1. Também suprimiu o técnico adicional de apoio assistencial.
3. `razao` das linhas de UTI: a norma diz "ou fração", isto é, mínimo de 1 por turno por UTI. O modelo deve aplicar teto por unidade.
4. `necessidade_leitos` usa população total (sem ajuste para quem tem plano de saúde) e demografia da Bahia (Censo 2022: 20,25% com 0-14 anos, 15,27% com 60+; 173.686 nascidos vivos em 2022, do Registro Civil). Para outro território, recalcular. Neonatologia em leito geral foi somada ao `pediatrico`.
5. **Cenários** (leitos por mil hab): Cenário 1 clinico 0,8447; cirurgico 0,3549; obstetrico 0,1414; pediatrico 0,1224; uti_adulto 0,0768; uti_neo_ped 0,0139 (gerais 1,46). Cenário 2 (padrão): 1,2547; 0,5571; 0,1612; 0,2026; 0,1743; 0,0356 (gerais 2,18). Cenário 3: 1,7402; 0,8048; 0,1810; 0,3016; 0,3225; 0,0720 (gerais 3,03). **Atenção à nomenclatura**: o "Cenário 2" do caderno (Quadros 47-48) é P25 com recusa 1% (ocupação 0,82), diferente do Cenário 2 deste CSV (interpolado). O caderno só traz 1º e 3º quartis; o ponto médio aritmético não é exatamente a mediana.
6. `mapa_leitos_cnes`: 41 (neonatologia clínica) -> `pediatrico`; 88/89/90/91 (queimados clínico/cirúrgico) -> clínico, pediátrico, cirúrgico, pediátrico; UTI coronariana (85, 86) -> `uti_adulto`; UTI de queimados (83), UCI (92-95), unidades intermediárias, hospital-dia, saúde mental, isolamento, crônicos, reabilitação -> `fora_do_escopo`.
7. `mapa_espec_sih`: os códigos 88-91 foram mapeados como no CNES (desvio da regra literal "todos os outros fora"; marcado em `observacao`). Códigos de UTI na ESPEC (51-86) ficam `fora_do_escopo` conforme instrução; internação em UTI deve ser medida pelos campos de UTI da AIH.
8. `custeio`: **mantido 0,25**; nenhuma fonte primária melhor foi verificável e não há dado por porte. Base: SES/DF (pessoal >80%) e Pereira et al., RAS 23(90), 2023 (pessoal 84,22% => 0,1875). Ambos subestimam o não pessoal se insumos centrais não são alocados; hospitais privados da Anahp (2017) têm razão ~1,0-1,1 (sensibilidade apenas).
9. `consorcio`: `pct_*` são frações (0-1). `criterio_rateio_municipios`=1 significa proporcional à população.
10. `arquetipos`: H3 e H4 têm UTI adulto de ~8,3% do total (como H2: 10/120) e UTI neo/ped pela razão do Cenário 2 (0,0356/0,1743=0,204): 4 e 7 leitos, abaixo de um tamanho operacional típico; o projeto pode querer subir.

## Pendências

- **Área por leito (`area_m2_ref` em `arquetipos.csv`)**: usada premissa de 80 m²/leito (meio da faixa 60-100 m²/leito indicada pelo solicitante). Não achei documento primário verificável. Tentei: SomaSUS/Ministério da Saúde (sem índice acessível), RDC 50/2002 (só áreas por ambiente, não bruta por leito), Portaria MS 400/1977 e acórdão do TCU (Hospital do Paranoá; citado só por resumo de busca, link do Jusbrasil deu 403, e o valor de "45 m²/leito" para a Portaria 400/77 não consta no texto dessa portaria). Os valores de área são premissa, não dado sourced.
- **Custeio por porte (H1-H4)**: sem dado por porte. Segunda rodada: lidos no original o manual da SES/DF e o artigo de Tangará da Serra-MT (RAS 2023, pessoal 84,22% na Tabela 6; o texto do mesmo artigo cita 82,9%). Vistos só em resumos de busca, não conferidos: hospital universitário do Sul (pessoal ~80%), resumo de congresso (75,35%), maternidade de alto risco (63,5%). ApuraSUS/PNGC (apresentações sem percentuais consolidados), TCU/EBSERH (sem proporção pessoal/total) e CONASS não renderam número. ANAHP 2017 lido (p.22): pessoal "quase metade" (privados).
- **Pronto-socorro**: médico por consulta (até 3 pacientes/hora/médico) depende do volume de atendimentos/ano, sem razão por leito ou sala; não gravado. Enfermagem de PS: o Parecer COFEN 1/2024 classifica o PS como Unidade Assistencial Especial (método do sítio funcional/espelho semanal, sem razão fixa); pendente.
- **Médicos das enfermarias (clínica, cirurgia, pediatria, obstetrícia)**: nenhuma norma citável com razão por leito encontrada; pendente. Também pendentes: obstetrícia/centro obstétrico, cirurgiões e auxiliares do centro cirúrgico além de anestesia e enfermagem, equipe de apoio (limpeza, administrativo).
- **Horário do centro cirúrgico** (`turnos_dia`=1, `cobertura_dias`=5): premissa, nenhuma norma define.
- **Médico diarista da UTI**: a RDC 7 não define os dias da semana; adotado 7.
- **CBO de médico emergencista**: a tabela CBO do DATASUS usada não tem código próprio; usado 225125 (médico clínico) como proxy. Conferir na CBO/MTE atualizada (a página mtecbo.gov.br é JSF e não foi consultada diretamente).
- **Códigos 74 e 77 do CNES**: descrição pela tabela CONASS (UTI adulto/pediátrica tipo I); a TabWin SIH diz só "UTI I"/"UTI Infantil I" e uma fonte secundária listou 74 como UTI pediátrica. Conferir em arquivos LT antigos. Os códigos 61, 62, 63, 64 aparecem apenas na tabela CONASS (também uma cópia, de 2023).
- **Consórcio**: uma busca secundária sugeriu mudança para 50/50 em período posterior; não confirmada em documento primário. Vale checar o contrato de rateio vigente do consórcio-alvo.
- **Nascidos vivos**: usado o Registro Civil (IBGE, 173.686), não o SINASC (maior, por sub-registro). Substituir pelo SINASC/TabNet quando disponível.

## Fontes principais

- Parâmetros SUS (cópia hospedada, texto original em estimasus.saude.gov.br): https://mapadasaude.goias.gov.br/documentos/parametros_assistenciais_2_revisao_2021.pdf
- CNES, leitos por tipo: https://cnes2.datasus.gov.br/Mod_Ind_Tipo_Leito.asp?VEstado=00 ; domínio CONASS: https://wiki.conass.org.br/index.php?title=Tabela_de_dom%C3%ADnio_CNES_leito
- SIH, TabWin: ftp://ftp.datasus.gov.br/dissemin/publicos/SIHSUS/200801_/Auxiliar/TAB_SIH.zip
- RDC 7/2010: https://bvsms.saude.gov.br/bvs/saudelegis/anvisa/2010/res0007_24_02_2010.html ; RDC 26/2012: https://bvsms.saude.gov.br/bvs/saudelegis/anvisa/2012/rdc0026_11_05_2012.html
- Parecer Normativo COFEN 1/2024: https://www.cofen.gov.br/wp-content/uploads/2024/10/Parecer-Normativo-Cofen-no-01-2024.pdf
- CFM 2.174/2017 e 2.077/2014: https://sistemas.cfm.org.br/normas/arquivos/resolucoes/BR/2017/2174_2017.pdf ; https://sistemas.cfm.org.br/normas/arquivos/resolucoes/BR/2014/2077_2014.pdf
- SES/DF, Manual de Gestão de Custos Hospitalares (2023); SESAB, Consórcios de Saúde da Bahia: http://www.ba.gov.br/saude/atencao-a-saude/consorcios ; Almeida et al., Cad. Saúde Pública 38(9), 2022.
- IBGE: Censo 2022 (SIDRA 9514) e Registro Civil (SIDRA 2612).
