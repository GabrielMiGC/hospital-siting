"""Seção "Como o resultado é calculado" da página como-funciona (preenche o {{FASE2}} do template)."""

from __future__ import annotations

from html import escape

from hospital_siting.produto.custos import CustoPorte
from hospital_siting.produto.explicacao import reais


def _tabela_custos(custos: dict[str, CustoPorte]) -> str:
    linhas = "".join(
        f"<tr><td><b>{c.porte}</b></td><td>{c.leitos}</td><td>{reais(c.obra)}</td><td>{reais(c.equipamentos)}</td>"
        f"<td>{reais(c.operacao_anual)}</td><td><b>{reais(c.total)}</b></td>"
        f"<td>{reais(c.custo_leito_ano)}</td><td>{escape(', '.join(c.especialidades[-3:]))}</td></tr>"
        for c in custos.values()
    )
    return (
        "<table><thead><tr><th>Porte</th><th>Leitos</th><th>Obra</th><th>Equipamentos</th><th>12 meses de operação</th>"
        "<th>Total</th><th>Operação por leito/ano</th><th>Acrescenta</th></tr></thead>"
        f"<tbody>{linhas}</tbody></table>"
    )


def _exemplo(res) -> str:
    if res is None or not res.hospitais:
        return ""
    itens = "".join(f"<li>{escape(h.justificativa)}</li>" for h in res.hospitais[:5])
    resto = len(res.hospitais) - 5
    mais = f"<li>… e mais {resto} indicações.</li>" if resto > 0 else ""
    descartes = "".join(f"<li>{escape(d.nome)} ({d.porte}): {escape(d.motivo)}.</li>" for d in res.descartados)
    bloco_desc = f"<p>Por que não:</p><ul>{descartes}</ul>" if descartes else ""
    gap = f", a no máximo {res.gap * 100:.1f}% do ótimo".replace(".", ",") if res.gap is not None else ""
    tempo = f"{res.tempo_s:.1f}".replace(".", ",")
    return (
        f"<h3>Exemplo resolvido: {reais(res.orcamento)}</h3>"
        f"<p>{escape(res.mensagem)} Solução {escape(res.status)}{gap}, em {tempo} s.</p>"
        + f"<ul>{itens}{mais}</ul>{bloco_desc}"
    )


def secao_fase2(custos: dict[str, CustoPorte], exemplo=None) -> str:
    return f"""
<p>O otimizador recebe um orçamento e escolhe <b>quantos hospitais, de que porte (H1–H4) e em quais municípios</b>
construir para cobrir o maior déficit de leitos SUS. É um modelo de programação inteira mista (PuLP + HiGHS) que roda
ao vivo a cada mudança de parâmetro na interface.</p>

<h3>1. Quanto custa cada porte</h3>
<p>Obra = área do arquétipo × m² do SINAPI × <b>fator hospitalar</b> (o SINAPI é custo residencial; padrão 2,5×).
Equipamentos = itens da lista RENEM dos ambientes que o porte tem (UTI, centro cirúrgico, imagem, hemodinâmica…).
Operação = equipe exigida pelas normas (RDC 7/2010, COFEN, CFM) convertida em profissionais de 40 h, com 15% de
reserva técnica, salários da RAIS e 70% de encargos, mais a equipe que as normas não cobrem e o custeio não pessoal.</p>
{_tabela_custos(custos)}

<h3>2. Quem é atendido</h3>
<p>A cobertura cai com o tempo de viagem pela estrada (OSRM): 100% até 30 min, linear até zero em 3 h. Cada município
pode ser atendido até o tamanho do seu déficit (2SFCA, Fase 1), e cada hospital atende no máximo os leitos que tem
de cada tipo, então um H1 não cobre déficit de UTI.</p>

<h3>3. Quem paga a operação</h3>
<p>Um hospital só entra se o <b>consórcio</b> o sustenta a partir do 2º ano: 20% da receita corrente dos municípios
consorciados (ponderada pela cobertura) + receita SUS estimada pelo valor médio da AIH + aporte estadual de 40%
(regra das Policlínicas da Bahia) ≥ custo anual de operação. A receita de um município conta para um consórcio só.</p>

<h3>4. O que se maximiza</h3>
<p>Leitos de déficit cobertos, menos uma penalidade por hospital que já existe a até 60 min da sede. Assim o modelo
não escolhe sempre os polos já bem servidos.</p>
<p><b>Prioridade por tipo de leito.</b> Cada leito coberto do tipo t entra no objetivo multiplicado por um peso
π<sub>t</sub>: <code>max Σ π<sub>t</sub>·w·u − λ·Σ H·y − ε·custo</code>. O padrão é <b>todos 1</b>: todo leito de
déficit vale igual, como na formulação original. Quanto vale um leito de UTI frente a um de enfermaria é decisão de
política pública, então a ferramenta não traz valor recomendado: os pesos são ajustáveis na interface (0× a 5×) e na
API (0 a 10). A penalidade λ fica na mesma unidade ponderada: com UTI em 3×, um hospital existente no raio pesa o
mesmo que um terço de leito de UTI. Os números exibidos (leitos cobertos, déficit por tipo) continuam em leitos
reais; quando algum peso é diferente de 1, as justificativas mostram também o total ponderado.</p>

{_exemplo(exemplo)}

<h3>O que os números revelaram</h3>
<ul>
<li>Com os 20% de receita municipal da spec, o consórcio <b>nunca</b> é o gargalo na Bahia: só a sede de um município
de 30 mil habitantes já paga a operação de um H1. A restrição passa a decidir com menos de ~5%.</li>
<li>Por leito, hospitais pequenos são mais baratos de construir e operar, e o objetivo conta todo leito igual: com
orçamentos de até R$ 1 bi o modelo prefere muitos H1 espalhados. Hospitais maiores aparecem quando o orçamento cresce,
quando só se permitem portes maiores ou quando se dá mais peso à UTI na prioridade por tipo de leito. Com R$ 1 bi e
UTI em 3×, saem 1 H4, 5 H2 e 1 H1 (em vez de 21 H1 e 1 H2), com 90 leitos de UTI em vez de 10 e 978 leitos cobertos
em vez de 1.079.</li>
<li>A primeira formulação levava 10–20 s; reescalar o dinheiro para milhões e trocar 36 mil restrições de ligação por
restrições de demanda e capacidade derrubou para poucos segundos, com cobertura igual ou maior.</li>
</ul>
"""
