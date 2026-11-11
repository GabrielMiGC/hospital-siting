"""Carga idempotente da gold e do schema meta no PostgreSQL/PostGIS (TRUNCATE + INSERT numa transação)."""

from __future__ import annotations

import json

import pandas as pd
import shapely
from sqlalchemy import Engine, text

from hospital_siting.core.config import Config

GEOM_COLS = {
    "dim_municipio": {"geom_sede": "Point", "geom_limite": "MultiPolygon"},
    "estabelecimentos_hospitalares": {"geom": "Point"},
}
ORDEM = [
    "dim_municipio",
    "leitos_existentes",
    "estabelecimentos_hospitalares",
    "necessidade_leitos_param",
    "deficit_leitos",
    "fluxo_internacoes",
    "valor_medio_internacao",
    "matriz_tempo_viagem",
    "custo_obra_m2",
    "equipamento_ambiente",
    "dimensionamento_equipe_param",
    "salario_ocupacao",
    "indice_correcao",
    "consorcio_param",
    "custeio_param",
    "arquetipo_leitos",
]


def _jsonl(path) -> pd.DataFrame:
    if not path.exists():
        return pd.DataFrame()
    return pd.DataFrame([json.loads(x) for x in path.read_text(encoding="utf-8").splitlines() if x.strip()])


def _meta(cfg: Config) -> dict[str, pd.DataFrame]:
    fontes = [_jsonl(m) for m in sorted((cfg.data_dir / "raw").glob("*/manifest.jsonl"))]
    f = pd.concat(fontes, ignore_index=True) if fontes else pd.DataFrame()
    if not f.empty:
        f = f.drop_duplicates(["sha256", "path"])[
            ["fonte", "ref", "filename", "path", "sha256", "url", "bytes", "coletado_em"]
        ]
    ex = _jsonl(cfg.data_dir / "meta" / "execucoes.jsonl")
    if not ex.empty:
        ex["extra"] = ex["extra"].map(lambda d: json.dumps(d, ensure_ascii=False, default=str))
        ex = ex[["em", "uf", "dominio", "status", "extra"]]
    va = _jsonl(cfg.data_dir / "meta" / "validacoes.jsonl")
    if not va.empty:
        va = va[["em", "uf", "dataset", "check", "status", "detalhe"]]
    return {"fontes": f, "execucoes": ex, "validacoes": va}


def _inserir(conn, schema: str, tabela: str, df: pd.DataFrame) -> None:
    if df.empty:
        return
    geos = GEOM_COLS.get(tabela, {})
    plano = pd.DataFrame(df).copy()
    for col in geos:
        plano[col] = [None if g is None else shapely.to_wkb(g, hex=True) for g in plano[col]]
    stg = f"_stg_{tabela}"
    plano.to_sql(stg, conn, schema=schema, if_exists="replace", index=False)
    cols = list(plano.columns)
    sel = []
    for c in cols:
        if c in geos:
            expr = f"ST_SetSRID(ST_GeomFromWKB(decode(\"{c}\", 'hex')), 4674)"
            sel.append(f"ST_Multi({expr})" if geos[c] == "MultiPolygon" else expr)
        elif c == "extra":
            sel.append('"extra"::jsonb')
        elif c in ("em", "coletado_em"):
            sel.append(f'"{c}"::timestamptz')
        else:
            sel.append(f'"{c}"')
    lista = ", ".join(f'"{c}"' for c in cols)
    conn.exec_driver_sql(f'INSERT INTO {schema}."{tabela}" ({lista}) SELECT {", ".join(sel)} FROM {schema}."{stg}"')
    conn.exec_driver_sql(f'DROP TABLE {schema}."{stg}"')


def carregar(cfg: Config, t: dict, engine: Engine) -> None:
    meta = _meta(cfg)
    with engine.begin() as conn:
        tabelas = ", ".join([f"gold.{x}" for x in ORDEM] + [f"meta.{x}" for x in meta])
        conn.execute(text(f"TRUNCATE {tabelas}"))
        for tab in ORDEM:
            _inserir(conn, "gold", tab, t[tab])
        for tab, df in meta.items():
            _inserir(conn, "meta", tab, df)
