# Prioridade por tipo de leito — design

Data: 2026-11-12 · Fase 2, incremento do otimizador (`produto/otimizador.py`)

## Por quê

O objetivo do MILP conta todo leito de déficit atendido igual (`Σ w·u`). Por leito, um H1 é mais barato de construir e
operar, então, até R$ 1 bi, o modelo espalha H1 e a UTI quase não entra (achado em `docs/bugs-encontrados.md`,
"Achados de modelagem da Fase 2"). Dar mais peso a tipos críticos (UTI) resolve isso, mas **quanto mais peso é uma
decisão de política pública**.

## Decisão do usuário (2026-11-12)

Pesos **ajustáveis na interface, com padrão neutro: todos 1**, o que reproduz exatamente o comportamento atual.
Nenhum valor diferente de 1 vem embutido no código, e nenhum peso é derivado de fonte. Quem usa a ferramenta escolhe
a prioridade e vê o efeito.

## Objetivo, não-objetivos, anti-objetivos

- **Objetivo:** cada um dos 6 tipos de `TIPOS_LEITO` tem um peso `π_t ≥ 0`. O objetivo passa a ser
  `max Σ π_t·w_ij·u_ijt − λ·Σ H_j·y_jp − ε·Σ C_p·y_jp`.
- **Não-objetivo:** mudar restrições (demanda, capacidade, orçamento, consórcio), custos ou o déficit da Fase 1.
- **Anti-objetivo:** padrão diferente de 1, ou qualquer valor "sugerido" sem fonte. Com o padrão, o resultado tem que
  ser idêntico ao atual (mesmos hospitais, mesmo déficit coberto).

## Como

- **`Parametros.pesos_leito: dict[str, float]`**, padrão `{t: 1.0 for t in TIPOS_LEITO}`. Uma chave ausente vale 1.
  Uma chave fora de `TIPOS_LEITO` ou um valor negativo gera `ValueError`. Helper `peso_tipo(p, t)`.
- **Objetivo:** o termo de cobertura vira `Σ π_t·w·u`. A penalidade de concentração λ continua em "leitos-equivalentes",
  agora na mesma unidade ponderada. Com UTI = 3, um hospital existente no raio equivale a 1/3 de leito de UTI. A
  página explica isso. O ε continua desempatando por custo.
- **Relatórios em leitos reais:** `deficit_coberto`, `deficit_por_tipo` e os KPIs continuam em leitos, sem ponderação.
  Quando algum peso ≠ 1, `HospitalIndicado` e `Resultado` ganham o valor ponderado (`deficit_ponderado`).
- **Descartes ("por que não…"):** a avaliação isolada passa a pontuar o potencial ponderado, para ficar coerente
  com o objetivo.
- **API:** seis campos planos em `OtimizarEntrada`: `peso_clinico`, `peso_cirurgico`, `peso_obstetrico`,
  `peso_pediatrico`, `peso_uti_adulto` e `peso_uti_neo_ped`, cada um com padrão 1 e faixa 0–10. São campos planos para
  aproveitar `padroes()`, `limites()` e a chave do cache sem mudanças, além de manter o pré-cálculo válido (padrão
  neutro). Em `parametros()` eles viram o dict.
- **Interface:** novo grupo recolhível "Prioridade por tipo de leito" com 6 sliders (0–5, passo 0,5), exibidos como
  `1×`, `3×` e assim por diante, com a nota "todos 1 = todo leito vale igual; é uma escolha de política, não um dado".
  Os sliders entram em `CAMPOS` (ler, rotular, restaurar padrões).
- **Justificativas:** com pesos não neutros, a justificativa de cada hospital acrescenta "com a prioridade escolhida
  (UTI adulto 3×…), vale N leitos ponderados", e `mensagem_geral` cita a ponderação. Com o padrão, o texto continua
  igual.
- **Página como-funciona (`produto/pagina.py`):** a seção 4 explica π_t, o padrão neutro e o efeito em λ. O achado
  "objetivo favorece pequenos" ganha a frase de que agora dá para mudar isso pela prioridade, sem valor padrão.

## Testes

- O padrão reproduz os resultados atuais (todos os testes existentes continuam passando sem mudança).
- Caso pequeno: A tem 10 de déficit clínico e 10 de UTI adulto, D e E têm 10 clínico cada, todos distantes, e o
  orçamento paga três H1 ou um H2. Com pesos 1 saem 3×H1 (30 leitos contra 20). Com UTI adulto = 3 sai H2 em A
  (10 + 3·10 = 40 contra 30).
- Validação: tipo desconhecido ou peso negativo rejeitado em `Parametros` e na API (422).
- API: `/api/parametros` expõe os seis padrões e limites, e o POST com `peso_uti_adulto` muda o resultado.
- Justificativa e página mencionam a ponderação só quando ela existe, e a página sempre explica o mecanismo.
- Gold real (marker `db`): o padrão continua dentro de 10 s. Rodo também R$ 1 bi com UTI 3× para registrar o efeito.

## Fica para o builder

Os textos exatos, a disposição dos sliders e os nomes internos dos helpers.

## Calls feitas por mim (não decididas pelo usuário)

- Campos planos na API, em vez de um dict.
- Faixa 0–10 na API e 0–5 no slider.
- λ na unidade ponderada, sem renormalizar os pesos.
- Relatórios continuam em leitos reais.
