"""
Log de execuções — o que já foi processado, por página e por mês.

A `retomada` no topo de cada template responde "qual foi o último período que
rodei AQUI". Esta tela responde a pergunta do fechamento do mês: "de quem ainda
falta?" — que nenhum template consegue responder sozinho, porque cada um só vê
o próprio histórico. Lê o mesmo data/logs/execucoes.jsonl (utils.execution_log)
que as páginas gravam.
"""

import html
import json
from datetime import datetime
from itertools import groupby

import pandas as pd
import streamlit as st

from utils import execution_log
from utils.execution_log import MESES_PT, mes_anterior, mes_seguinte
from utils.page import setup_page
from utils.ui_components import estado_vazio

setup_page(__file__)

# Rótulo por chave de `pagina` no log. A chave é o que cada página passa a
# execution_log.registrar; os templates de Processamento de relatórios usam
# "processamento_relatorios:<slug>" (e o The Orchard, um slug por catálogo).
# Ao criar um template novo lá, registre o rótulo aqui — sem isso ele ainda
# aparece nas duas tabelas, mas com a chave crua.
#
# "Grupo · Item" vira um grupo na grade (o grupo numa linha, os itens
# recuados embaixo); na lista e no filtro o rótulo aparece inteiro.
ROTULOS = {
    "processamento_relatorios:nikita": "Nikita Digital",
    "processamento_relatorios:backoffice": "Backoffice",
    "processamento_relatorios:youtube": "YouTube",
    "processamento_relatorios:warner": "Warner Chappell",
    "processamento_relatorios:orchard:luiza_possi": "The Orchard · Luiza Possi",
    "processamento_relatorios:orchard:zeeba": "The Orchard · Zeeba",
    "processamento_relatorios:orchard:midas": "The Orchard · Midas",
    "processamento_relatorios:orchard:mza": "The Orchard · MZA",
    "processamento_relatorios:imusica": "iMusica (OTT)",
    "processamento_relatorios:claro": "Claro Música",
    "processamento_relatorios:fuga": "FUGA",
    "douglas_cezar_ep": "Douglas Cezar EP",
    "reconciliacao_pagamentos": "Reconciliação de pagamentos",
}

# Páginas que entram na grade mensal: as que gravam um período que é um mês.
# A Reconciliação grava o nome da planilha, então só aparece na lista.
NA_GRADE = [k for k in ROTULOS if k != "reconciliacao_pagamentos"]

# Páginas que processam por trimestre. Para marcar outra, acrescente a chave
# dela aqui (a mesma de ROTULOS). Na grade, isso muda duas coisas:
#   - todo mês gravado vale o trimestre inteiro. A Warner grava só o último
#     mês (202603 = 1º tri/2026), e sem isso jan e fev sairiam como pulados;
#   - o próximo a processar é o trimestre seguinte, desenhado como barra
#     vazada do tamanho que ela vai ter, e não o círculo de um mês.
# Uma página que muda de cadência (a Luiza Possi foi trimestral em 2025 e é
# mensal desde jan/2026) fica como é hoje: o que já foi gravado mês a mês
# continua certo na grade, só o próximo é que segue esta lista.
TRIMESTRAIS = {
    "processamento_relatorios:warner",
    "processamento_relatorios:orchard:zeeba",
}

MESES_NA_GRADE = 6

# Chaves de `resumo` que servem de "total" na lista, em ordem de preferência —
# cada página grava o total com o nome que faz sentido para ela.
CHAVES_TOTAL = ("total_liquido", "final_value_total", "partner_revenue_total", "total_bruto")

# Moeda do total para execuções gravadas antes de o `resumo` trazer "moeda"
# (as páginas passaram a gravá-la em 09/2026). Orchard e YouTube reportam em
# dólar; o resto, em real.
MOEDA_POR_PAGINA = {
    "processamento_relatorios:youtube": "US$",
    "processamento_relatorios:orchard:": "US$",   # prefixo: vale para todo catálogo
}
MOEDA_PADRAO = "R$"


def _rotulo(pagina: str) -> str:
    return ROTULOS.get(pagina, pagina)


def _grupo_e_nome(rotulo: str) -> tuple[str | None, str]:
    grupo, sep, nome = rotulo.partition(" · ")
    return (grupo, nome) if sep else (None, rotulo)


# ---------------------------------------------------------------------------
# Meses (AAAAMM) e datas
# ---------------------------------------------------------------------------

def _janela_meses(hoje: datetime, n: int) -> list[str]:
    """Os últimos `n` meses (AAAAMM), terminando no mês de `hoje`, em ordem."""
    meses = [f"{hoje.year}{hoje.month:02d}"]
    while len(meses) < n:
        meses.append(mes_anterior(meses[-1]))
    return list(reversed(meses))


def _trimestre(aaaamm: str) -> list[str]:
    """Os três meses do trimestre civil que contém `aaaamm`."""
    ano, mes = aaaamm[:4], int(aaaamm[4:6])
    inicio = mes - (mes - 1) % 3
    return [f"{ano}{m:02d}" for m in range(inicio, inicio + 3)]


def _rotulo_mes(aaaamm: str) -> str:
    return f"{MESES_PT[int(aaaamm[4:6]) - 1]}/{aaaamm[2:4]}"


def _rotulo_trimestre(aaaamm: str) -> str:
    return f"{(int(aaaamm[4:6]) - 1) // 3 + 1}º trimestre/{aaaamm[:4]}"


def _data(iso: str) -> datetime | None:
    try:
        return datetime.fromisoformat(iso)
    except (TypeError, ValueError):
        return None


def _data_fmt(iso: str) -> str:
    dt = _data(iso)
    return dt.strftime("%d/%m/%Y") if dt else str(iso)


# ---------------------------------------------------------------------------
# Grade mensal — uma faixa de cobertura por página
# ---------------------------------------------------------------------------
# Meses processados em sequência formam uma barra contínua. A cor fica só para
# a exceção: um mês pulado entre dois processados quebra a barra com o ▲
# terracota das Pendências do Home. O próximo a processar — o mês seguinte ao
# último, ou o trimestre seguinte nas páginas de TRIMESTRAIS — sai vazado: é a
# `retomada` de cada página, lida de uma vez. Ele diz "é o próximo", nunca
# "está atrasado": cada distribuidora tem atraso próprio (a Claro chega meses
# depois), e isso o log não sabe.
#
# O desenho mora em assets/theme.css (.nn-cobertura); aqui só a marcação.

def _sr(texto: str) -> str:
    """Texto só para leitor de tela — a barra e as marcas são desenho."""
    return f'<span class="nn-sr">{html.escape(texto)}</span>'


def _celulas(pagina: str, meses: list[str], cobertos: set[str], quando: dict, trimestral: bool) -> str:
    primeiro, ultimo = min(cobertos), max(cobertos)
    proximo = mes_seguinte(ultimo)
    # Numa página trimestral o último processado sempre fecha um trimestre
    # (_grade expande cada mês gravado para o trimestre dele), então isto é o
    # trimestre seguinte inteiro.
    proximos = [m for m in _trimestre(proximo) if m >= proximo] if trimestral else [proximo]
    proximos_na_janela = [m for m in proximos if m in meses]
    rotulo = _rotulo_trimestre if trimestral else _rotulo_mes
    celulas = []
    for i, m in enumerate(meses):
        classes = ["m"]
        if i and m[:4] != meses[i - 1][:4]:
            classes.append("virada")
        titulo = conteudo = estilo = ""
        if m in cobertos:
            # A barra só arredonda onde a sequência começa ou termina de
            # verdade — se o mês vizinho (mesmo fora da janela) também foi
            # processado, ela segue reta até a borda.
            classes.append("feito")
            if mes_anterior(m) not in cobertos:
                classes.append("ini")
            if mes_seguinte(m) not in cobertos:
                classes.append("fim")
            titulo = f"{rotulo(m)}: processado em {_data_fmt(quando[(pagina, m)])}"
            conteudo = _sr("processado")
        elif primeiro < m < ultimo:
            classes.append("buraco")
            titulo = f"{rotulo(m)}: pulado, há processamento antes e depois"
            # Trimestre pulado é uma falta só: um ▲, no mês do meio.
            if not trimestral or int(m[4:6]) % 3 == 2:
                conteudo = '<span class="nn-marca nn-marca--buraco" aria-hidden="true">▲</span>'
            conteudo += _sr("pulado")
        elif m in proximos and trimestral:
            titulo = f"{rotulo(m)}: próximo a processar"
            conteudo = _sr("próximo")
            # A barra vazada é uma peça só: desenhada na primeira célula do
            # trimestre e esticada sobre as seguintes (--meses). Em três
            # pedaços, as pontas arredondadas saíam suavizadas e o mês do meio
            # nítido, e o fio fazia degrau na emenda.
            if m == proximos_na_janela[0]:
                classes.append("previsto")
                if m == proximos[0]:
                    classes.append("ini")
                if proximos_na_janela[-1] == proximos[-1]:
                    classes.append("fim")
                estilo = f' style="--meses: {len(proximos_na_janela)}"'
        elif m in proximos:
            titulo = f"{rotulo(m)}: próximo a processar"
            conteudo = '<span class="nn-marca nn-marca--proximo" aria-hidden="true"></span>' + _sr("próximo")
        atributo_titulo = f' title="{html.escape(titulo)}"' if titulo else ""
        celulas.append(f'<td class="{" ".join(classes)}"{atributo_titulo}{estilo}>{conteudo}</td>')
    return "".join(celulas)


def _lista_por_extenso(nomes: list[str]) -> str:
    return nomes[0] if len(nomes) == 1 else f"{', '.join(nomes[:-1])} e {nomes[-1]}"


def _grade(execucoes: list[execution_log.Execucao]) -> None:
    meses = _janela_meses(datetime.now(), MESES_NA_GRADE)

    # (página, mês) -> quando rodou por último para aquele mês. ISO ordena como
    # texto, então max() basta — e não depende da ordem de gravação, que a
    # importação de histórico embaralha.
    # Página trimestral: o mês gravado vale o trimestre todo.
    quando: dict[tuple[str, str], str] = {}
    for ex in execucoes:
        for mes in execution_log.meses_do_periodo(ex.periodo):
            for m in _trimestre(mes) if ex.pagina in TRIMESTRAIS else [mes]:
                quando[(ex.pagina, m)] = max(quando.get((ex.pagina, m), ""), ex.quando)

    cobertos: dict[str, set[str]] = {}
    for p, m in quando:
        cobertos.setdefault(p, set()).add(m)

    # Linhas: as esperadas, na ordem de ROTULOS, mais qualquer página que
    # apareça no log com um mês reconhecível e não esteja registrada aqui.
    # As que nunca gravaram um mês viram uma frase embaixo da grade — uma linha
    # inteira vazia não diz nada que o nome sozinho não diga.
    paginas = [p for p in NA_GRADE if p in cobertos] + sorted(set(cobertos) - set(ROTULOS))
    sem_periodo = [_rotulo(p) for p in NA_GRADE if p not in cobertos]

    notas = []
    if paginas:
        anos = [(ano, len(list(ms))) for ano, ms in groupby(meses, key=lambda m: m[:4])]
        linha_anos = '<th rowspan="2" class="rotulo" scope="col">Página</th>' + "".join(
            f'<th colspan="{n}" class="ano{" virada" if i else ""}" scope="colgroup">{ano}</th>'
            for i, (ano, n) in enumerate(anos)
        )
        linha_meses = "".join(
            f'<th class="m{" virada" if i and m[:4] != meses[i - 1][:4] else ""}" scope="col">'
            f"{MESES_PT[int(m[4:6]) - 1]}</th>"
            for i, m in enumerate(meses)
        )

        linhas, grupo_atual = [], None
        for p in paginas:
            grupo, nome = _grupo_e_nome(_rotulo(p))
            if grupo and grupo != grupo_atual:
                linhas.append(
                    f'<tr class="grupo"><th colspan="{len(meses) + 1}" scope="rowgroup">'
                    f"{html.escape(grupo)}</th></tr>"
                )
            grupo_atual = grupo
            classe_rotulo = "rotulo item" if grupo else "rotulo"
            linhas.append(
                f'<tr><th class="{classe_rotulo}" scope="row">{html.escape(nome)}</th>'
                f"{_celulas(p, meses, cobertos[p], quando, p in TRIMESTRAIS)}</tr>"
            )

        st.markdown(
            '<div class="nn-tabela nn-cobertura"><table>'
            f"<thead><tr>{linha_anos}</tr><tr>{linha_meses}</tr></thead>"
            f"<tbody>{''.join(linhas)}</tbody></table></div>",
            unsafe_allow_html=True,
        )
        legenda = [
            '<span class="nn-marca nn-marca--feito"></span>processado',
            '<span class="nn-marca nn-marca--buraco">▲</span>mês pulado entre dois processados',
            '<span class="nn-marca nn-marca--proximo"></span>próximo mês a processar',
        ]
        if any(p in TRIMESTRAIS for p in paginas):
            legenda.append('<span class="nn-marca nn-marca--previsto"></span>próximo trimestre a processar')
        notas.append("".join(f'<span class="nn-legenda">{item}</span>' for item in legenda))
        notas.append(
            "O mês é o do período do relatório, não o dia em que rodou. Passe o "
            "mouse sobre a barra para ver quando rodou."
        )

    if sem_periodo:
        notas.append(f"Sem período registrado ainda: {html.escape(_lista_por_extenso(sem_periodo))}.")

    st.markdown(
        "".join(f'<p class="nn-cobertura-nota">{n}</p>' for n in notas),
        unsafe_allow_html=True,
    )


# ---------------------------------------------------------------------------
# Lista cronológica
# ---------------------------------------------------------------------------

def _total(resumo: dict) -> float | None:
    for k in CHAVES_TOTAL:
        if k in resumo:
            try:
                return float(resumo[k])
            except (TypeError, ValueError):
                return None
    return None


def _moeda(ex: execution_log.Execucao) -> str:
    if ex.resumo.get("moeda"):
        return str(ex.resumo["moeda"])
    for prefixo, moeda in MOEDA_POR_PAGINA.items():
        if ex.pagina.startswith(prefixo):
            return moeda
    return MOEDA_PADRAO


def _dinheiro(valor: float | None, moeda: str) -> str:
    if valor is None:
        return ""
    return f"{moeda} " + f"{valor:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def _arquivo(resumo: dict) -> str:
    """Cada página grava o(s) arquivo(s) de um jeito: um nome em "arquivo", ou
    em "arquivos" uma lista de nomes ou só a contagem."""
    if isinstance(resumo.get("arquivo"), str):
        return resumo["arquivo"]
    arquivos = resumo.get("arquivos")
    if isinstance(arquivos, list) and arquivos:
        return arquivos[0] if len(arquivos) == 1 else f"{arquivos[0]} e mais {len(arquivos) - 1}"
    if isinstance(arquivos, int) and arquivos:
        return f"{arquivos} arquivos" if arquivos > 1 else "1 arquivo"
    return ""


def _origem(resumo: dict) -> str:
    # scripts/importar_log_processamentos.py grava "importado do arquivo (Z:)…";
    # as páginas não gravam "origem". Só vai para o CSV: na tela, a única
    # diferença visível era a hora (importado não tem), e a hora saiu.
    return "Importado" if str(resumo.get("origem", "")).startswith("importado") else "Rodado no Lyra"


def _periodo_ordenavel(periodo: str) -> str:
    """Chave de ordenação pro período: o mês mais recente que ele cobre
    (AAAAMM). Período sem mês reconhecível (nome de planilha, na
    Reconciliação) vai pro fim — string vazia ordena antes de qualquer AAAAMM."""
    meses = execution_log.meses_do_periodo(periodo)
    return max(meses) if meses else ""


def _lista(execucoes: list[execution_log.Execucao]) -> None:
    rotulos_presentes = sorted({_rotulo(ex.pagina) for ex in execucoes})
    filtro = st.selectbox("Página", ["Todas"] + rotulos_presentes, key="log_filtro")

    # Dois níveis, ambos do mais recente pro mais antigo: quando a execução
    # rodou primeiro (é o que se vê de cara); entre execuções do mesmo
    # instante (típico de importação em lote — mesmo segundo pra várias),
    # o período desempata.
    ordenadas = sorted(
        execucoes,
        key=lambda ex: (ex.quando, _periodo_ordenavel(ex.periodo)),
        reverse=True,
    )

    # Duas versões das mesmas linhas: a da tela (legível, total com moeda) e a
    # do CSV (valores crus, origem e o resumo inteiro, para quem for conferir
    # no Excel).
    tela, csv = [], []
    for ex in ordenadas:
        if filtro != "Todas" and _rotulo(ex.pagina) != filtro:
            continue
        total = _total(ex.resumo)
        moeda = _moeda(ex) if total is not None else ""
        comum = {
            "Página": _rotulo(ex.pagina),
            "Período": execution_log.periodo_codigo(ex.periodo),
        }
        tela.append({
            "Data": _data(ex.quando),
            **comum,
            "Total": _dinheiro(total, moeda),
            "Arquivo": _arquivo(ex.resumo),
        })
        csv.append({
            "Quando": ex.quando,
            **comum,
            "Total": total,
            "Moeda": moeda,
            "Origem": _origem(ex.resumo),
            "Arquivo": _arquivo(ex.resumo),
            "Resumo": json.dumps(ex.resumo, ensure_ascii=False),
        })

    df = pd.DataFrame(tela)
    df["Data"] = pd.to_datetime(df["Data"], errors="coerce")

    st.dataframe(
        df,
        hide_index=True,
        width="stretch",
        column_config={
            "Data": st.column_config.DateColumn(format="DD/MM/YYYY"),
            "Total": st.column_config.TextColumn(
                help="Na moeda do relatório — dólar e real não se comparam. É o total "
                "que cada página grava: líquido no Orchard e no Backoffice, FinalValue "
                "na iMusica e na Claro, Partner Revenue no YouTube."
            ),
        },
    )

    st.download_button(
        "Baixar log em CSV",
        data=pd.DataFrame(csv).to_csv(index=False).encode("utf-8-sig"),
        file_name="log_execucoes.csv",
        mime="text/csv",
        icon=":material/download:",
    )


# ---------------------------------------------------------------------------

execucoes = execution_log.todas()

if not execucoes:
    estado_vazio(
        "Nenhuma execução registrada ainda.",
        "Cada página grava aqui quando processa um relatório. A grade e a lista "
        "aparecem depois da primeira.",
    )
    st.stop()

st.subheader("Por mês")
_grade(execucoes)

st.divider()

st.subheader("Todas as execuções")
_lista(execucoes)
