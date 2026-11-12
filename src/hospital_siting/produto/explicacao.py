"""Monta o resultado legível do otimizador: hospitais indicados, descartes e justificativas em português."""

from __future__ import annotations

import numpy as np

from hospital_siting.produto.custos import TIPOS_LEITO, CustoPorte

ROTULO_TIPO = {
    "clinico": "clínico",
    "cirurgico": "cirúrgico",
    "obstetrico": "obstétrico",
    "pediatrico": "pediátrico",
    "uti_adulto": "UTI adulto",
    "uti_neo_ped": "UTI neo/ped",
}


def reais(v: float) -> str:
    """R$ em milhões/bilhões no formato brasileiro."""
    s = f"{v / 1e9:,.2f} bi" if abs(v) >= 1e9 else f"{v / 1e6:,.1f} mi"
    return "R$ " + s.replace(",", "X").replace(".", ",").replace("X", ".")


def pessoas(n: float) -> str:
    if n >= 1e6:
        return f"{n / 1e6:.1f} milhão".replace(".", ",") if n < 2e6 else f"{n / 1e6:.1f} milhões".replace(".", ",")
    if n >= 1e3:
        return f"{n / 1e3:.0f} mil"
    return f"{n:.0f}"


def montar_hospitais(inst, escolhidos, membros_de, cobertura, w_ij, custos: dict[str, CustoPorte], gold, p) -> list:
    from hospital_siting.produto.otimizador import HospitalIndicado, Membro, Viabilidade

    pct_estado = gold.consorcio.get("pct_estado", 0.0)
    minutos = {(i, j): m for i, j, m in zip(inst.pares["i"], inst.pares["j"], inst.pares["minutos"], strict=True)}
    pesos = w_ij

    out = []
    for j, k in escolhidos:
        c = custos[k]
        membros, por_tipo = [], dict.fromkeys(TIPOS_LEITO, 0.0)
        do_consorcio = set(membros_de[j])
        atendidos = do_consorcio | {i for (i, jj, _) in cobertura if jj == j}
        for i in atendidos:
            w = pesos[(i, j)]
            cob_i = 0.0
            for ti, t in enumerate(TIPOS_LEITO):
                v = cobertura.get((i, j, ti), 0.0)
                por_tipo[t] += v
                cob_i += v
            socio = i in do_consorcio
            membros.append(
                Membro(
                    cod_ibge=str(inst.cods[i]),
                    nome=str(inst.nomes[i]),
                    populacao=int(inst.pop[i]),
                    minutos=round(float(minutos[(i, j)]) * p.fator_osrm, 1),
                    peso=round(float(w), 3),
                    deficit_coberto=cob_i,
                    contribuicao=p.pct_receita * inst.receita[i] * w if socio else 0.0,
                    consorciado=socio,
                )
            )
        membros.sort(key=lambda m: m.minutos)
        viab = Viabilidade(
            contribuicao_municipal=sum(m.contribuicao for m in membros),
            receita_sus=c.receita_sus_anual,
            aporte_estadual=pct_estado * c.operacao_anual + p.aporte_por_leito * c.leitos,
            custo_operacao_anual=c.operacao_anual,
        )
        h = HospitalIndicado(
            cod_ibge=str(inst.cods[j]),
            nome=str(inst.nomes[j]),
            porte=k,
            lat=float(inst.lat[j]),
            lon=float(inst.lon[j]),
            custo=c,
            deficit_coberto=sum(por_tipo.values()),
            deficit_por_tipo={t: v for t, v in por_tipo.items() if v > 1e-6},
            municipios=membros,
            populacao_atendida=sum(m.populacao * m.peso for m in membros if m.consorciado),
            populacao_90min=sum(m.populacao for m in membros if m.consorciado and m.minutos <= 90),
            viabilidade=viab,
            hospitais_no_raio=int(inst.H[j]),
        )
        h.justificativa = _justificativa(h, p)
        out.append(h)
    out.sort(key=lambda h: -h.deficit_coberto)
    return out


def _justificativa(h, p) -> str:
    tipos = sorted(h.deficit_por_tipo.items(), key=lambda kv: -kv[1])[:3]
    detalhe = ", ".join(f"{ROTULO_TIPO[t]} {v:.0f}" for t, v in tipos)
    partes = [
        f"{h.porte} em {h.nome}: cobre {h.deficit_coberto:.0f} leitos de déficit ({detalhe}) "
        f"de {sum(m.deficit_coberto > 0.5 for m in h.municipios)} municípios",
        f"{pessoas(h.populacao_90min)} pessoas a até 90 min",
        f"o consórcio cobre {h.viabilidade.cobertura_pct:.0f}% do custo anual de operação",
    ]
    if h.hospitais_no_raio:
        partes.append(f"{h.hospitais_no_raio} hospitais existentes a até {p.t_conc:.0f} min")
    else:
        partes.append(f"nenhum hospital existente a até {p.t_conc:.0f} min")
    return "; ".join(partes) + "."


def descartes(inst, hospitais, custos: dict[str, CustoPorte], gold, p, restante: float, n: int = 3) -> list:
    """Avalia isoladamente os candidatos não escolhidos e explica por que os mais promissores ficaram de fora."""
    from hospital_siting.produto.otimizador import Descarte

    escolhidos = {h.cod_ibge for h in hospitais}
    ocupados = {m.cod_ibge for h in hospitais for m in h.municipios}
    pct_estado = gold.consorcio.get("pct_estado", 0.0)
    pares = inst.pares
    livres = ~np.isin(inst.cods[pares["i"].to_numpy()], list(ocupados))
    avaliados = []
    for j, grupo in pares[livres].groupby("j"):
        cod = str(inst.cods[j])
        if cod in escolhidos:
            continue
        ii = grupo["i"].to_numpy()
        w = grupo["w"].to_numpy()
        demanda = (inst.D[ii] * w[:, None]).sum(axis=0)
        contrib = float((p.pct_receita * inst.receita[ii] * w).sum())
        sobreposto = bool(np.isin(inst.cods[pares.loc[pares["j"] == j, "i"]], list(ocupados)).any())
        melhor = None
        for k, c in custos.items():
            if c.total > p.orcamento:
                continue
            pot = float(sum(min(c.leitos_por_tipo.get(t, 0), demanda[ti]) for ti, t in enumerate(TIPOS_LEITO)))
            receitas = contrib + c.receita_sus_anual + pct_estado * c.operacao_anual + p.aporte_por_leito * c.leitos
            razao = receitas / c.operacao_anual
            score = pot - p.peso_concentracao * inst.H[j]
            chave = (razao >= 1, score / c.total)  # porte mais eficiente (déficit coberto por real)
            if melhor is None or chave > melhor[0]:
                melhor = (chave, k, pot, razao, score)
        if melhor is None or melhor[2] <= 0:
            continue
        _, k, pot, razao, score = melhor
        avaliados.append((score / custos[k].total, j, k, pot, razao, sobreposto))

    avaliados.sort(key=lambda a: -a[0])
    out = []
    for _, j, k, pot, razao, sobreposto in avaliados[:n]:
        c = custos[k]
        H = int(inst.H[j])
        penal = p.peso_concentracao * H
        if razao < 1:
            motivo = f"consórcio cobriria só {razao * 100:.0f}% do custo anual de operação do {k}"
        elif c.total > restante:
            motivo = f"seria a próxima indicação ({k}) com mais {reais(c.total - max(restante, 0))} de orçamento"
        elif penal > 0.1 * pot:
            motivo = f"penalizada por já ter {H} hospitais a até {p.t_conc:.0f} min"
        elif sobreposto:
            motivo = "parte da região já é atendida pelas indicações escolhidas"
        else:
            motivo = "cobriria menos déficit que as indicações escolhidas"
        out.append(
            Descarte(
                cod_ibge=str(inst.cods[j]),
                nome=str(inst.nomes[j]),
                porte=k,
                deficit_potencial=pot,
                cobertura_consorcio_pct=razao * 100,
                hospitais_no_raio=H,
                motivo=motivo,
            )
        )
    return out


def mensagem_geral(res) -> str:
    if not res.hospitais:
        if res.descartados:
            d = res.descartados[0]
            return f"Nenhuma indicação viável. Melhor candidato: {d.nome} ({d.porte}), descartado porque {d.motivo}."
        return "Nenhuma indicação: não há déficit alcançável pelos candidatos com estes parâmetros."
    pct = 100 * res.deficit_coberto / res.deficit_total if res.deficit_total else 0.0
    uso = 100 * res.custo_total / res.orcamento
    n = len(res.hospitais)
    return (
        f"Com {reais(res.orcamento)}, {'a indicação cobre' if n == 1 else f'as {n} indicações cobrem'} "
        f"{res.deficit_coberto:.0f} dos {res.deficit_total:.0f} leitos de déficit da UF ({pct:.1f}%), "
        f"usando {reais(res.custo_total)} ({uso:.0f}% do orçamento)."
    )
