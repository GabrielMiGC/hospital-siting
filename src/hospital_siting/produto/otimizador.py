"""Otimizador de localização (MILP, PuLP + HiGHS). Formulação na spec da Fase 2, §5 (versão revisada).

y_jp ∈ {0,1}: abre o porte p no município j.  u_ijt ≥ 0: déficit do tipo t de i atendido por j.
x_ij ∈ {0,1}: i adere ao consórcio de j (só onde a receita decide a viabilidade de j).

max  Σ π_t·w_ij·u_ijt − λ·Σ H_j·y_jp − ε·Σ C_p·y_jp
     π_t: prioridade do tipo de leito t (padrão 1 = todo leito vale igual; escolha de política, ajustável)
s.a. Σ_p y_jp ≤ 1                                   um hospital por município
     Σ_j u_ijt ≤ D_it                               não atende mais que o déficit
     Σ_i w_ij·u_ijt ≤ Σ_p L_pt·y_jp                 capacidade por tipo (porte sem UTI não cobre UTI)
     Σ C_p·y_jp ≤ B                                 orçamento (obra + equipamentos + 12 meses)
     X·R_j·aberto_j + Σ_i X·R_i·w_ij·x_ij + Σ_p (SUS_p + aporte_p − O_p)·y_jp ≥ 0   viabilidade do consórcio
     Σ_j x_ij + aberto_i ≤ 1;  x_ij ≤ aberto_j        receita de cada município conta uma vez só

A primeira versão ligava cada par por z_ijt ≤ w·D·x_ij (36 mil linhas e 9 mil binárias) e levava 10–20 s na
Bahia; esta resolve em poucos segundos com cobertura igual ou maior (ver docs/bugs-encontrados.md, 15 e 16).
"""

from __future__ import annotations

import time
from collections import defaultdict
from dataclasses import dataclass, field

import numpy as np
import pandas as pd
import pulp

from hospital_siting.produto.cobertura import hospitais_no_raio, peso_cobertura
from hospital_siting.produto.custos import TIPOS_LEITO, CustoPorte, Premissas, custos_portes
from hospital_siting.produto.dados import Gold


@dataclass(frozen=True)
class Parametros:
    orcamento: float
    portes: list[str] = field(default_factory=lambda: ["H1", "H2", "H3", "H4"])
    pct_receita: float = 0.20
    t_full: float = 30.0
    t_max: float = 180.0
    fator_osrm: float = 1.0
    peso_concentracao: float = 1.0  # leitos-equivalentes por hospital existente no raio
    t_conc: float = 60.0
    aporte_por_leito: float = 0.0  # R$/leito/ano, além da fração estadual do consórcio
    pop_min_candidato: int = 20_000
    premissas: Premissas = field(default_factory=Premissas)
    time_limit: float = 10.0
    gap: float = 0.01  # 1%: o HiGHS acha soluções a ~3% do limite em ~2 s; fechar 0,5% custa mais 10 s
    # Prioridade π_t por tipo de leito no objetivo. Tipo ausente vale 1; todos 1 reproduz o modelo sem ponderação.
    # Não há valor padrão diferente de 1: quanto vale um leito de UTI frente a um de enfermaria é decisão de política.
    pesos_leito: dict[str, float] = field(default_factory=dict)

    def __post_init__(self) -> None:
        desconhecidos = set(self.pesos_leito) - set(TIPOS_LEITO)
        if desconhecidos:
            raise ValueError(f"tipo de leito desconhecido em pesos_leito: {sorted(desconhecidos)}")
        if any(not (v >= 0) for v in self.pesos_leito.values()):
            raise ValueError("os pesos por tipo de leito precisam ser ≥ 0")
        completos = {t: float(self.pesos_leito.get(t, 1.0)) for t in TIPOS_LEITO}
        object.__setattr__(self, "pesos_leito", completos)


def peso_tipo(p: Parametros, tipo: str) -> float:
    return p.pesos_leito.get(tipo, 1.0)


def pesos_neutros(p: Parametros) -> bool:
    return all(v == 1.0 for v in p.pesos_leito.values())


@dataclass
class Membro:
    cod_ibge: str
    nome: str
    populacao: int
    minutos: float
    peso: float
    deficit_coberto: float
    contribuicao: float
    consorciado: bool = True  # False: atendido por este hospital, mas sócio de outro consórcio


@dataclass
class Viabilidade:
    contribuicao_municipal: float
    receita_sus: float
    aporte_estadual: float
    custo_operacao_anual: float

    @property
    def cobertura_pct(self) -> float:
        receitas = self.contribuicao_municipal + self.receita_sus + self.aporte_estadual
        return 100 * receitas / self.custo_operacao_anual if self.custo_operacao_anual else 0.0


@dataclass
class HospitalIndicado:
    cod_ibge: str
    nome: str
    porte: str
    lat: float
    lon: float
    custo: CustoPorte
    deficit_coberto: float
    deficit_por_tipo: dict[str, float]
    deficit_ponderado: float  # Σ π_t × leitos do tipo t; igual a deficit_coberto com os pesos padrão
    municipios: list[Membro]
    populacao_atendida: float  # Σ população × peso de cobertura
    populacao_90min: int
    viabilidade: Viabilidade
    hospitais_no_raio: int
    justificativa: str = ""


@dataclass
class Descarte:
    cod_ibge: str
    nome: str
    porte: str
    deficit_potencial: float
    cobertura_consorcio_pct: float
    hospitais_no_raio: int
    motivo: str


@dataclass
class Resultado:
    orcamento: float
    hospitais: list[HospitalIndicado]
    descartados: list[Descarte]
    deficit_coberto: float
    deficit_total: float
    custo_total: float
    status: str
    gap: float | None
    tempo_s: float
    n_candidatos: int
    mensagem: str
    custos_portes: dict[str, CustoPorte]
    data_base: str
    deficit_ponderado: float = 0.0  # Σ π_t × leitos cobertos do tipo t


@dataclass
class _Instancia:
    """Arrays densos do problema, indexados por posição."""

    cods: np.ndarray
    nomes: np.ndarray
    pop: np.ndarray
    receita: np.ndarray
    lat: np.ndarray
    lon: np.ndarray
    D: np.ndarray  # (n, n_tipos) déficit positivo
    cand: np.ndarray  # índices dos candidatos
    pares: pd.DataFrame  # i, j (posições), minutos, w  (w > 0, j candidato)
    H: np.ndarray  # hospitais no raio, por município


def _instancia(gold: Gold, p: Parametros) -> _Instancia:
    mun = gold.municipios.reset_index(drop=True)
    pos = pd.Series(np.arange(len(mun)), index=mun["cod_ibge"])
    D = np.zeros((len(mun), len(TIPOS_LEITO)))
    d = gold.deficit[(gold.deficit["deficit"] > 0) & gold.deficit["tipo_leito"].isin(TIPOS_LEITO)]
    d = d[d["cod_ibge"].isin(pos.index)]
    D[pos[d["cod_ibge"]].to_numpy(), [TIPOS_LEITO.index(t) for t in d["tipo_leito"]]] = d["deficit"].to_numpy()

    receita = np.where(mun["receita_disponivel"].astype(bool), mun["receita_corrente"].astype(float), 0.0)
    cand = np.flatnonzero(mun["populacao"].to_numpy() >= p.pop_min_candidato)

    tm = gold.tempos[gold.tempos["origem"].isin(pos.index) & gold.tempos["destino"].isin(pos.index)]
    pares = pd.DataFrame(
        {"i": pos[tm["origem"]].to_numpy(), "j": pos[tm["destino"]].to_numpy(), "minutos": tm["minutos"].to_numpy()}
    )
    diag = pd.DataFrame({"i": np.arange(len(mun)), "j": np.arange(len(mun)), "minutos": 0.0})
    pares = pd.concat([pares[pares["i"] != pares["j"]], diag], ignore_index=True)
    pares = pares[pares["j"].isin(cand)]
    pares["w"] = peso_cobertura(pares["minutos"].to_numpy(), p.t_full, p.t_max, p.fator_osrm)
    pares = pares[pares["w"] > 0].reset_index(drop=True)

    H = hospitais_no_raio(gold, p.t_conc, p.fator_osrm).reindex(mun["cod_ibge"]).fillna(0).to_numpy()
    return _Instancia(
        cods=mun["cod_ibge"].to_numpy(),
        nomes=mun["nome"].to_numpy(),
        pop=mun["populacao"].to_numpy(dtype=float),
        receita=receita,
        lat=mun["lat"].to_numpy(dtype=float),
        lon=mun["lon"].to_numpy(dtype=float),
        D=D,
        cand=cand,
        pares=pares,
        H=H,
    )


def _economia(custos: dict[str, CustoPorte], gold: Gold, p: Parametros) -> dict[str, float]:
    """Por porte: SUS + aporte estadual − custo anual de operação (termo fixo da restrição de viabilidade)."""
    pct_estado = gold.consorcio.get("pct_estado", 0.0)
    return {
        k: c.receita_sus_anual + pct_estado * c.operacao_anual + p.aporte_por_leito * c.leitos - c.operacao_anual
        for k, c in custos.items()
    }


def _status(stats) -> str:
    nome = stats.status_str
    if nome == "Optimal":
        return "ótimo"
    if stats.has_solution:
        return "limite de tempo"
    return {"Infeasible": "inviável", "Not Solved": "não resolvido"}.get(nome, nome.lower())


def _membros(inst, abertos, cobertura, adesao, w_ij) -> dict[int, list[int]]:
    """Consórcio de cada hospital aberto: cada município entra em no máximo um.

    Prioridade: adesão decidida pelo modelo (onde a receita importa) > a própria sede > o hospital que mais cobre o
    déficit do município > o hospital aberto de maior peso de cobertura (área de influência).
    """
    abertos_set = set(abertos)
    cob_ij = defaultdict(float)
    for (i, j, _), v in cobertura.items():
        cob_ij[(i, j)] += v
    dono: dict[int, int] = dict(adesao)
    for j in abertos:
        dono[j] = j
    alcance = defaultdict(list)
    for (i, j), w in w_ij.items():
        if j in abertos_set:
            alcance[i].append((cob_ij.get((i, j), 0.0), w, j))
    for i, opcoes in alcance.items():
        if i not in dono:
            dono[i] = max(opcoes)[2]
    out = defaultdict(list)
    for i, j in dono.items():
        out[j].append(i)
    return out


def otimizar(gold: Gold, p: Parametros) -> Resultado:
    t0 = time.perf_counter()
    custos_todos = custos_portes(gold, p.premissas)
    custos = {k: c for k, c in custos_todos.items() if k in p.portes}
    inst = _instancia(gold, p)
    deficit_total = float(inst.D.sum())
    vazio = dict(
        orcamento=p.orcamento,
        hospitais=[],
        deficit_coberto=0.0,
        deficit_total=deficit_total,
        custo_total=0.0,
        gap=None,
        n_candidatos=len(inst.cand),
        custos_portes=custos_todos,
        data_base=gold.data_base,
    )
    if not custos:
        return Resultado(
            **vazio,
            descartados=[],
            status="sem portes",
            tempo_s=time.perf_counter() - t0,
            mensagem="Nenhum porte permitido.",
        )
    mais_barato = min(custos.values(), key=lambda c: c.total)
    if mais_barato.total > p.orcamento:
        return Resultado(
            **vazio,
            descartados=[],
            status="sem solução",
            tempo_s=time.perf_counter() - t0,
            mensagem=(
                f"O orçamento é menor que o hospital mais barato permitido "
                f"({mais_barato.porte}: R$ {mais_barato.total / 1e6:,.1f} mi)."
            ).replace(",", "."),
        )

    # Dinheiro em R$ milhões no modelo: com reais os coeficientes iam de 1e-5 a 1e9 e o HiGHS perdia ~15 s
    # só com escala ruim (bug 15 em docs/bugs-encontrados.md).
    MI = 1e6
    eco = {k: v / MI for k, v in _economia(custos, gold, p).items()}
    total = {k: c.total / MI for k, c in custos.items()}
    receita = p.pct_receita * inst.receita / MI
    portes = list(custos)
    oferta = {t: {k: c.leitos_por_tipo.get(t, 0) for k, c in custos.items()} for t in TIPOS_LEITO}
    tipos_ok = [ti for ti, t in enumerate(TIPOS_LEITO) if any(v > 0 for v in oferta[t].values())]
    # Viabilidade redundante: a contribuição da própria sede já paga o porte mais deficitário.
    sede_paga = {j: all(receita[j] + eco[k] >= 0 for k in portes) for j in inst.cand}

    prob = pulp.LpProblem("localizacao_hospitais", pulp.LpMaximize)
    y = {(j, k): prob.add_variable(f"y_{j}_{k}", cat="Binary") for j in inst.cand for k in portes}
    aberto = {j: pulp.lpSum(y[(j, k)] for k in portes) for j in inst.cand}
    pares = inst.pares
    w_ij = dict(zip(zip(pares["i"], pares["j"], strict=True), pares["w"], strict=True))

    # u_ijt: déficit do tipo t de i atendido por j. Leitos usados = w·u (cobertura gradual).
    pi = [peso_tipo(p, t) for t in TIPOS_LEITO]
    u = {}
    ganho = []
    cap = defaultdict(list)
    por_demanda = defaultdict(list)
    for (i, j), w in w_ij.items():
        for ti in tipos_ok:
            dem = inst.D[i, ti]
            if dem <= 0:
                continue
            v = prob.add_variable(f"u_{i}_{j}_{ti}", 0, float(dem))
            u[(i, j, ti)] = (w, v)
            cap[(j, ti)].append(w * v)
            por_demanda[(i, ti)].append(v)
            if pi[ti] > 0:
                ganho.append(pi[ti] * w * v)
    for (i, ti), vs in por_demanda.items():
        if len(vs) > 1:
            prob += pulp.lpSum(vs) <= float(inst.D[i, ti])
    for (j, ti), termos in cap.items():
        prob += pulp.lpSum(termos) <= pulp.lpSum(oferta[TIPOS_LEITO[ti]][k] * y[(j, k)] for k in portes)

    eps = 0.01 / max(p.orcamento / MI, 1.0)
    prob += (
        pulp.lpSum(ganho)
        - pulp.lpSum(p.peso_concentracao * inst.H[j] * y[(j, k)] for (j, k) in y)
        - pulp.lpSum(eps * total[k] * y[(j, k)] for (j, k) in y)
    )
    for j in inst.cand:
        prob += aberto[j] <= 1
    prob += pulp.lpSum(total[k] * y[(j, k)] for (j, k) in y) <= p.orcamento / MI

    # Consórcio: só onde a receita decide a viabilidade há variável de adesão (binária, 1 consórcio por município).
    x = {}
    por_i = defaultdict(list)
    for i, j in w_ij:
        if sede_paga[j] or i == j or receita[i] <= 0:
            continue
        v = prob.add_variable(f"x_{i}_{j}", 0, 1, cat="Binary")
        x[(i, j)] = v
        por_i[i].append(v)
        prob += v <= aberto[j]
    for i, vs in por_i.items():
        sede_aberta = aberto.get(i, 0)
        prob += pulp.lpSum(vs) + sede_aberta <= 1
    for j in inst.cand:
        if sede_paga[j]:
            continue
        contrib = receita[j] * aberto[j] + pulp.lpSum(
            receita[i] * w_ij[(i, jj)] * v for (i, jj), v in x.items() if jj == j
        )
        prob += contrib + pulp.lpSum(eco[k] * y[(j, k)] for k in portes) >= 0

    solver = pulp.HiGHS(msg=False, timeLimit=p.time_limit, gapRel=p.gap)
    stats = prob.solve(solver)
    status = _status(stats)
    gap = float(stats.gap_rel) if stats.gap_rel is not None and np.isfinite(stats.gap_rel) else None

    from hospital_siting.produto.explicacao import descartes, mensagem_geral, montar_hospitais

    escolhidos = [(j, k) for (j, k), v in y.items() if (v.value() or 0) > 0.5]
    cobertura = {chave: w * (v.value() or 0.0) for chave, (w, v) in u.items() if (v.value() or 0.0) > 1e-6}
    adesao = {i: j for (i, j), v in x.items() if (v.value() or 0) > 0.5}
    membros = _membros(inst, [j for j, _ in escolhidos], cobertura, adesao, w_ij)
    hospitais = montar_hospitais(inst, escolhidos, membros, cobertura, w_ij, custos, gold, p)
    custo_total = sum(h.custo.total for h in hospitais)
    coberto = sum(h.deficit_coberto for h in hospitais)
    desc = descartes(inst, hospitais, custos, gold, p, p.orcamento - custo_total)
    res = Resultado(
        orcamento=p.orcamento,
        hospitais=hospitais,
        descartados=desc,
        deficit_coberto=coberto,
        deficit_total=deficit_total,
        custo_total=custo_total,
        status=status,
        gap=gap,
        tempo_s=time.perf_counter() - t0,
        n_candidatos=len(inst.cand),
        mensagem="",
        custos_portes=custos_todos,
        data_base=gold.data_base,
        deficit_ponderado=sum(h.deficit_ponderado for h in hospitais),
    )
    res.mensagem = mensagem_geral(res)
    return res
