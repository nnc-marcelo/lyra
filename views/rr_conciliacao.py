"""
RR — Conciliação de recebimentos (ABRAMUS).

O trabalho que esta página substitui: o financeiro avisa que caiu um valor da
ABRAMUS no banco e alguém abre o recibo do mês para destrinchar quanto daquele
valor é de cada catálogo, linha por linha. O recibo é padronizado, então essa
quebra pode ser lida do próprio PDF.

O que o recibo entrega de graça e o que não entrega:

* **venda de catálogo** (`VENDA CATALOGO - CESSAO - <TITULAR>`) já vem quebrada
  por titular — falta só traduzir titular para catálogo, que é o de-para em
  `data/mapping/rr_titulares_abramus.json`;
* **repertório próprio** (linhas do código do demonstrativo da NNC) vem como um
  bolo só, por rubrica, e são dois rateios diferentes: a execução pública sai do
  analítico `_XLS.csv` — via o relatório agrupado que a página de **Cruzamento
  com catálogo** gera — e o direito autoral do exterior sai do `_INT.pdf`, que
  esta página cruza com a base de obras por ISWC. Daí os dois uploads opcionais.

O titular sai **exatamente como está no recibo**; o de-para guarda só o
catálogo.

A leitura do PDF mora em `utils/abramus_recibo.py` e a montagem das linhas em
`utils/rr_linhas.py`; aqui só tem tela. O app roda no Streamlit Cloud, que não
enxerga o `Z:`: por isso tudo é por upload, e o de-para é um arquivo versionado
no repositório — semeado do histórico por
`scripts/bootstrap_titulares_abramus.py`.
"""

import io
import json
import sys
from pathlib import Path

import pandas as pd
import streamlit as st

sys.path.insert(0, str(Path(__file__).parent.parent))
from utils.abramus_recibo import conferencia, ler_recibo, normalizar  # noqa: E402
from utils.page import setup_page  # noqa: E402
from utils.rr_linhas import (  # noqa: E402
    COLUNAS_SAIDA,
    FONTE_ABRAMUS,
    MAPEAMENTO_A_RATEAR,
    MAPEAMENTO_A_RATEAR_INT,
    MAPEAMENTO_PENDENTE,
    ORIGEM_VENDA,
    aplicar_mapeamentos,
    carregar_depara,
    gravar_depara,
    ler_agrupado,
    ler_debitos_editora,
    ler_internacional,
    linhas_do_recibo,
    novos_mapeamentos,
)

setup_page(__file__)

with st.expander("ℹ️ O que é esta página e como usar", expanded=False):
    st.markdown(
        """
**O que faz**

Lê o recibo da ABRAMUS (`..._REC.pdf`, o "Demonstrativo de Pagamento") e devolve **quanto daquele
crédito bancário é de cada catálogo**, pronto para lançar na RR.

**De onde sai cada número**

- **Venda de catálogo**: o recibo já detalha por titular (nome civil ou razão social). A página soma
  as seis categorias do mesmo titular (autor, editor, intérprete, músico, produtor fonográfico,
  versionista) — que é a granularidade de uma linha da RR — e traduz o titular para o catálogo.
- **Repertório próprio**: vem no recibo como um bolo só, por rubrica, sem catálogo — e são duas
  coisas distintas. A **execução pública no Brasil** se quebra com o **relatório agrupado** que a
  página *Cruzamento com catálogo* gera a partir do `..._XLS.csv`. O **direito autoral do exterior**
  (rubrica `DIR AUTORAL EXTERIOR`) não está nesse analítico: ele se quebra com o **`..._INT.pdf`**
  do mesmo mês, que esta página cruza com a base de obras da ABRAMUS por ISWC (e por título quando
  o ISWC não está na base). Sem os arquivos, cada bloco sai numa linha única marcada para ratear.
- **Débitos de editora (Warner/Universal)**: o recibo só entrega um total negativo por editora. O
  **`..._VCV.csv`** detalha obra a obra — o percentual do contrato (4/8/16% é Warner, 7/14% é
  Universal) diz a editora, e a base de obras dá o catálogo. Sem ele, sai numa linha só, sem catálogo.
- **Despesas bancárias**: saem em linha própria, com catálogo em branco. Assim a soma das linhas
  fecha com o que caiu no banco.
- **Titular**: sai exatamente como está no recibo (`ROBERTO MALTEZ GARRIDO FILHO`, e não
  `Beto Garrido`). O de-para guarda só o catálogo.

**Como usar**

1. Suba o `..._REC.pdf` (pode subir vários meses de uma vez).
2. Se tiver, suba o relatório agrupado do cruzamento, o `..._INT.pdf` e o `..._VCV.csv` do mesmo
   mês para quebrar repertório próprio e débitos de editora por catálogo.
3. Confira o painel de fechamento (soma × TOTAL do recibo).
4. Resolva os titulares pendentes na tabela — e grave no de-para para não perguntar de novo.
5. Baixe o xlsx/CSV.
"""
    )

if "rr_depara" not in st.session_state:
    st.session_state["rr_depara"] = carregar_depara()


def brl(valor: float) -> str:
    """Valor em reais para texto markdown. O cifrão vai escapado porque dois
    cifrões soltos na mesma string fazem o Streamlit ler o trecho do meio como
    LaTeX — "R$ 647,78. R$ 56,38" virava fórmula na tela."""
    return rf"R\$ {valor:,.2f}"


def para_xlsx(df: pd.DataFrame) -> bytes:
    buffer = io.BytesIO()
    with pd.ExcelWriter(buffer, engine="xlsxwriter") as writer:
        df.to_excel(writer, index=False, sheet_name="RR")
    return buffer.getvalue()


tab_conciliar, tab_depara = st.tabs(["🧾 Conciliar recibo", "🔗 De-para de titulares"])

# ---------------------------------------------------------------------------
# Conciliar
# ---------------------------------------------------------------------------
with tab_conciliar:
    pdfs = st.file_uploader(
        "Recibo da ABRAMUS (`..._REC.pdf`)", type=["pdf"], accept_multiple_files=True,
        help="É o Demonstrativo de Pagamento. Pode subir vários meses de uma vez.",
    )
    col_a, col_b, col_c = st.columns(3)
    with col_a:
        agrupado_arquivo = st.file_uploader(
            "Relatório agrupado do cruzamento (opcional)", type=["xlsx"],
            help="O xlsx com CATÁLOGO e RATEIO que a página de Cruzamento com catálogo gera a "
                 "partir do `..._XLS.csv` — quebra a execução pública por catálogo.",
        )
    with col_b:
        int_arquivo = st.file_uploader(
            "Demonstrativo internacional `..._INT.pdf` (opcional)", type=["pdf"],
            help="Do mesmo mês do recibo. Quebra o direito autoral do exterior por catálogo, "
                 "cruzando as obras com a base da ABRAMUS por ISWC.",
        )
    with col_c:
        vcv_arquivo = st.file_uploader(
            "Débito de editora `..._VCV.csv` (opcional)", type=["csv"],
            help="Do mesmo mês do recibo. Quebra o débito de Warner/Universal por catálogo — o "
                 "percentual do contrato de cessão diz a editora.",
        )

    agrupado = internacional = debitos_editora = None
    if agrupado_arquivo is not None:
        try:
            agrupado = ler_agrupado(agrupado_arquivo)
            st.caption(
                f"Relatório agrupado: {len(agrupado)} catálogos, {brl(agrupado['Valor'].sum())}."
            )
        except Exception as erro:  # noqa: BLE001 — arquivo do usuário
            st.error(f"Não consegui ler o relatório agrupado: {erro}")
    if int_arquivo is not None:
        try:
            internacional = ler_internacional(int_arquivo)
            por_titulo = float(internacional["Casado só por título"].sum())
            sem_catalogo = float(internacional.loc[internacional["Catálogo"] == "", "Valor"].sum())
            recado = (
                f"Internacional: {int(internacional['Obras'].sum())} obras, "
                f"{brl(internacional['Valor'].sum())}."
            )
            if sem_catalogo:
                recado += f" {brl(sem_catalogo)} sem catálogo na base de obras."
            if por_titulo:
                recado += (
                    f" {brl(por_titulo)} casado(s) só por título (o ISWC não está na base) — "
                    "confira, pode haver obra homônima de outro autor."
                )
            st.caption(recado)
        except Exception as erro:  # noqa: BLE001 — arquivo do usuário
            st.error(f"Não consegui ler o demonstrativo internacional: {erro}")
    if vcv_arquivo is not None:
        try:
            debitos_editora = ler_debitos_editora(vcv_arquivo)
            por_titulo = float(debitos_editora["Casado só por título"].sum())
            sem_catalogo = float(
                debitos_editora.loc[debitos_editora["Catálogo"] == "", "Valor"].sum()
            )
            por_editora = debitos_editora.groupby("Editora")["Valor"].sum()
            recado = "Débito de editora: " + ", ".join(
                f"{editora.title()} {brl(-valor)}" for editora, valor in por_editora.items()
            ) + "."
            if sem_catalogo:
                recado += f" {brl(-sem_catalogo)} sem catálogo na base de obras."
            if por_titulo:
                recado += (
                    f" {brl(-por_titulo)} casado(s) só por título (o ISWC não está na base) — "
                    "confira, pode haver obra homônima de outro autor."
                )
            st.caption(recado)
        except Exception as erro:  # noqa: BLE001 — arquivo do usuário
            st.error(f"Não consegui ler o _VCV.csv: {erro}")

    detalhes_de_um_mes = (agrupado, internacional, debitos_editora)
    if pdfs:
        if len(pdfs) > 1 and any(d is not None for d in detalhes_de_um_mes):
            st.warning(
                "Os arquivos de detalhe são de um mês só. Com vários recibos no upload eles são "
                "ignorados — suba um mês por vez para quebrar o repertório próprio e os débitos.",
                icon=":material/warning:",
            )
            agrupado = internacional = debitos_editora = None

        partes = []
        for arquivo in pdfs:
            recibo = ler_recibo(arquivo)
            conf = conferencia(recibo)

            with st.container(border=True):
                st.markdown(
                    f"**{arquivo.name}** — competência **{recibo.competencia or '?'}** · "
                    f"recibo {recibo.numero or '?'} · {recibo.titular or ''}"
                )
                m1, m2, m3, m4 = st.columns(4)
                m1.metric("Total do recibo", f"R$ {conf['total']:,.2f}",
                          help="É o valor que caiu no banco.")
                m2.metric("Venda de catálogo", f"R$ {recibo.valor_relacionamento:,.2f}")
                m3.metric("Repertório próprio", f"R$ {recibo.valor_proprio:,.2f}",
                          help=f"Execução pública {brl(recibo.valor_ecad)} (rateada pelo "
                               f"relatório agrupado) + exterior {brl(recibo.valor_exterior)} "
                               "(rateado pelo _INT.pdf).")
                m4.metric("Diferença", f"R$ {conf['diferenca']:,.2f}",
                          help="Soma do detalhe menos as deduções, contra o TOTAL declarado. O "
                               "resíduo são as frações abaixo de um centavo que o recibo soma no "
                               "resumo mas não exibe no detalhe.")
                for aviso in recibo.avisos:
                    st.warning(aviso, icon=":material/warning:")

            if not recibo.linhas.empty:
                partes.append(linhas_do_recibo(
                    recibo, st.session_state["rr_depara"], agrupado, internacional, debitos_editora
                ))

        if partes:
            st.session_state["rr_resultado"] = pd.concat(partes, ignore_index=True)

    df = st.session_state.get("rr_resultado")
    if df is not None and not df.empty:
        st.divider()
        c1, c2, c3 = st.columns(3)
        c1.metric("Linhas", len(df))
        c2.metric("Soma das linhas", f"R$ {df['Valor'].sum():,.2f}")
        c3.metric("Sem catálogo", int((df["Catálogo"] == "").sum()))

        # Só titular de venda de catálogo é "pendente" no sentido de faltar
        # de-para; o resíduo do repertório próprio também vem sem catálogo, mas
        # se resolve subindo o relatório agrupado, não editando a tabela.
        pendentes = df[
            (df["Mapeamento"] == MAPEAMENTO_PENDENTE) & (df["Origem"] == ORIGEM_VENDA)
        ]
        if not pendentes.empty:
            st.warning(
                f"{len(pendentes)} titular(es) sem catálogo no de-para "
                f"({brl(pendentes['Valor'].sum())}). Preencha a coluna **Catálogo** abaixo e "
                "grave no de-para para não precisar de novo no mês que vem.",
                icon=":material/help:",
            )
        for mapeamento, recado in (
            (MAPEAMENTO_A_RATEAR,
             "de execução pública numa linha só. Para quebrar por catálogo, suba o relatório "
             "agrupado que a página **Cruzamento com catálogo** gera a partir do `..._XLS.csv` "
             "do mesmo mês."),
            (MAPEAMENTO_A_RATEAR_INT,
             "de direito autoral do exterior numa linha só. Para quebrar por catálogo, suba o "
             "`..._INT.pdf` do mesmo mês."),
        ):
            bloco = df[df["Mapeamento"] == mapeamento]
            if not bloco.empty:
                st.info(f"{brl(bloco['Valor'].sum())} {recado}", icon=":material/info:")

        st.markdown("##### Linhas para a RR")
        st.caption(
            "Catálogo e Titular são editáveis. As três últimas colunas são contexto e **não** vão "
            "no arquivo baixado."
        )
        editado = st.data_editor(
            df,
            width="stretch",
            # Um recibo recente passa de 60 linhas; com a altura padrão (~10) a
            # conferência vira rolagem dentro de rolagem.
            height=560,
            hide_index=True,
            column_config={
                "Período": st.column_config.TextColumn(disabled=True, width="small"),
                "Catálogo": st.column_config.TextColumn(help="Como o catálogo é grafado na RR."),
                "Titular": st.column_config.TextColumn(),
                "Valor": st.column_config.NumberColumn(format="%.2f", disabled=True),
                "Origem": st.column_config.TextColumn(disabled=True),
                "Titular no recibo": st.column_config.TextColumn(disabled=True, width="medium"),
                "Mapeamento": st.column_config.TextColumn(disabled=True, width="small"),
            },
            key="rr_editor",
        )
        saida = editado[COLUNAS_SAIDA]
        periodo = str(editado["Período"].iloc[0] or "periodo")

        col_a, col_b, col_c = st.columns([1, 1, 2])
        with col_a:
            st.download_button(
                "⬇️ Baixar xlsx", data=para_xlsx(saida),
                file_name=f"rr_{FONTE_ABRAMUS.lower()}_{periodo}.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                width="stretch",
            )
        with col_b:
            st.download_button(
                "⬇️ Baixar CSV",
                data=saida.to_csv(index=False, sep=";", decimal=",").encode("utf-8-sig"),
                file_name=f"rr_{FONTE_ABRAMUS.lower()}_{periodo}.csv",
                mime="text/csv", width="stretch",
            )
        with col_c:
            novos = novos_mapeamentos(editado)
            if not novos.empty and st.button(
                f"💾 Gravar {len(novos)} titular(es) no de-para", width="stretch"
            ):
                mapa = aplicar_mapeamentos(st.session_state["rr_depara"], novos)
                st.session_state["rr_depara"] = mapa
                gravar_depara(mapa)
                st.success(
                    f"{len(novos)} titular(es) gravado(s). Baixe o JSON na aba **De-para de "
                    "titulares** e commite no repositório para não perder no próximo restart."
                )

# ---------------------------------------------------------------------------
# De-para
# ---------------------------------------------------------------------------
with tab_depara:
    mapa = st.session_state["rr_depara"]
    st.caption(
        f"{len(mapa)} titulares. O arquivo é `data/mapping/rr_titulares_abramus.json`, semeado do "
        "histórico por `scripts/bootstrap_titulares_abramus.py`. **No Streamlit Cloud o disco é "
        "efêmero**: o que for gravado aqui vale até o app reiniciar — baixe o JSON e commite no "
        "repositório para valer para sempre."
    )
    if not mapa:
        st.info("De-para vazio — rode `scripts/bootstrap_titulares_abramus.py` para semeá-lo.")
    else:
        tabela = pd.DataFrame(mapa.values())[
            ["titular_recibo", "catalogo", "origem", "ocorrencias"]
        ].rename(columns={
            "titular_recibo": "Titular no recibo",
            "catalogo": "Catálogo",
            "origem": "Origem",
            "ocorrencias": "Meses vistos",
        })
        busca = st.text_input("Filtrar", placeholder="titular ou catálogo")
        if busca:
            alvo = normalizar(busca)
            tabela = tabela[
                tabela["Titular no recibo"].map(lambda v: alvo in normalizar(v))
                | tabela["Catálogo"].map(lambda v: alvo in normalizar(v))
            ]
        st.dataframe(
            tabela.sort_values(["Catálogo", "Titular no recibo"]),
            hide_index=True, width="stretch", height=460,
            column_config={"Meses vistos": st.column_config.NumberColumn(
                format="%d", help="Em quantos meses do histórico este titular caiu neste catálogo."
            )},
        )
        st.download_button(
            "⬇️ Baixar de-para (JSON)",
            data=json.dumps(
                {"fonte": FONTE_ABRAMUS, "titulares": sorted(mapa.values(), key=lambda t: t["chave"])},
                ensure_ascii=False, indent=2,
            ).encode("utf-8"),
            file_name="rr_titulares_abramus.json", mime="application/json",
        )
