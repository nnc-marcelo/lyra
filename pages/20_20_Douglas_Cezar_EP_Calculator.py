import streamlit as st
import pandas as pd
import os
from io import BytesIO

st.set_page_config(page_title="Douglas Cezar EP Calculator", layout="wide")

# =============================================================================
# Configurações pré-determinadas
# =============================================================================
AUTOR = "Douglas Cezar"
EDITORA = "DC Editora"
OBRAS_PATH = os.path.join("data", "catalogs", "douglas-cezar", "obras-cadastradas-DOUGLAS-CEZAR.xlsx")

# Shares do deal (writer e publisher)
WRITER_SHARE = 0.5          # Douglas (writer)
NNC_WRITER_SHARE = 0.5      # Nas Nuvens aquisição (writer)
PUBLISHER_TOTAL_SHARE = 0.5
NNC_PUBLISHER_SHARE = 0.5   # Nas Nuvens aquisição (publisher)
PUBLISHER_ADMIN_SHARE = 0.4 # DC Editora (admin)
NNC_ADMIN_SHARE = 0.6       # Nas Nuvens fee (admin)


def get_regras(periodo):
    """Nomes de income e contratos (Money In/Out) por tipo de share."""
    return {
        ("DOUGLAS CEZAR", "Writer Share"): [
            {"Contract - Money In": "ABRAMUS"},
            {"nome_income1": periodo + " EXECUCAO PUBLICA - DOUGLAS CEZAR - NN AQUISICAO (50%)"},
            {"nome_income2": periodo + " EXECUCAO PUBLICA - DOUGLAS CEZAR - RECUPERAVEL (50%)"},
            {"Contract - Money Out": "NAS NUVENS (WS) - DOUGLAS CEZAR (37,5%)"},
            {"SPLIT AMOUNT | Organization (%)": 0},
            {"SPLIT AMOUNT | Rights-Holder (%)": 50},
            {"Contract - Money Out": "DOUGLAS CEZAR AQUISIÇÃO (37,5%)"},
            {"SPLIT AMOUNT | Organization (%)": 0},
            {"SPLIT AMOUNT | Rights-Holder (%)": 50},
        ],
        ("DOUGLAS CEZAR", "Publisher Share"): [
            {"Contract - Money In": "ABRAMUS"},
            {"nome_income1": periodo + " EXECUCAO PUBLICA - DOUGLAS CEZAR / DC EDICOES - NN AQUISICAO (50%)"},
            {"nome_income2": periodo + " EXECUCAO PUBLICA - DOUGLAS CEZAR / DC EDICOES - NN RECUPERAVEL (50%)"},
            {"Contract - Money Out": "NAS NUVENS (PS) - DOUGLAS CEZAR - DC PRODUÇÕES (12,5%)"},
            {"SPLIT AMOUNT | Organization (%)": 0},
            {"SPLIT AMOUNT | Rights-Holder (%)": 50},
            {"Contract - Money Out": "DC PRODUÇÕES (DOUGLAS CEZAR) (PS) (12,5%)"},
            {"SPLIT AMOUNT | Organization (%)": 30},
            {"SPLIT AMOUNT | Rights-Holder (%)": 20},
        ],
    }


def format_currency(value):
    """Formata número no padrão pt-BR."""
    try:
        if isinstance(value, str):
            value = float(value.replace('R$', '').replace('.', '').replace(',', '.').strip())
        return f"{value:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    except Exception:
        return value


class ProcessadorRoyalties:
    """Lê os relatórios por obra (nacional/internacional), cruza com as obras
    cadastradas e devolve o total por obra com o flag AQUIRED."""

    def __init__(self, obras_cadastradas):
        self.obras_cadastradas = obras_cadastradas

    def obras_com_total(self, relatorio):
        tem_nacional = 'CÓD. OBRA' in relatorio.columns and 'RATEIO' in relatorio.columns
        tem_internacional = 'ISRC/ISWC' in relatorio.columns and 'Rendimento' in relatorio.columns
        dfs = []

        if tem_nacional:
            dfn = relatorio[relatorio['CÓD. OBRA'].notna()].copy()
            if not dfn.empty:
                dfn = dfn.groupby(['CÓD. OBRA', 'TÍTULO DA MUSICA']).agg({'RATEIO': 'sum'}).reset_index()
                dfn = dfn.rename(columns={'RATEIO': 'TOTAL'})
                dfn = dfn.merge(self.obras_cadastradas[['CÓD. OBRA', 'AQUIRED', 'CONTROLLED']],
                                on='CÓD. OBRA', how='inner')
                if not dfn.empty:
                    dfs.append(dfn)

        if tem_internacional:
            dfi = relatorio[relatorio['ISRC/ISWC'].notna()].copy()
            if not dfi.empty:
                col_tit = 'Título' if 'Título' in dfi.columns else 'TITULOTITULO'
                dfi = dfi.groupby(['ISRC/ISWC', col_tit]).agg({'Rendimento': 'sum'}).reset_index()
                dfi = dfi.rename(columns={'Rendimento': 'TOTAL'})
                dfi = dfi.merge(self.obras_cadastradas[['ISWC', 'AQUIRED', 'CONTROLLED']],
                                left_on='ISRC/ISWC', right_on='ISWC', how='inner')
                dfi = dfi.rename(columns={'ISRC/ISWC': 'CÓD. OBRA', col_tit: 'TÍTULO DA MUSICA'})
                if not dfi.empty:
                    dfs.append(dfi)

        if not dfs:
            return pd.DataFrame(columns=['CÓD. OBRA', 'TÍTULO DA MUSICA', 'TOTAL', 'AQUIRED', 'CONTROLLED'])

        df = pd.concat(dfs, ignore_index=True)
        df = df.groupby(['CÓD. OBRA', 'TÍTULO DA MUSICA']).agg(
            {'TOTAL': 'sum', 'AQUIRED': 'first', 'CONTROLLED': 'first'}).reset_index()
        return df


def gerar_incomes_por_obra(df_obras, tipo, periodo):
    """Gera as 2 linhas de income (NN AQUISICAO + RECUPERAVEL) calculando por obra.

    Adquirida (AQUIRED=Y) -> split do deal; Não-adquirida (N) -> 100% recuperável/admin.
    Por isso o split NÃO é fixo 50/50: depende do mix de obras do pagamento.
    """
    regras = get_regras(periodo)
    chave = ("DOUGLAS CEZAR", "Writer Share") if tipo == "Writer" else ("DOUGLAS CEZAR", "Publisher Share")
    r = regras[chave]
    money_in = r[0]["Contract - Money In"]

    if df_obras is None or df_obras.empty:
        return pd.DataFrame()

    acq = df_obras.loc[df_obras['AQUIRED'] == 'Y', 'TOTAL'].sum()
    nao = df_obras.loc[df_obras['AQUIRED'] == 'N', 'TOTAL'].sum()
    gross = round(acq + nao, 2)

    # Linha 1 (NN AQUISICAO) = Nas Nuvens fica com 50% só das obras ADQUIRIDAS
    net1 = round(acq * NNC_WRITER_SHARE, 2)  # 0.5 (writer e publisher usam 0.5 p/ NN aquisição)
    # Linha 2 (RECUPERAVEL) = todo o resto (50% das adquiridas + 100% das não-adquiridas)
    net2 = round(gross - net1, 2)

    if tipo == "Writer":
        org1, rights1 = 0.0, net1
        org2, rights2 = 0.0, net2
        notes1 = "Org: 0% | Rights: 50%"
        notes2 = "Org: 0% | Rights: 50%"
    else:  # Publisher: a recuperável tem fee (NN Fee=org) + DC Editora (rights)
        org1, rights1 = 0.0, net1
        # NN Fee (org): 30% das adquiridas + 60% das não-adquiridas
        org2 = round(acq * PUBLISHER_TOTAL_SHARE * NNC_ADMIN_SHARE + nao * NNC_ADMIN_SHARE, 2)
        rights2 = round(net2 - org2, 2)  # DC Editora absorve o resto (e o ajuste de centavos)
        notes1 = "Org: 0% | Rights: 50%"
        notes2 = f"Org (NN Fee): {org2:.2f} | Rights (DC Editora): {rights2:.2f}"

    linhas = [
        (r[1]["nome_income1"], net1, org1, rights1, r[3]["Contract - Money Out"], notes1),
        (r[2]["nome_income2"], net2, org2, rights2, r[6]["Contract - Money Out"], notes2),
    ]
    return pd.DataFrame([{
        "Name (*)": nome,
        "Contract - Money In (*)": money_in,
        "Sale Date (*)": "",
        "Payment Date (*)": "",
        "Net Amount (*)": net,
        "Gross Amount": gross,
        "Foreign Currency": "",
        "Foreign Net Amount": "",
        "Foreign Gross Amount": "",
        "Contract - Money Out (*)": out,
        "SPLIT AMOUNT | Organization (*)": org,
        "SPLIT AMOUNT | Rights-Holder (*)": rights,
        "Notes": notes,
    } for (nome, net, org, rights, out, notes) in linhas])


def ler_nacional(arquivo):
    return pd.read_csv(arquivo, sep=';', encoding="ISO-8859-1", decimal=',', thousands='.', header=4)


def total_relatorio(df):
    t = 0.0
    if 'RATEIO' in df.columns:
        t += df['RATEIO'].fillna(0).sum()
    if 'Rendimento' in df.columns:
        t += df['Rendimento'].fillna(0).sum()
    return t


def processar_lado(relatorios, tipo, processador, periodo):
    """Processa um lado (Writer ou Publisher) e devolve um dict com tudo p/ exibir."""
    completo = pd.concat(relatorios, ignore_index=True)
    df_obras = processador.obras_com_total(completo)
    total_geral = total_relatorio(completo)
    total_proc = df_obras['TOTAL'].sum()
    df_incomes = gerar_incomes_por_obra(df_obras, tipo, periodo)
    return {
        'df_obras': df_obras,
        'total_geral': total_geral,
        'total_processado': total_proc,
        'total_nao_processado': total_geral - total_proc,
        'total_adquiridas': df_obras.loc[df_obras['AQUIRED'] == 'Y', 'TOTAL'].sum(),
        'total_nao_adquiridas': df_obras.loc[df_obras['AQUIRED'] == 'N', 'TOTAL'].sum(),
        'qtd_obras': len(df_obras),
        'df_incomes': df_incomes,
    }


def bloco_validacao(df_incomes, total_processado):
    gross = df_incomes['Gross Amount'].iloc[0] if len(df_incomes) else 0
    check1 = abs(gross - round(total_processado, 2)) < 0.02
    soma_net = df_incomes['Net Amount (*)'].sum()
    check2 = abs(soma_net - gross) < 0.02
    checks3 = [abs(r['SPLIT AMOUNT | Organization (*)'] + r['SPLIT AMOUNT | Rights-Holder (*)']
                   - r['Net Amount (*)']) < 0.02 for _, r in df_incomes.iterrows()]
    c1, c2, c3 = st.columns(3)
    c1.metric("Gross = Total processado", "✅" if check1 else "❌",
              f"{format_currency(gross)} = {format_currency(total_processado)}")
    c2.metric("Soma Net = Gross", "✅" if check2 else "❌", format_currency(soma_net))
    c3.metric("Splits = Net", "✅" if all(checks3) else "❌", f"{sum(checks3)}/{len(checks3)} linhas")


def exibir_lado(titulo, d):
    st.header(titulo)
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Total geral", format_currency(d['total_geral']))
    c2.metric("Total processado", format_currency(d['total_processado']))
    c3.metric("Adquiridas", format_currency(d['total_adquiridas']))
    c4.metric("Não adquiridas", format_currency(d['total_nao_adquiridas']), delta_color="inverse")
    if d['total_nao_processado'] > 0.01:
        st.warning(f"⚠️ {format_currency(d['total_nao_processado'])} em obras NÃO cadastradas "
                   f"(não processadas). Verifique a lista de obras.")
    st.subheader("Linhas de Income")
    st.dataframe(d['df_incomes'], hide_index=True, use_container_width=True)
    st.caption("🔍 Validação")
    bloco_validacao(d['df_incomes'], d['total_processado'])
    with st.expander(f"Detalhamento de obras ({d['qtd_obras']})"):
        st.dataframe(d['df_obras'].sort_values('TOTAL', ascending=False)
                     .style.format({'TOTAL': format_currency}),
                     hide_index=True, use_container_width=True)


# =============================================================================
# UI
# =============================================================================
st.title("Douglas Cezar EP Calculator")
st.caption(f"Autor: {AUTOR} | Editora: {EDITORA} — calcula as Direct Incomes **por obra** e gera as "
           "linhas no layout de import do Reprtoir.")

with st.expander("ℹ️ O que é esta página e como usar", expanded=False):
    st.markdown(
"""
**Para que serve**

Calcula as *Direct Incomes* do **Douglas Cezar** (Writer) e da **DC Editora** (Publisher) a partir dos
relatórios da ABRAMUS e devolve as linhas prontas para importar no Reprtoir.

**Por que é diferente dos outros catálogos**

Aqui o split **não é fixo** — depende de cada **obra** ter sido ou não adquirida pela Nas Nuvens:
- **Obra adquirida** → dividida conforme o contrato (parte de aquisição da Nas Nuvens + parte recuperável).
- **Obra não adquirida** → vai **100% para recuperável/administração** (a Nas Nuvens apenas administra, não adquiriu).

Como cada mês tem um mix diferente de obras, a divisão do total varia (não é um 50/50 cego). Por isso o
Douglas é calculado aqui e **fica de fora** do processamento geral de Direct Incomes.

**Lista de obras**

Usa `data/catalogs/douglas-cezar/obras-cadastradas-DOUGLAS-CEZAR.xlsx`, onde cada obra é marcada como
adquirida (`Y`) ou não (`N`). ⚠️ **Obra que não estiver nessa lista é ignorada** (aparece como
"não processado") — mantenha a lista atualizada a cada obra nova ou mudança de status.

**Como usar**

1. Informe o **período** (vira o prefixo dos nomes das receitas, ex.: `2026M04`).
2. Suba os relatórios da ABRAMUS — **Nacional (CSV)** e/ou **Internacional (Excel)** — separados em
   *Douglas Cezar (Writer)* e *DC Editora (Publisher)*.
3. Clique em **Processar**.
4. Confira a **validação** (Gross = total, Σ Net = Gross, splits = net) e baixe o **CSV consolidado**
   para importar no Reprtoir.
"""
    )

periodo = st.text_input("Período (prefixo dos nomes de income)", "2026M04")

try:
    obras_cadastradas = pd.read_excel(OBRAS_PATH)
    st.success(f"Obras cadastradas: {len(obras_cadastradas)} "
               f"({(obras_cadastradas['AQUIRED'] == 'Y').sum()} adquiridas / "
               f"{(obras_cadastradas['AQUIRED'] == 'N').sum()} não-adquiridas)")
except Exception as e:
    st.error(f"Erro ao carregar a lista de obras ({OBRAS_PATH}): {e}")
    st.stop()

st.subheader("Upload dos relatórios ABRAMUS")
col1, col2 = st.columns(2)
with col1:
    st.markdown("**Douglas Cezar (Writer)**")
    up_w_nac = st.file_uploader("Nacional (CSV)", type=['csv'], key="w_nac")
    up_w_int = st.file_uploader("Internacional (Excel)", type=['xlsx', 'xls'], key="w_int")
with col2:
    st.markdown("**DC Editora (Publisher)**")
    up_p_nac = st.file_uploader("Nacional (CSV)", type=['csv'], key="p_nac")
    up_p_int = st.file_uploader("Internacional (Excel)", type=['xlsx', 'xls'], key="p_int")

if st.button("Processar", type="primary"):
    processador = ProcessadorRoyalties(obras_cadastradas)
    dados = {}

    rel_w = []
    if up_w_nac:
        rel_w.append(ler_nacional(up_w_nac))
    if up_w_int:
        rel_w.append(pd.read_excel(up_w_int))
    if rel_w:
        dados['writer'] = processar_lado(rel_w, "Writer", processador, periodo)

    rel_p = []
    if up_p_nac:
        rel_p.append(ler_nacional(up_p_nac))
    if up_p_int:
        rel_p.append(pd.read_excel(up_p_int))
    if rel_p:
        dados['publisher'] = processar_lado(rel_p, "Publisher", processador, periodo)

    if not dados:
        st.warning("Nenhum relatório carregado.")
    else:
        st.session_state['douglas_dados'] = dados

if st.session_state.get('douglas_dados'):
    dados = st.session_state['douglas_dados']
    if 'writer' in dados:
        exibir_lado("Writer (Douglas Cezar)", dados['writer'])
        st.divider()
    if 'publisher' in dados:
        exibir_lado("Publisher (DC Editora)", dados['publisher'])
        st.divider()

    partes = [dados[k]['df_incomes'] for k in ('writer', 'publisher') if k in dados]
    if partes:
        df_final = pd.concat(partes, ignore_index=True)
        st.header("📥 Exportar incomes consolidadas")
        st.dataframe(df_final, hide_index=True, use_container_width=True)
        buf = BytesIO()
        df_final.to_csv(buf, index=False, encoding='utf-8-sig')
        st.download_button("📥 Download CSV", data=buf.getvalue(),
                           file_name=f"incomes_consolidadas_DouglasCezar_{periodo}.csv",
                           mime="text/csv")
