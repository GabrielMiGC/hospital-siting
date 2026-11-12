-- Contrato da camada gold (consumido pela Fase 2). Versão em contracts/VERSION.
-- Convenções: códigos text; dinheiro numeric(14,2) na data-base; contagens integer; geometrias SRID 4674.
-- Mudança aditiva = bump menor; mudança de tipo/remoção = bump maior + CHANGELOG.

CREATE EXTENSION IF NOT EXISTS postgis;
CREATE SCHEMA IF NOT EXISTS gold;
CREATE SCHEMA IF NOT EXISTS meta;

CREATE TABLE IF NOT EXISTS gold.dim_municipio (
    cod_ibge            text PRIMARY KEY,
    nome                text NOT NULL,
    uf                  text NOT NULL,
    populacao           integer NOT NULL,
    ano_populacao       integer NOT NULL,
    pib                 numeric(16,2),
    pib_per_capita      numeric(14,2),
    ano_pib             integer,
    receita_corrente    numeric(16,2),
    exercicio_receita   integer,
    receita_disponivel  boolean NOT NULL,
    cod_regiao_saude    text,
    nome_regiao_saude   text,
    cod_macrorregiao    text,
    geom_sede           geometry(Point, 4674) NOT NULL,
    geom_limite         geometry(MultiPolygon, 4674) NOT NULL
);

CREATE TABLE IF NOT EXISTS gold.leitos_existentes (
    cod_ibge         text NOT NULL,
    tipo_leito       text NOT NULL,
    qtd_total        integer NOT NULL,
    qtd_sus          integer NOT NULL,
    competencia_cnes text NOT NULL,
    PRIMARY KEY (cod_ibge, tipo_leito)
);

CREATE TABLE IF NOT EXISTS gold.estabelecimentos_hospitalares (
    cnes          text PRIMARY KEY,
    cod_ibge      text NOT NULL,
    tipo          text NOT NULL,
    natureza      text NOT NULL,
    leitos_total  integer NOT NULL,
    leitos_sus    integer NOT NULL,
    geom          geometry(Point, 4674)
);

CREATE TABLE IF NOT EXISTS gold.necessidade_leitos_param (
    tipo_leito          text PRIMARY KEY,
    leitos_por_mil_hab  numeric(8,4) NOT NULL,
    fonte               text NOT NULL
);

CREATE TABLE IF NOT EXISTS gold.deficit_leitos (
    cod_ibge              text NOT NULL,
    tipo_leito            text NOT NULL,
    necessidade           numeric(12,2) NOT NULL,
    existente_local_sus   numeric(12,2) NOT NULL,
    oferta_acessivel_sus  numeric(12,2) NOT NULL,
    deficit               numeric(12,2) NOT NULL,
    t_oferta_min          integer NOT NULL,
    PRIMARY KEY (cod_ibge, tipo_leito)
);

CREATE TABLE IF NOT EXISTS gold.fluxo_internacoes (
    cod_ibge_residencia  text NOT NULL,
    cod_ibge_ocorrencia  text NOT NULL,
    ano                  integer NOT NULL,
    tipo_leito           text NOT NULL,
    internacoes          integer NOT NULL,
    valor_total          numeric(16,2) NOT NULL,
    n_competencias       integer NOT NULL,  -- meses do ano presentes na janela SIH
    PRIMARY KEY (cod_ibge_residencia, cod_ibge_ocorrencia, ano, tipo_leito)
);

CREATE TABLE IF NOT EXISTS gold.valor_medio_internacao (
    tipo_leito              text PRIMARY KEY,
    unidade                 text NOT NULL,          -- 'aih' ou 'diaria' (UTI)
    valor_medio             numeric(14,2) NOT NULL,
    permanencia_media_dias  numeric(8,2),
    n_observacoes           integer NOT NULL,
    fonte_periodo           text NOT NULL
);

CREATE TABLE IF NOT EXISTS gold.matriz_tempo_viagem (
    origem        text NOT NULL,
    destino       text NOT NULL,
    minutos_osrm  numeric(10,2),
    km            numeric(10,2),
    PRIMARY KEY (origem, destino)
);

CREATE TABLE IF NOT EXISTS gold.custo_obra_m2 (
    fonte      text NOT NULL,
    padrao     text NOT NULL,
    valor_m2   numeric(14,2) NOT NULL,
    mes_origem text NOT NULL,
    data_base  text NOT NULL,
    PRIMARY KEY (fonte, padrao)
);

CREATE TABLE IF NOT EXISTS gold.equipamento_ambiente (
    ambiente        text NOT NULL,
    equipamento     text NOT NULL,
    unidade         text NOT NULL,
    quantidade_ref  numeric(10,2) NOT NULL,
    preco_ref       numeric(14,2),
    fonte           text NOT NULL,
    data_base       text NOT NULL,
    PRIMARY KEY (ambiente, equipamento)
);

CREATE TABLE IF NOT EXISTS gold.dimensionamento_equipe_param (
    setor           text NOT NULL,
    cbo             text NOT NULL,
    unidade         text NOT NULL,          -- por_leito | por_sala | por_unidade_fixa
    razao           numeric(10,4) NOT NULL, -- profissionais por unidade por turno
    turnos_dia      integer NOT NULL,
    cobertura_dias  integer NOT NULL,
    fonte           text NOT NULL,
    PRIMARY KEY (setor, cbo)
);

CREATE TABLE IF NOT EXISTS gold.salario_ocupacao (
    cbo            text PRIMARY KEY,
    descricao      text NOT NULL,
    salario_medio  numeric(14,2) NOT NULL,
    encargos_pct   numeric(6,4) NOT NULL,
    ano            integer NOT NULL,
    data_base      text NOT NULL
);

CREATE TABLE IF NOT EXISTS gold.indice_correcao (
    indice  text NOT NULL,
    mes     text NOT NULL,
    valor   numeric(14,6) NOT NULL,
    PRIMARY KEY (indice, mes)
);

CREATE TABLE IF NOT EXISTS gold.consorcio_param (
    parametro  text PRIMARY KEY,
    valor      numeric(14,4) NOT NULL,
    fonte      text NOT NULL
);

CREATE TABLE IF NOT EXISTS gold.custeio_param (
    porte                             text PRIMARY KEY,
    custeio_nao_pessoal_pct_pessoal   numeric(6,4) NOT NULL,
    fonte                             text NOT NULL
);

CREATE TABLE IF NOT EXISTS gold.arquetipo_leitos (
    porte        text NOT NULL,
    tipo_leito   text NOT NULL,
    leitos       integer NOT NULL,
    area_m2_ref  numeric(12,2),
    PRIMARY KEY (porte, tipo_leito)
);

CREATE TABLE IF NOT EXISTS meta.fontes (
    fonte        text NOT NULL,
    ref          text NOT NULL,
    filename     text NOT NULL,
    path         text NOT NULL,
    sha256       text NOT NULL,
    url          text NOT NULL,
    bytes        bigint,
    coletado_em  timestamptz NOT NULL,
    PRIMARY KEY (sha256, path)
);

CREATE TABLE IF NOT EXISTS meta.execucoes (
    em       timestamptz NOT NULL,
    uf       text NOT NULL,
    dominio  text NOT NULL,
    status   text NOT NULL,
    extra    jsonb
);

CREATE TABLE IF NOT EXISTS meta.validacoes (
    em       timestamptz NOT NULL,
    uf       text NOT NULL,
    dataset  text NOT NULL,
    "check"  text NOT NULL,
    status   text NOT NULL,
    detalhe  text
);
