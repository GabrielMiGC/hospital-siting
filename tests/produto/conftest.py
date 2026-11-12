import pandas as pd
import pytest

from hospital_siting.produto.dados import Gold


def fazer_gold(
    municipios: list[tuple],
    deficit: list[tuple],
    tempos: dict[tuple[str, str], float],
    estabelecimentos: list[tuple] = (),
) -> Gold:
    """Gold pequena com custos simples.

    municipios: (cod, nome, populacao, receita_corrente|None, lat, lon)
    deficit: (cod, tipo_leito, deficit)
    tempos: {(origem, destino): minutos} — completado com a diagonal e simetria.
    """
    mun = pd.DataFrame(municipios, columns=["cod_ibge", "nome", "populacao", "receita_corrente", "lat", "lon"])
    mun["receita_disponivel"] = mun["receita_corrente"].notna()
    mun["receita_corrente"] = mun["receita_corrente"].fillna(0.0).astype(float)
    pares = {}
    for (o, d), m in tempos.items():
        pares[(o, d)] = m
        pares.setdefault((d, o), m)
    for c in mun["cod_ibge"]:
        pares[(c, c)] = 0.0
    tm = pd.DataFrame([(o, d, m) for (o, d), m in pares.items()], columns=["origem", "destino", "minutos"])
    return Gold(
        municipios=mun,
        deficit=pd.DataFrame(deficit, columns=["cod_ibge", "tipo_leito", "deficit"]),
        tempos=tm,
        estabelecimentos=pd.DataFrame(list(estabelecimentos), columns=["cnes", "cod_ibge", "leitos_sus"]),
        arquetipos=pd.DataFrame(
            [
                ("H1", "clinico", 10, 800.0),
                ("H2", "clinico", 20, 1600.0),
                ("H2", "uti_adulto", 10, 800.0),
            ],
            columns=["porte", "tipo_leito", "leitos", "area_m2_ref"],
        ),
        custo_obra_m2=1000.0,
        equipamentos=pd.DataFrame(
            [
                ("Internação", "Cama", "por_leito", 1.0, 100.0),
                ("UTI adulto", "Monitor", "por_leito", 1.0, 1000.0),
                ("UTI adulto", "Sem preço", "por_leito", 1.0, None),
                ("Imagem", "Aparelho de raios X", "por_hospital", 1.0, 5000.0),
                ("Imagem", "Tomógrafo computadorizado", "por_hospital", 1.0, 50000.0),
                ("Centro cirúrgico", "Mesa cirúrgica", "por_sala", 1.0, 700.0),
            ],
            columns=["ambiente", "equipamento", "unidade", "quantidade_ref", "preco_ref"],
        ),
        equipe=pd.DataFrame(
            [
                ("internacao_clinica_enfermeiro", "1", "por_leito", 0.1, 3, 7),
                ("uti_adulto_enfermeiro_assistencial", "1", "por_leito", 0.1, 3, 7),
            ],
            columns=["setor", "cbo", "unidade", "razao", "turnos_dia", "cobertura_dias"],
        ),
        salarios=pd.DataFrame(
            [("1", "Enfermeiro", 1000.0, 0.7)], columns=["cbo", "descricao", "salario_medio", "encargos_pct"]
        ),
        custeio={"H1": 0.25, "H2": 0.25, "H3": 0.25, "H4": 0.25},
        valor_internacao=pd.DataFrame(
            [("clinico", "aih", 100.0, 5.0), ("uti_adulto", "diaria", 500.0, 4.0)],
            columns=["tipo_leito", "unidade", "valor_medio", "permanencia_media_dias"],
        ),
        consorcio={"pct_estado": 0.4, "pct_municipios": 0.6},
        data_base="2026-09",
    )


@pytest.fixture
def gold_mini() -> Gold:
    return fazer_gold(
        municipios=[("A", "Alfa", 100_000, 1e9, -12.0, -38.0), ("B", "Beta", 50_000, 5e8, -12.5, -38.5)],
        deficit=[("A", "clinico", 30.0), ("B", "clinico", 10.0), ("A", "uti_adulto", 5.0)],
        tempos={("A", "B"): 60.0},
    )
