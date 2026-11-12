import pandas as pd

from hospital_siting.custos import renem
from hospital_siting.schemas.silver import EQUIPAMENTO_AMBIENTE

# Formato real da lista RENEM (pd.read_excel(header=None)): linha 0 título, linha 1 cabeçalho, itens a seguir.
RENEM_RAW = pd.DataFrame(
    [
        ["Relação Nacional de Equipamentos Médico-Assistenciais - RENEM 2026", None, None, None, None, None, None],
        [
            "Cod. Item",
            "Item",
            "Definição",
            "Classificação",
            "R$ Valor Sugerido",
            "Item Dolarizado",
            "Especificação Sugerida",
        ],
        [1001, "Ventilador pulmonar", "Ventilação mecânica invasiva", "Equipamento", 85000.0, "Sim", "Esp. A"],
        ["2002", "Monitor multiparamétrico", "Monitorização de sinais vitais", "Equipamento", 12500.5, "Não", None],
    ]
)


def test_renem_parse_lista():
    out = renem.parse_lista(RENEM_RAW)
    assert list(out.columns) == ["cod_item", "item", "classificacao", "valor_sugerido", "dolarizado"]
    assert len(out) == 2  # título e cabeçalho não entram
    assert all(isinstance(c, str) for c in out.cod_item)
    assert out.cod_item.tolist() == ["1001", "2002"]
    assert all(isinstance(v, float) for v in out.valor_sugerido)
    assert out.valor_sugerido.tolist() == [85000.0, 12500.5]
    assert all(isinstance(d, bool) for d in out.dolarizado)
    assert out.dolarizado.tolist() == [True, False]


def test_renem_de_seed_junta_por_cod_item():
    lista = pd.DataFrame(
        {
            "cod_item": ["1001", "2002"],
            "item": ["Ventilador pulmonar", "Monitor multiparamétrico"],
            "classificacao": ["Equipamento", "Equipamento"],
            "valor_sugerido": [85000.0, 12500.5],
            "dolarizado": [True, False],
        }
    )
    seed = pd.DataFrame(
        {
            "ambiente": ["UTI adulto", "UTI adulto", "Centro cirúrgico"],
            "equipamento": ["Ventilador pulmonar", "Monitor multiparamétrico", "Mesa cirúrgica"],
            "cod_item_renem": ["1001", "2002", "9999"],  # 9999 não existe na lista
            "unidade": ["por_leito", "por_leito", "por_sala"],
            "quantidade_ref": [1.0, 1.0, 1.0],
            "fonte": ["Portaria X"] * 3,
            "documento": ["doc.pdf"] * 3,
            "pagina_ou_artigo": ["p. 1", "p. 2", "art. 3"],
            "observacao": [None, None, None],
        }
    )
    out = renem.de_seed(seed, lista, "2026-03")
    EQUIPAMENTO_AMBIENTE.validate(out)
    assert set(out.fonte) == {"RENEM/FNS"}
    assert set(out.mes) == {"2026-03"}
    preco = out.set_index("equipamento").preco_ref
    assert preco["Ventilador pulmonar"] == 85000.0
    assert preco["Monitor multiparamétrico"] == 12500.5
    assert pd.isna(preco["Mesa cirúrgica"])  # sem correspondência na lista
