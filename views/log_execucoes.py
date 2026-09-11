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

import pandas as pd
import streamlit as st

from utils import execution_log
from utils.execution_log import MESES_PT
from utils.page import setup_page
from utils.ui_components import COR_ATIVO, COR_INATIVO, estado_vazio, render_html_table

setup_page(__file__)

# Rótulo por chave de `pagina` no log. A chave é o que cada página passa a
# execution_log.registrar; os templates de Processamento de relatórios usam
# "processamento_relatorios:<slug>" (e o The Orchard, um slug por catálogo).
# Ao criar um template novo lá, registre o rótulo aqui — sem isso ele ainda
# aparece nas duas tabelas, mas com a chave crua.
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

MESES_NA_GRADE = 12

# Chaves de `resumo` que servem de "total" na lista, em ordem de preferência —
# cada página grava o total com o nome que faz sentido para ela.
CHAVES_TOTAL = ("total_liquido", "final_value_total", "partner_revenue_total", "total_bruto")


def _rotulo(pagina: str) -> str:
    return ROTULOS.get(pagina, pagina)


def _janela_meses(n: int) -> list[str]:
    """Os últimos `n` meses (AAAAMM), terminando no mês atual, em ordem."""
    ano, mes = datetime.now().year, datetime.now().month
    meses = []
    for _ in range(n):
        meses.append(f"{ano}{mes:02d}")
        mes -= 1
        if mes == 0:
            mes, ano = 12, ano - 1
    return list(reversed(meses))


def _rotulo_mes(aaaamm: str) -> str:
    return f"{MESES_PT[int(aaaamm[4:6]) - 1]}/{aaaamm[2:4]}"


def _ponto(feito: bool) -> str:
    """Bolinha de status centrada na célula. `status_dot_html` traz margem à
    direita para sentar antes de um texto; numa célula só de bolinha, isso a
    tira do centro."""
    cor = COR_ATIVO if feito else COR_INATIVO
    return (
        f'<span style="display:inline-block;width:8px;height:8px;'
        f'border-radius:50%;background:{cor};"></span>'
    )


def _quando_fmt(iso: str, com_hora: bool = True) -> str:
    try:
        dt = datetime.fromisoformat(iso)
    except (TypeError, ValueError):
        return iso
    return dt.strftime("%d/%m/%Y %H:%M" if com_hora else "%d/%m/%Y")


# ---------------------------------------------------------------------------
# Grade mensal
# ---------------------------------------------------------------------------

def _grade(execucoes: list[execution_log.Execucao]) -> None:
    meses = _janela_meses(MESES_NA_GRADE)

    # (página, mês) -> quando foi a última execução daquele mês
    feito: dict[tuple[str, str], str] = {}
    for ex in execucoes:
        for m in execution_log.meses_do_periodo(ex.periodo):
            feito[(ex.pagina, m)] = ex.quando

    # Linhas: as esperadas, na ordem de ROTULOS, mais qualquer página que
    # apareça no log com um mês reconhecível e não esteja registrada aqui.
    extras = sorted({p for (p, _m) in feito} - set(ROTULOS))
    paginas = NA_GRADE + extras

    headers = ["Página"] + [_rotulo_mes(m) for m in meses]
    rows = []
    for p in paginas:
        celulas = [f"<td>{html.escape(_rotulo(p))}</td>"]
        for m in meses:
            quando = feito.get((p, m))
            titulo = f'title="Processado em {_quando_fmt(quando)}"' if quando else ""
            celulas.append(f'<td style="text-align:center" {titulo}>{_ponto(quando is not None)}</td>')
        rows.append("<tr>" + "".join(celulas) + "</tr>")

    render_html_table(headers, rows, max_height="520px", translucent=False)
    st.caption(
        "Mês = período do relatório, não a data em que você rodou. Verde: houve "
        "pelo menos uma execução daquele período — passe o mouse para ver quando."
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


def _lista(execucoes: list[execution_log.Execucao]) -> None:
    rotulos_presentes = sorted({_rotulo(ex.pagina) for ex in execucoes})
    filtro = st.selectbox("Página", ["Todas"] + rotulos_presentes, key="log_filtro")

    linhas = [
        {
            "Quando": datetime.fromisoformat(ex.quando),
            "Página": _rotulo(ex.pagina),
            "Período": execution_log.periodo_humano(ex.periodo),
            "Linhas": ex.resumo.get("linhas"),
            "Total": _total(ex.resumo),
            "Resumo": json.dumps(ex.resumo, ensure_ascii=False),
        }
        for ex in reversed(execucoes)          # mais recente primeiro
        if filtro == "Todas" or _rotulo(ex.pagina) == filtro
    ]
    df = pd.DataFrame(linhas)
    # Página que não grava a chave vem como None; sem isso o st.dataframe
    # imprime "None" em vez de deixar a célula vazia.
    for col in ("Linhas", "Total"):
        df[col] = pd.to_numeric(df[col], errors="coerce")

    st.dataframe(
        df,
        hide_index=True,
        width="stretch",
        column_config={
            "Quando": st.column_config.DatetimeColumn(format="DD/MM/YYYY HH:mm"),
            "Linhas": st.column_config.NumberColumn(format="%d"),
            "Total": st.column_config.NumberColumn(format="%.2f"),
            "Resumo": st.column_config.TextColumn(
                help="Tudo que a página gravou nessa execução. Clique duas vezes na célula para ver inteiro."
            ),
        },
    )

    st.download_button(
        "Baixar log em CSV",
        data=df.to_csv(index=False).encode("utf-8-sig"),
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
