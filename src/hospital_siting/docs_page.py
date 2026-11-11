"""Gera a página estática 'como funciona' a partir dos metadados do pipeline (data/raw/*/manifest, data/meta)."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from html import escape
from pathlib import Path
from urllib.parse import urlparse

from hospital_siting.core.config import REPO_ROOT, Config

TEMPLATE = REPO_ROOT / "docs" / "como-funciona" / "template.html"
SEM_DADOS = "Ainda não executado"


def _jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    return [json.loads(x) for x in path.read_text(encoding="utf-8").splitlines() if x.strip()]


def _fontes(cfg: Config) -> list[dict]:
    linhas = []
    for m in sorted((cfg.data_dir / "raw").glob("*/manifest.jsonl")):
        entradas = _jsonl(m)
        if not entradas:
            continue
        hosts = sorted({urlparse(e["url"]).netloc for e in entradas})
        linhas.append({
            "fonte": m.parent.name, "arquivos": len(entradas), "refs": sorted({e["ref"] for e in entradas}),
            "em": max(e["coletado_em"] for e in entradas)[:10], "hosts": hosts,
        })
    return linhas


def render(cfg: Config, out: Path) -> Path:
    fontes = _fontes(cfg)
    validacoes = _jsonl(cfg.data_dir / "meta" / "validacoes.jsonl")
    execucoes = _jsonl(cfg.data_dir / "meta" / "execucoes.jsonl")
    gold = next((e for e in reversed(execucoes) if e.get("dominio") == "gold"), None)
    data_base = (gold or {}).get("extra", {}).get("data_base", SEM_DADOS)
    municipios = (gold or {}).get("extra", {}).get("municipios", "—")

    if fontes:
        linhas_f = "".join(
            f"<tr><td>{escape(f['fonte'])}</td><td>{f['arquivos']}</td><td>{escape(', '.join(f['refs'][:6]))}</td>"
            f"<td>{escape(f['em'])}</td><td>{escape(', '.join(f['hosts']))}</td></tr>"
            for f in fontes
        )
    else:
        linhas_f = f"<tr><td colspan='5'>{SEM_DADOS}</td></tr>"

    ultimas: dict[tuple[str, str], dict] = {}
    for v in validacoes:  # mantém o resultado mais recente de cada checagem
        ultimas[(v["dataset"], v["check"])] = v
    if ultimas:
        linhas_v = "".join(
            f"<tr><td>{escape(v['dataset'])}</td><td>{escape(v['check'])}</td>"
            f"<td class='s-{escape(v['status'])}'>{escape(v['status'])}</td>"
            f"<td>{escape(str(v.get('detalhe', ''))[:200])}</td></tr>"
            for v in ultimas.values()
        )
    else:
        linhas_v = f"<tr><td colspan='4'>{SEM_DADOS}</td></tr>"

    n_ok = sum(1 for v in ultimas.values() if v["status"] == "pass")
    kpis = "".join(
        f"<div class='kpi'><b>{escape(str(valor))}</b><span>{escape(rotulo)}</span></div>"
        for valor, rotulo in (
            (municipios, "municípios"), (len(fontes) or "—", "fontes coletadas"),
            (f"{n_ok}/{len(ultimas)}" if ultimas else "—", "checagens aprovadas"), (data_base, "data-base monetária"),
        )
    )
    html = (
        TEMPLATE.read_text(encoding="utf-8")
        .replace("{{KPIS}}", kpis)
        .replace("{{FONTES}}", linhas_f)
        .replace("{{VALIDACOES}}", linhas_v)
        .replace("{{FASE2}}", "O otimizador (Fase 2) consome a camada gold; esta seção será preenchida por ele.")
        .replace("{{GERADO_EM}}", datetime.now(UTC).strftime("%Y-%m-%d %H:%M UTC"))
        .replace("{{UF}}", escape(cfg.uf))
        .replace("{{DATA_BASE}}", escape(str(data_base)))
    )
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(html, encoding="utf-8")
    css = TEMPLATE.parent / "style.css"
    if out.parent.resolve() != css.parent.resolve():
        (out.parent / "style.css").write_text(css.read_text(encoding="utf-8"), encoding="utf-8")
    return out
