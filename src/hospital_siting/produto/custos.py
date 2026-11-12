"""Modelo de custos por porte (H1–H4): obra, equipamentos e 12 meses de operação, na data-base da gold."""

from __future__ import annotations

import math
from dataclasses import dataclass, field

from hospital_siting.produto.dados import Gold

LEITOS_GERAIS = ("clinico", "cirurgico", "obstetrico", "pediatrico")
TIPOS_LEITO = (*LEITOS_GERAIS, "uti_adulto", "uti_neo_ped")
ORDEM_PORTES = ("H1", "H2", "H3", "H4")

# Ambientes cumulativos por porte (spec §9).
_AMBIENTES_NOVOS = {
    "H1": {"Pronto-socorro", "Internação", "Centro cirúrgico", "Imagem"},
    "H2": {"UTI adulto", "Ortopedia"},
    "H3": {"UTI neonatal", "Hemodinâmica"},
    "H4": {"Neurocirurgia"},
}
AMBIENTES_POR_PORTE: dict[str, set[str]] = {}
_acum: set[str] = set()
for _p in ORDEM_PORTES:
    _acum = _acum | _AMBIENTES_NOVOS[_p]
    AMBIENTES_POR_PORTE[_p] = set(_acum)

# Equipamentos de imagem que só entram a partir de certo porte (prefixo do nome -> porte mínimo).
EQUIPAMENTO_PORTE_MINIMO = {("Imagem", "Tomógrafo"): "H2", ("Imagem", "Ressonância"): "H3"}

ESPECIALIDADES = {
    "H1": ["PS 24h", "clínica médica", "pediatria", "parto de baixo risco", "cirurgia geral", "raio-X e ultrassom"],
    "H2": ["UTI adulto", "ortopedia e traumatologia", "tomografia"],
    "H3": ["UTI neonatal", "cardiologia com hemodinâmica", "ressonância magnética"],
    "H4": ["neurocirurgia", "unidade de AVC"],
}

# Leitos que multiplicam itens "por_leito" de cada ambiente.
_LEITOS_DO_AMBIENTE = {"Internação": LEITOS_GERAIS, "UTI adulto": ("uti_adulto",), "UTI neonatal": ("uti_neo_ped",)}

# Setor da equipe (prefixo) -> tipos de leito que o dimensionam. UTI pediátrica não é somada: as regras são
# idênticas às da neonatal e os leitos uti_neo_ped são um só grupo (evita contar duas vezes).
_SETOR_LEITOS = {
    "internacao_clinica": ("clinico",),
    "internacao_cirurgica": ("cirurgico",),
    "internacao_obstetrica": ("obstetrico",),
    "internacao_pediatrica": ("pediatrico",),
    "uti_adulto": ("uti_adulto",),
    "uti_neonatal": ("uti_neo_ped",),
    "uti_pediatrica": (),
}


@dataclass(frozen=True)
class Premissas:
    """Premissas da Fase 2 que não vêm da gold. Todas aparecem (e são ajustáveis) na interface."""

    fator_hospitalar: float = 2.5  # m² hospitalar / m² SINAPI residencial
    fator_pessoal_nao_normatizado: float = 1.0  # equipe fora das normas, como fração da normatizada
    ist: float = 0.15  # índice de segurança técnica (férias, ausências)
    horas_turno: float = 8.0
    horas_semana_contrato: float = 40.0
    leitos_cirurgicos_por_sala: float = 15.0  # RDC 50/2002
    pct_obs_ps: float = 0.10  # leitos de observação do PS / leitos do hospital
    leitos_reanimacao: int = 2
    salas_emergencia: int = 1
    ocupacao: float = 0.80


@dataclass(frozen=True)
class CustoPorte:
    porte: str
    leitos: int
    leitos_por_tipo: dict[str, int]
    area_m2: float
    obra: float
    equipamentos: float
    pessoal_anual: float
    custeio_anual: float
    operacao_anual: float
    total: float
    fte: float
    salas_cirurgicas: int
    receita_sus_anual: float
    especialidades: list[str]
    itens_sem_preco: list[str] = field(default_factory=list)

    @property
    def custo_leito_ano(self) -> float:
        return self.operacao_anual / self.leitos if self.leitos else 0.0


def _ate(porte: str) -> list[str]:
    return list(ORDEM_PORTES[: ORDEM_PORTES.index(porte) + 1])


def receita_sus_anual(gold: Gold, leitos_por_tipo: dict[str, int], ocupacao: float) -> float:
    """Spec §8.1: AIH = leitos × ocupação × 365 / permanência × valor; UTI = leitos × ocupação × 365 × diária."""
    vmi = gold.valor_internacao.set_index("tipo_leito")
    total = 0.0
    for tipo, n in leitos_por_tipo.items():
        if n <= 0 or tipo not in vmi.index:
            continue
        r = vmi.loc[tipo]
        if r["unidade"] == "diaria":
            total += n * ocupacao * 365 * r["valor_medio"]
        elif r["permanencia_media_dias"] and r["permanencia_media_dias"] > 0:
            total += n * ocupacao * 365 / r["permanencia_media_dias"] * r["valor_medio"]
    return total


def _equipamentos(gold: Gold, porte: str, leitos: dict[str, int], salas_cc: int, p: Premissas):
    ambientes = AMBIENTES_POR_PORTE[porte]
    total, sem_preco = 0.0, []
    for r in gold.equipamentos.itertuples(index=False):
        if r.ambiente not in ambientes:
            continue
        minimo = next(
            (
                m
                for (a, pref), m in EQUIPAMENTO_PORTE_MINIMO.items()
                if a == r.ambiente and r.equipamento.startswith(pref)
            ),
            None,
        )
        if minimo and porte not in ORDEM_PORTES[ORDEM_PORTES.index(minimo) :]:
            continue
        if r.unidade == "por_leito":
            mult = sum(leitos.get(t, 0) for t in _LEITOS_DO_AMBIENTE.get(r.ambiente, ()))
        elif r.unidade == "por_sala":
            mult = salas_cc if r.ambiente == "Centro cirúrgico" else p.salas_emergencia
        else:
            mult = 1
        if mult <= 0:
            continue
        if r.preco_ref is None or (isinstance(r.preco_ref, float) and math.isnan(r.preco_ref)):
            sem_preco.append(f"{r.ambiente}: {r.equipamento}")
            continue
        total += mult * r.quantidade_ref * r.preco_ref
    return total, sem_preco


def _unidades_setor(setor: str, unidade: str, leitos: dict[str, int], salas_cc: int, p: Premissas) -> float:
    if setor.startswith("centro_cirurgico"):
        return salas_cc
    if setor.startswith("pronto_socorro_observacao"):
        return math.ceil(p.pct_obs_ps * sum(leitos.values()))
    if setor.startswith("pronto_socorro_sala_reanimacao"):
        return p.leitos_reanimacao
    for prefixo, tipos in _SETOR_LEITOS.items():
        if setor.startswith(prefixo):
            return sum(leitos.get(t, 0) for t in tipos)
    return 0


def _pessoal(gold: Gold, leitos: dict[str, int], salas_cc: int, p: Premissas) -> tuple[float, float]:
    """(FTE, custo anual do pessoal normatizado)."""
    sal = gold.salarios.set_index("cbo")
    fte_total = custo = 0.0
    for r in gold.equipe.itertuples(index=False):
        unidades = _unidades_setor(r.setor, r.unidade, leitos, salas_cc, p)
        if unidades <= 0:
            continue
        postos = r.razao * unidades
        if r.setor.startswith("uti_"):  # RDC 7/2010: "1 para cada N leitos ou fração"
            postos = math.ceil(postos - 1e-9)
        horas = postos * r.turnos_dia * p.horas_turno * r.cobertura_dias
        fte = horas / p.horas_semana_contrato * (1 + p.ist)
        s = sal.loc[str(r.cbo)]
        fte_total += fte
        custo += fte * s["salario_medio"] * 12 * (1 + s["encargos_pct"])
    return fte_total, custo


def custo_porte(gold: Gold, porte: str, premissas: Premissas) -> CustoPorte:
    arq = gold.arquetipos[gold.arquetipos["porte"] == porte]
    if arq.empty:
        raise KeyError(f"porte sem arquétipo na gold: {porte}")
    leitos = {r.tipo_leito: int(r.leitos) for r in arq.itertuples(index=False)}
    area = float(arq["area_m2_ref"].fillna(0).sum())
    salas_cc = max(1, math.ceil(leitos.get("cirurgico", 0) / premissas.leitos_cirurgicos_por_sala))

    obra = area * gold.custo_obra_m2 * premissas.fator_hospitalar
    equip, sem_preco = _equipamentos(gold, porte, leitos, salas_cc, premissas)
    fte, pessoal_norm = _pessoal(gold, leitos, salas_cc, premissas)
    pessoal = pessoal_norm * (1 + premissas.fator_pessoal_nao_normatizado)
    custeio = pessoal * gold.custeio[porte]
    operacao = pessoal + custeio
    return CustoPorte(
        porte=porte,
        leitos=sum(leitos.values()),
        leitos_por_tipo=leitos,
        area_m2=area,
        obra=obra,
        equipamentos=equip,
        pessoal_anual=pessoal,
        custeio_anual=custeio,
        operacao_anual=operacao,
        total=obra + equip + operacao,
        fte=fte,
        salas_cirurgicas=salas_cc,
        receita_sus_anual=receita_sus_anual(gold, leitos, premissas.ocupacao),
        especialidades=[e for q in _ate(porte) for e in ESPECIALIDADES[q]],
        itens_sem_preco=sem_preco,
    )


def custos_portes(gold: Gold, premissas: Premissas) -> dict[str, CustoPorte]:
    return {p: custo_porte(gold, p, premissas) for p in gold.portes}
