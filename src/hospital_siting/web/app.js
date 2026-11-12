"use strict";
// Interface do hospital-siting: mapa Leaflet + parâmetros -> POST /api/otimizar.

const $ = (s) => document.querySelector(s);
const ROTULO = {
  clinico: "clínico", cirurgico: "cirúrgico", obstetrico: "obstétrico", pediatrico: "pediátrico",
  uti_adulto: "UTI adulto", uti_neo_ped: "UTI neo/ped",
};
const PALETA = ["#efece4", "#f7e2c0", "#f3c993", "#eaa96c", "#dc8650", "#c4663a"];
const FORMATO = {
  pct_receita: (v) => `${Math.round(v * 100)}%`,
  t_full: (v) => `${v} min`, t_max: (v) => `${v} min`,
  ocupacao: (v) => `${Math.round(v * 100)}%`,
  fator_hospitalar: (v) => `${(+v).toFixed(1).replace(".", ",")}×`,
  fator_pessoal_nao_normatizado: (v) => `+${Math.round(v * 100)}%`,
  peso_concentracao: (v) => (+v === 0 ? "nenhuma" : `${(+v).toFixed(1).replace(".", ",")} leito`),
  pop_min_candidato: (v) => `${Math.round(v / 1000)} mil`,
};
const vezes = (v) => `${String(+v).replace(".", ",")}×`;
for (const t of Object.keys(ROTULO)) FORMATO[`peso_${t}`] = vezes;
const CAMPOS = Object.keys(FORMATO);

const estado = { orcamentos: [], padroes: {}, geo: null, portes: {}, resultado: null, ativo: null, pedido: 0 };

const reais = (v) => {
  const s = v >= 1e9 ? `${(v / 1e9).toFixed(2)} bi` : `${(v / 1e6).toFixed(1)} mi`;
  return "R$ " + s.replace(".", ",");
};
const inteiro = (v) => Math.round(v).toLocaleString("pt-BR");
const pessoas = (v) => (v >= 1e6 ? `${(v / 1e6).toFixed(1).replace(".", ",")} mi` : `${Math.round(v / 1e3)} mil`);

// ---------- mapa ----------
// Sem mapa de fundo: os 417 municípios já desenham o estado, e o deploy não depende de servidor de tiles.
const mapa = L.map("mapa", { zoomControl: false, preferCanvas: true, minZoom: 5, maxZoom: 11, zoomSnap: 0.25 })
  .setView([-12.9, -41.7], 6);
L.control.zoom({ position: "bottomleft" }).addTo(mapa);
mapa.attributionControl.addAttribution("Malha municipal: IBGE · tempos de viagem: OSRM/OpenStreetMap");
const camadaMun = L.geoJSON(null, { style: estilo, onEachFeature: popupMunicipio }).addTo(mapa);
const camadaLigacoes = L.layerGroup().addTo(mapa);
const camadaDescartes = L.layerGroup().addTo(mapa);
const camadaHospitais = L.layerGroup().addTo(mapa);

function valorCamada(p) {
  const c = document.querySelector("input[name=camada]:checked").value;
  if (c === "deficit_uti") return (p.deficit.uti_adulto || 0) + (p.deficit.uti_neo_ped || 0);
  if (c === "hospitais") return p.hospitais;
  return p[c] || 0;
}

let quebras = [];
function calcularQuebras() {
  const vals = estado.geo.features.map((f) => valorCamada(f.properties)).filter((v) => v > 0).sort((a, b) => a - b);
  quebras = [0.2, 0.4, 0.6, 0.8, 0.95].map((q) => vals[Math.floor(q * (vals.length - 1))] || 0);
  const c = document.querySelector("input[name=camada]:checked");
  const nome = c.parentElement.textContent.trim();
  $("#legenda").innerHTML = `${nome} por município
    <div class="barra" style="background:linear-gradient(90deg,${PALETA.join(",")})"></div>
    <div class="extremos"><span>0</span><span>${inteiro(vals[vals.length - 1] || 0)}</span></div>`;
}
function cor(v) {
  if (!(v > 0)) return PALETA[0];
  let i = 1;
  while (i < PALETA.length - 1 && v > quebras[i - 1]) i++;
  return PALETA[i];
}
function estilo(f) {
  return { color: "#ffffff", weight: 0.6, fillColor: cor(valorCamada(f.properties)), fillOpacity: 0.85 };
}
function popupMunicipio(f, layer) {
  layer.on("click", () => {
    const p = f.properties;
    const tipos = Object.entries(p.deficit).sort((a, b) => b[1] - a[1])
      .map(([t, v]) => `${ROTULO[t]} ${v.toFixed(0)}`).join(", ") || "sem déficit (superávit acessível)";
    layer.bindPopup(`<b>${p.nome}</b><br>${inteiro(p.populacao)} hab. · ${p.regiao_saude || ""}<br>
      Déficit: <b>${p.deficit_total.toFixed(0)}</b> leitos (${tipos})<br>
      ${p.hospitais} hospitais, ${inteiro(p.leitos_sus)} leitos SUS no município`).openPopup();
  });
}

// ---------- parâmetros ----------
function lerParametros() {
  const corpo = { orcamento: estado.orcamentos[+$("#orcamento").value] };
  corpo.portes = [...document.querySelectorAll(".porte input:checked")].map((i) => i.value);
  for (const c of CAMPOS) corpo[c] = +$("#" + c).value;
  return corpo;
}
function atualizarRotulos() {
  $("#orcamento-valor").textContent = reais(estado.orcamentos[+$("#orcamento").value] || 0);
  for (const c of CAMPOS) {
    const o = document.querySelector(`output[data-for=${c}]`);
    if (o) o.textContent = FORMATO[c]($("#" + c).value);
  }
}
let temporizador;
function agendar() {
  atualizarRotulos();
  clearTimeout(temporizador);
  temporizador = setTimeout(otimizar, 400);
}

async function otimizar() {
  const corpo = lerParametros();
  if (!corpo.portes.length) {
    $("#mensagem").textContent = "Escolha ao menos um porte.";
    return;
  }
  if (corpo.t_max <= corpo.t_full) {
    $("#mensagem").textContent = "O tempo em que a cobertura zera precisa ser maior que o de cobertura total.";
    return;
  }
  const n = ++estado.pedido;
  const inicio = performance.now();
  const relogio = setInterval(() => { $("#cronometro").textContent = `${((performance.now() - inicio) / 1000).toFixed(0)} s`; }, 250);
  const aviso = setTimeout(() => { $("#calculando").hidden = false; }, 250);
  try {
    const r = await fetch("api/otimizar", { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify(corpo) });
    const d = await r.json();
    if (n !== estado.pedido) return; // chegou uma resposta mais nova
    if (!r.ok) throw new Error(d.detail ? JSON.stringify(d.detail) : r.statusText);
    estado.resultado = d;
    estado.ativo = null;
    desenhar();
  } catch (e) {
    if (n === estado.pedido) $("#mensagem").textContent = `Erro ao otimizar: ${e.message}`;
  } finally {
    clearTimeout(aviso);
    clearInterval(relogio);
    if (n === estado.pedido) $("#calculando").hidden = true;
  }
}

// ---------- resultado ----------
function desenhar() {
  const d = estado.resultado;
  const pct = d.deficit_total ? (100 * d.deficit_coberto) / d.deficit_total : 0;
  const pop = d.hospitais.reduce((s, h) => s + h.populacao_atendida, 0);
  $("#kpis").innerHTML = [
    [`${inteiro(d.deficit_coberto)}`, `leitos de déficit cobertos (${pct.toFixed(1).replace(".", ",")}% da UF)`],
    [pessoas(pop), "pessoas atendidas (ponderado pelo tempo)"],
    [d.hospitais.length, d.hospitais.length === 1 ? "hospital indicado" : "hospitais indicados"],
  ].map(([v, t]) => `<div class="kpi"><b>${v}</b><span>${t}</span></div>`).join("");
  $("#mensagem").textContent = d.mensagem;
  const gap = d.gap == null ? "" : ` · a no máximo ${(Math.max(d.gap, 0) * 100).toFixed(1).replace(".", ",")}% do ótimo`;
  $("#meta").textContent = `Solução ${d.status}${gap} · ${d.n_candidatos} candidatos · ${d.cache ? "resposta em cache" : `${d.tempo_s.toFixed(1).replace(".", ",")} s`}`;

  camadaHospitais.clearLayers();
  camadaLigacoes.clearLayers();
  camadaDescartes.clearLayers();
  const lista = $("#lista");
  lista.innerHTML = "";
  d.hospitais.forEach((h, idx) => {
    const tam = { H1: 22, H2: 28, H3: 34, H4: 40 }[h.porte];
    const icone = L.divIcon({ className: "", html: `<div class="marcador-h" style="width:${tam}px;height:${tam}px">${h.porte}</div>`, iconSize: [tam, tam] });
    const m = L.marker([h.lat, h.lon], { icon: icone, zIndexOffset: 1000 }).addTo(camadaHospitais);
    m.bindTooltip(`${h.porte} em ${h.nome}`);
    m.on("click", () => ativar(idx));
    lista.appendChild(cartao(h, idx));
  });
  desenharLigacoes();
  if ($("#ver-descartes").checked) desenharDescartes();
  $("#descartes").innerHTML = d.descartados.length
    ? `<h2>Por que não…</h2>` + d.descartados.map((x) => `<p class="descarte"><b>${x.nome}</b> (${x.porte}): ${x.motivo}.</p>`).join("")
    : "";
  $("#n-indicacoes").textContent = d.hospitais.length ? `(${d.hospitais.length})` : "";
  $("#indicacoes").hidden = !d.hospitais.length && !d.descartados.length;
}

function desenharLigacoes() {
  camadaLigacoes.clearLayers();
  if (!$("#ver-consorcios").checked || !estado.resultado) return;
  const centro = Object.fromEntries(estado.geo.features.map((f) => [f.properties.cod_ibge, f.properties._c]));
  estado.resultado.hospitais.forEach((h, idx) => {
    const ativo = estado.ativo === idx;
    for (const m of h.municipios) {
      if (m.cod_ibge === h.cod_ibge || !centro[m.cod_ibge]) continue;
      L.polyline([centro[m.cod_ibge], [h.lat, h.lon]], {
        color: "#0f6e6a", weight: ativo ? 2 : 1, opacity: (ativo ? 0.9 : 0.35) * (0.3 + 0.7 * m.peso),
        dashArray: m.consorciado ? null : "3 4", interactive: false,
      }).addTo(camadaLigacoes);
    }
  });
}

function desenharDescartes() {
  camadaDescartes.clearLayers();
  for (const x of estado.resultado.descartados) {
    const f = estado.geo.features.find((g) => g.properties.cod_ibge === x.cod_ibge);
    if (!f) continue;
    L.circleMarker(f.properties._c, { radius: 7, color: "#8a8f96", weight: 2, fillOpacity: 0, dashArray: "2 3" })
      .bindTooltip(`${x.nome} (${x.porte}) descartado: ${x.motivo}`).addTo(camadaDescartes);
  }
}

function cartao(h, idx) {
  const li = document.createElement("li");
  li.className = "cartao";
  const v = h.viabilidade;
  const tipos = Object.entries(h.deficit_por_tipo).sort((a, b) => b[1] - a[1])
    .map(([t, x]) => `<tr><td>${ROTULO[t]}</td><td>${x.toFixed(0)} leitos</td></tr>`).join("");
  const c = h.custo;
  li.innerHTML = `
    <h3><span>${h.nome}</span><span class="selo">${h.porte} · ${c.leitos} leitos</span></h3>
    <p class="resumo">Cobre <b>${h.deficit_coberto.toFixed(0)}</b> leitos de déficit · ${pessoas(h.populacao_90min)} pessoas a até 90 min · ${reais(c.total)}</p>
    <div class="detalhe">
      <p>${h.justificativa}</p>
      <table>${tipos}</table>
      <p><b>Custos</b> (data-base)</p>
      <table>
        <tr><td>Obra (${inteiro(c.area_m2)} m²)</td><td>${reais(c.obra)}</td></tr>
        <tr><td>Equipamentos</td><td>${reais(c.equipamentos)}</td></tr>
        <tr><td>12 meses de operação (${inteiro(c.fte)} profissionais normatizados)</td><td>${reais(c.operacao_anual)}</td></tr>
      </table>
      <p><b>Consórcio</b> (custeio anual a partir do 2º ano): ${v.cobertura_pct.toFixed(0)}% do custo de operação</p>
      <div class="viab"><i style="width:${Math.min(100, v.cobertura_pct)}%"></i></div>
      <table>
        <tr><td>Municípios (${h.municipios.filter((m) => m.consorciado).length})</td><td>${reais(v.contribuicao_municipal)}</td></tr>
        <tr><td>Receita SUS estimada</td><td>${reais(v.receita_sus)}</td></tr>
        <tr><td>Aporte estadual</td><td>${reais(v.aporte_estadual)}</td></tr>
        <tr><td>Custo anual de operação</td><td>${reais(v.custo_operacao_anual)}</td></tr>
      </table>
      <p>Especialidades: ${c.especialidades.join(", ")}.</p>
    </div>`;
  li.addEventListener("click", () => ativar(idx));
  return li;
}

function ativar(idx) {
  estado.ativo = estado.ativo === idx ? null : idx;
  document.querySelectorAll(".cartao").forEach((el, i) => el.classList.toggle("ativo", i === estado.ativo));
  desenharLigacoes();
  if (estado.ativo != null) {
    const h = estado.resultado.hospitais[idx];
    mapa.flyTo([h.lat, h.lon], Math.max(mapa.getZoom(), 8), { duration: 0.6 });
    document.querySelectorAll(".cartao")[idx].scrollIntoView({ block: "nearest", behavior: "smooth" });
  }
}

function enquadrar() {
  mapa.invalidateSize();
  const largo = window.innerWidth > 900;
  // Deixa espaço para a caixa de explicação (esquerda/topo) e a lista de indicações (direita).
  mapa.fitBounds(camadaMun.getBounds(), largo ? { paddingTopLeft: [40, 150], paddingBottomRight: [370, 20] } : { padding: [10, 10] });
}

// ---------- inicialização ----------
async function iniciar() {
  const [par, geo, portes] = await Promise.all([
    fetch("api/parametros").then((r) => r.json()),
    fetch("api/municipios").then((r) => r.json()),
    fetch("api/portes").then((r) => r.json()),
  ]);
  estado.orcamentos = par.orcamentos_sugeridos;
  estado.padroes = par.padroes;
  $("#orcamento").max = estado.orcamentos.length - 1;
  $("#orcamento").value = estado.orcamentos.indexOf(1e9);
  $("#data-base").textContent = par.data_base;

  $("#portes").innerHTML = portes.map((p) => `
    <label class="porte" title="${p.especialidades.join(", ")}">
      <input type="checkbox" value="${p.porte}" checked>
      <span>${p.porte}<small>${p.leitos} leitos</small><small>${reais(p.total)}</small></span>
    </label>`).join("");

  for (const f of geo.features) {
    const c = L.geoJSON(f).getBounds().getCenter();
    f.properties._c = [c.lat, c.lng];
  }
  estado.geo = geo;
  calcularQuebras();
  camadaMun.addData(geo);
  enquadrar();
  window.addEventListener("resize", () => mapa.invalidateSize());

  document.querySelectorAll(".lateral input[type=range], .porte input").forEach((el) => el.addEventListener("input", agendar));
  document.querySelectorAll("input[name=camada]").forEach((el) => el.addEventListener("change", () => {
    calcularQuebras();
    camadaMun.setStyle(estilo);
  }));
  $("#ver-consorcios").addEventListener("change", desenharLigacoes);
  $("#ver-descartes").addEventListener("change", () => (estado.resultado && $("#ver-descartes").checked ? desenharDescartes() : camadaDescartes.clearLayers()));
  $("#restaurar").addEventListener("click", () => {
    for (const c of CAMPOS) $("#" + c).value = estado.padroes[c];
    agendar();
  });
  atualizarRotulos();
  otimizar();
}

iniciar().catch((e) => { $("#mensagem").textContent = `Falha ao carregar a base: ${e.message}`; });
