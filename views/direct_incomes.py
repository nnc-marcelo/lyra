import streamlit as st
import pandas as pd
import json
from pathlib import Path
from datetime import datetime

from utils.bi_extract import normalize, coerce_money, read_bi_extract
from utils.page import setup_page

# ============================================================================
# Direct Incomes
# Distribui receitas diretas (extrato do BI -> Reprtoir) a partir de regras por
# (Catálogo, Fonte) com discriminação opcional por Titular e Origem/Detalhe.
# As regras ficam em data/direct_incomes/regras.json (persistidas em disco) e
# são editáveis pela própria página.
# ============================================================================

setup_page(
    __file__,
    descricao=(
        "Distribui receitas diretas por catálogo/fonte/titular e gera o arquivo pronto "
        "para o Reprtoir. As regras de cálculo são editáveis aqui mesmo, sem mexer no código."
    ),
)

with st.expander("ℹ️ O que é esta página e como usar", expanded=False):
    st.markdown(
"""
**O que faz**

Distribui as *Direct Incomes* (receitas diretas) a partir do extrato do BI e gera o CSV pronto para
importar no Reprtoir.

**Como filtra**

Usa apenas as linhas de **Direct Income** (coluna `Motivo Processamento`). Rodapés do BI (Total,
"Filtros aplicados") são descartados. Você pode subir o **histórico inteiro** do extrato (vários
meses de uma vez): a página lista os meses encontrados na coluna `Data` (data de recebimento) e você
escolhe qual processar. Também dá pra restringir a um ou alguns **catálogos** específicos.

**Como calcula (regras)**

Cada receita vem de uma regra por **Catálogo + Fonte**, com **Titular** e **Origem/Detalhe** opcionais.
A regra mais específica vence: se houver uma com o titular/origem da transação, ela é usada; senão cai
na regra geral de Catálogo+Fonte. O titular casa de forma tolerante (ignora acento/maiúsculas e aceita
abreviações como "Hele" → "Helena"). As regras ficam em `data/direct_incomes/regras.json` e são
editáveis nas abas **Lista de regras** e **Editar regras**.

**Douglas Cezar** é calculado à parte (por obra) na página **Douglas Cezar EP Calculator**, porque o
split dele depende de cada obra ser adquirida ou não. Aqui ele é ignorado de propósito.

**Como usar**

1. Na aba **Calcular**, faça o upload do extrato (xlsx/csv) — pode ser o histórico inteiro.
2. Escolha o **mês a processar** (detectado a partir da coluna `Data`) e, se quiser, um ou mais
   **catálogos** para restringir.
3. Defina o **período** (prefixo dos nomes das receitas, ex.: `2026M04`) e clique em **Processar receitas**.
4. Confira a validação de totais e baixe o **CSV (Reprtoir)**.
5. Gere o Douglas pela página dele e junte ao import final.
"""
    )

RULES_PATH = Path(__file__).resolve().parent.parent / "data" / "direct_incomes" / "regras.json"

INCOME_COLS = ["descricao", "money_out", "org_pct", "rights_pct"]

# ---------------------------------------------------------------------------
# Conhecimento de casos especiais (portado do projeto "Direct Incomes App",
# fonte da verdade operacional — ver data/direct_incomes/regras.json e
# docs/CASOS-ESPECIAIS.md do projeto original). Catálogos aqui NUNCA entram
# no lote geral, mesmo que exista regra casando — são gerados à parte.
# ---------------------------------------------------------------------------
NEUTRALIZADOS = {"DOUGLAS CEZAR", "ROSENBLIT"}

# Ignorados que sabemos que não devem gerar receita aqui (chave = catálogo
# normalizado + fonte normalizada, ou "*" para qualquer fonte do catálogo).
EXCLUSOES_ESPERADAS = {
    ("DOUGLAS CEZAR", "*"): (
        "Processado À PARTE por obra (página Douglas Cezar EP Calculator). "
        "Neutralizado de propósito; mesclar a saída ao import final."
    ),
    ("ROSENBLIT", "*"): (
        "Defasagem de 1 mês: extrato do Rosenblit é sempre do mês seguinte ao lote. "
        "Lançar À PARTE e conferir Gross+Data contra o mês anterior antes de importar "
        "(risco de duplicidade já ocorrido)."
    ),
    ("CELSO FONSECA", "NIKITA MUSIC DIGITAL"): "Não é Direct Income (confirmado jun/2026).",
    ("DOUGLAS CEZAR", "R3 PRODUCOES"): "Não é Direct Income (confirmado jun/2026).",
    ("MATSUMOTO", "UBC"): "Não tem Direct Income; Motivo mal rotulado na origem. Ignorar/corrigir no BI.",
}

# Gaps conhecidos: sem regra cadastrada, mas deveriam ter — exigem ação.
GAPS_CONHECIDOS = {
    ("ZEIDER", "CASA 1 PRODUTORA"): "GAP conhecido: sem regra cadastrada. Definir split e cadastrar.",
}


# ---------------------------------------------------------------------------
# Utilidades
# ---------------------------------------------------------------------------
def norm_date(value):
    if isinstance(value, pd.Timestamp):
        return value.strftime("%Y-%m-%d")
    try:
        return pd.to_datetime(value).strftime("%Y-%m-%d")
    except Exception:
        return datetime.now().strftime("%Y-%m-%d")


# ---------------------------------------------------------------------------
# Persistência das regras
# ---------------------------------------------------------------------------
def load_rules():
    if RULES_PATH.exists():
        with open(RULES_PATH, encoding="utf-8") as f:
            return json.load(f)
    return {"periodo": "", "regras": []}


def save_rules(data):
    RULES_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(RULES_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def rule_label(r):
    partes = [r.get("catalogo", ""), r.get("fonte", "")]
    if r.get("titular"):
        partes.append(f"👤 {r['titular']}")
    if r.get("origem"):
        partes.append(f"🔖 {r['origem']}")
    return "  |  ".join(p for p in partes if p)


def rules_to_dataframe(regras):
    """Achata as regras em uma linha por receita, para a visão de lista."""
    rows = []
    for r in regras:
        for inc in r.get("incomes", []):
            org = float(inc.get("org_pct") or 0)
            rights = float(inc.get("rights_pct") or 0)
            rows.append({
                "Fonte": r.get("fonte", ""),
                "Catálogo": r.get("catalogo", ""),
                "Titular": r.get("titular") or "",
                "Origem": r.get("origem") or "",
                "Money In": r.get("money_in") or "",
                "Receita": inc.get("descricao", ""),
                "Money Out": inc.get("money_out", ""),
                "Org %": org,
                "Rights %": rights,
                "Total %": round(org + rights, 2),
            })
    df = pd.DataFrame(rows)
    if not df.empty:
        df = df.sort_values(["Fonte", "Catálogo", "Titular", "Origem"], kind="stable").reset_index(drop=True)
    return df


# ---------------------------------------------------------------------------
# Casamento de regras
# ---------------------------------------------------------------------------
def titular_match(rule_tit, row_tit):
    """Match tolerante de titular (resolve 'Hele'/'Helena', etc.). A tolerância por
    abreviação exige pelo menos 2 letras nas duas pontas — senão um nome de 1 letra
    (ex.: o artista "Z") vira prefixo de qualquer titular que comece com essa letra
    (ex.: "ZEIDER" casaria com a regra de "Z PRODUCOES")."""
    a, b = normalize(rule_tit), normalize(row_tit)
    if not a:
        return True  # regra sem titular = curinga
    if a == b or b.startswith(a) or a.startswith(b):
        return True
    at = a.split()[0] if a else ""
    bt = b.split()[0] if b else ""
    if len(at) < 2 or len(bt) < 2:
        return False
    return at.startswith(bt) or bt.startswith(at)


def origem_match(rule_org, row_org):
    if not rule_org:
        return True  # regra sem origem = curinga
    return normalize(rule_org) == normalize(row_org)


def find_rule(regras, cat, fonte, titular, origem):
    """Acha a regra mais específica que casa com (cat, fonte, titular, origem)."""
    ncat, nfonte = normalize(cat), normalize(fonte)
    best, best_score = None, -1
    for r in regras:
        if normalize(r.get("catalogo")) != ncat or normalize(r.get("fonte")) != nfonte:
            continue
        rt, ro = r.get("titular"), r.get("origem")
        if not titular_match(rt, titular):
            continue
        if not origem_match(ro, origem):
            continue
        score = (1 if rt else 0) + (1 if ro else 0)
        if score > best_score:
            best, best_score = r, score
    return best


# ---------------------------------------------------------------------------
# Cálculo
# ---------------------------------------------------------------------------
def classificar_ignorado(cat, fonte):
    """Classifica um grupo ignorado como ESPERADA (ok ignorar) / GAP (falta
    cadastrar) / INVESTIGAR (possível regra nova), com o motivo conhecido."""
    cu, fu = normalize(cat), normalize(fonte)
    for (a, b), motivo in EXCLUSOES_ESPERADAS.items():
        if normalize(a) == cu and (b == "*" or normalize(b) == fu):
            return "ESPERADA", motivo
    for (a, b), motivo in GAPS_CONHECIDOS.items():
        if normalize(a) == cu and normalize(b) == fu:
            return "GAP", motivo
    return "INVESTIGAR", "Sem regra e não está na lista de exclusões esperadas."


def processar(df_norm, data):
    """Resolve a regra de cada linha e consolida POR REGRA CASADA (não por titular).
    Catálogos com regra geral (titular vazio) viram 1 grupo; catálogos com regras
    por titular/origem (ZEIDER, LUIZA...) ficam separados. Devolve (receitas, ignorados)."""
    regras = data.get("regras", [])
    periodo = (data.get("periodo") or "").strip()

    df = df_norm.copy()

    # 1) Regra de cada linha + chave de consolidação
    rule_por_linha, buckets = [], []
    for _, row in df.iterrows():
        cat, fonte = row["Catalogo"], row["Fonte"]
        if normalize(cat) in NEUTRALIZADOS:
            rule_por_linha.append("NEUTRALIZADO")
            buckets.append(f"NEUTRALIZADO|{normalize(cat)}|{normalize(fonte)}")
            continue
        rule = find_rule(regras, cat, fonte, row["Titular"], row["Origem"])
        rule_por_linha.append(rule)
        if rule is not None:
            buckets.append(f"REGRA|{id(rule)}")  # consolida tudo que casa a mesma regra
        else:
            buckets.append("SEM|" + "|".join(normalize(x) for x in
                            (cat, fonte, row["Titular"], row["Origem"])))
    df = df.assign(_rule=rule_por_linha, _bucket=buckets)

    receitas, ignorados = [], []
    for _, sub in df.groupby("_bucket", sort=False):
        first = sub.iloc[0]
        rule = first["_rule"]
        cat, fonte = first["Catalogo"], first["Fonte"]
        titular, origem = first["Titular"], first["Origem"]
        valor = round(float(sub["Valor"].sum()), 2)
        data_pg = norm_date(sub["Data"].max())

        if rule == "NEUTRALIZADO":
            _, motivo = classificar_ignorado(cat, fonte)
            ignorados.append({"Catalogo": cat, "Fonte": fonte, "Titular": titular or "-",
                              "Origem": origem or "-", "Valor": valor, "Data": data_pg,
                              "Classe": "ESPERADA", "Motivo": motivo})
            continue
        if rule is None or valor == 0:
            if valor == 0:
                classe, motivo = "ESPERADA", "Valor zero"
            else:
                classe, motivo = classificar_ignorado(cat, fonte)
            ignorados.append({"Catalogo": cat, "Fonte": fonte, "Titular": titular or "-",
                              "Origem": origem or "-", "Valor": valor, "Data": data_pg,
                              "Classe": classe, "Motivo": motivo})
            continue

        for inc in rule["incomes"]:
            org = float(inc["org_pct"])
            rights = float(inc["rights_pct"])
            total = org + rights

            net = valor * (total / 100.0)
            org_amt = net * (org / total) if total > 0 else 0.0

            net = round(net, 2)
            org_amt = round(org_amt, 2)
            rights_amt = round(net - org_amt, 2)  # Rights-Holder absorve centavos

            nome = f"{periodo} {inc['descricao']}".strip() if periodo else inc["descricao"]

            receitas.append({
                "Name (*)": nome,
                "Contract - Money In (*)": rule.get("money_in"),
                "Sale Date (*)": data_pg,
                "Payment Date (*)": data_pg,
                "Net Amount (*)": net,
                "Gross Amount": round(valor, 2),
                "Foreign Currency": "",
                "Foreign Net Amount": "",
                "Foreign Gross Amount": "",
                "Contract - Money Out (*)": inc["money_out"],
                "SPLIT AMOUNT | Organization (*)": org_amt,
                "SPLIT AMOUNT | Rights-Holder (*)": rights_amt,
                "Notes": f"Org: {org}% | Rights: {rights}%",
            })

    return pd.DataFrame(receitas), pd.DataFrame(ignorados)


# Estado: carrega as regras uma vez por sessão
if "di_rules" not in st.session_state:
    st.session_state.di_rules = load_rules()

data = st.session_state.di_rules


# ---------------------------------------------------------------------------
# Período (compartilhado entre as abas)
# ---------------------------------------------------------------------------
periodo = st.text_input(
    "Período (prefixo dos nomes das receitas)",
    value=data.get("periodo", ""),
    help="Ex.: 2026M04. Aplicado automaticamente no início de cada nome de receita.",
    key="di_periodo",
)
if periodo != data.get("periodo", ""):
    data["periodo"] = periodo  # calc usa o valor atual; é gravado ao salvar uma regra

st.caption(f"📚 {len(data.get('regras', []))} regras carregadas de `data/direct_incomes/regras.json`")

tab_calc, tab_lista, tab_rules = st.tabs(["🧮 Calcular", "📋 Lista de regras", "⚙️ Editar regras"])


# ===========================================================================
# ABA: CALCULAR
# ===========================================================================
with tab_calc:
    st.markdown("##### Processar extrato do BI")
    st.caption(
        "O arquivo deve conter as colunas: `Data`, `Catalogo`, `Fonte`, "
        "`Titular / Conta`, `Origem/Detalhe`, `Valor BRL` e `Motivo Processamento`. "
        "Pode ser o **histórico inteiro** (vários meses) — o mês é escolhido depois do upload. "
        "Linhas de rodapé (Total, Filtros aplicados) e que não sejam de **Direct Income** "
        "(pela coluna Motivo) são ignoradas."
    )

    uploaded = st.file_uploader(
        "Faça o upload do extrato do BI (.xlsx, .xls ou .csv) — histórico completo ou só um período",
        type=["xlsx", "xls", "csv"],
    )

    if uploaded is not None:
        df_norm, info = read_bi_extract(uploaded)
        if df_norm is None:
            st.error(info["erro"])
            st.write("Colunas disponíveis:", info["disponiveis"])
        else:
            partes = [f"{info['n_total']} linhas no arquivo"]
            if info["n_rodape"]:
                partes.append(f"{info['n_rodape']} rodapé(s) removido(s)")
            if info["n_proc"] is not None:
                partes.append(f"{info['n_final']} de Direct Income")
            st.success(" · ".join(partes) + ".")

            meses_serie = df_norm["Data"].dt.strftime("%YM%m")
            meses_disponiveis = sorted(
                (m for m in meses_serie.dropna().unique()), reverse=True
            )

            if not meses_disponiveis:
                st.warning("Nenhuma linha com `Data` válida encontrada — não dá pra escolher o mês.")
            else:
                c_mes, c_btn = st.columns([3, 1])
                default_idx = meses_disponiveis.index(periodo) if periodo in meses_disponiveis else 0
                mes_sel = c_mes.selectbox(
                    "Mês a processar (detectado pela coluna Data = recebimento)",
                    meses_disponiveis,
                    index=default_idx,
                    help="Regra do projeto: o período é o mês de RECEBIMENTO (coluna Data), "
                         "não o rótulo de lote (Mês Processamento).",
                )
                c_btn.markdown("<div style='height:28px'></div>", unsafe_allow_html=True)
                if c_btn.button("↳ Usar como período", help=f"Preenche o campo Período acima com {mes_sel}"):
                    st.session_state["di_periodo"] = mes_sel
                    data["periodo"] = mes_sel
                    st.rerun()

                df_mes = df_norm[meses_serie == mes_sel].copy()

                catalogos_disponiveis = sorted(df_mes["Catalogo"].unique())
                cats_sel = st.multiselect(
                    "Filtrar catálogo(s) (opcional — vazio = processa todos os catálogos do mês)",
                    catalogos_disponiveis,
                )
                df_periodo = df_mes[df_mes["Catalogo"].isin(cats_sel)] if cats_sel else df_mes

                partes_mes = [f"{len(df_mes)} linhas em {mes_sel}"]
                if cats_sel:
                    partes_mes.append(f"{len(df_periodo)} após filtro de catálogo")
                st.caption(" · ".join(partes_mes) + ".")

                with st.expander("Ver dados filtrados"):
                    st.dataframe(df_periodo, use_container_width=True, hide_index=True)

                if st.button("Processar receitas", type="primary", disabled=df_periodo.empty):
                    df_out, df_ign = processar(df_periodo, data)
                    st.session_state["di_result"] = df_out
                    st.session_state["di_ignorados"] = df_ign
                if df_periodo.empty:
                    st.info("Nenhuma linha para processar com esse mês/catálogo(s).")

    # Resultado (persiste no estado para não sumir ao baixar)
    if "di_result" in st.session_state:
        df_out = st.session_state["di_result"]
        df_ign = st.session_state["di_ignorados"]

        st.divider()
        c1, c2, c3 = st.columns(3)
        c1.metric("Receitas geradas", len(df_out))
        c2.metric("Grupos ignorados", len(df_ign))
        bruto = df_out["Gross Amount"].drop_duplicates().sum() if len(df_out) else 0.0
        c3.metric("Bruto distribuído", f"R$ {bruto:,.2f}")

        if len(df_out):
            st.markdown("##### Resultado")
            st.dataframe(df_out, use_container_width=True, hide_index=True)

            # Validação: soma dos Net por Gross deve fechar com o Gross
            val = df_out.groupby("Gross Amount").agg(Net=("Net Amount (*)", "sum")).reset_index()
            val["Diferença"] = (val["Gross Amount"] - val["Net"]).round(2)
            ok = (val["Diferença"].abs() < 0.01).all()
            if ok:
                st.success(f"✅ Validação de totais OK ({len(val)}/{len(val)} grupos fecham com o bruto).")
            else:
                st.warning("⚠️ Há grupos cujo Net não fecha com o Gross:")
                st.dataframe(val[val["Diferença"].abs() >= 0.01], use_container_width=True, hide_index=True)

            csv_bytes = df_out.to_csv(index=False).encode("utf-8-sig")
            ts = datetime.now().strftime("%Y%m%d_%H%M%S")
            per = (data.get("periodo") or "").strip() or "sem_periodo"
            st.download_button(
                "📥 Baixar CSV (Reprtoir)",
                data=csv_bytes,
                file_name=f"direct_incomes_{per}_{ts}.csv",
                mime="text/csv",
                type="primary",
            )
        else:
            st.info("Nenhuma receita gerada — verifique se há regras para os catálogos do arquivo.")

        if len(df_ign):
            n_investigar = int((df_ign["Classe"] == "INVESTIGAR").sum()) if "Classe" in df_ign else 0
            n_gap = int((df_ign["Classe"] == "GAP").sum()) if "Classe" in df_ign else 0
            st.markdown("##### ⚠️ Grupos ignorados — triagem")
            st.caption(
                "**ESPERADA** = sabemos que não gera receita aqui, ok ignorar · "
                "**GAP** = falta cadastrar regra · **INVESTIGAR** = não está em nenhuma lista, "
                "pode ser regra nova ou erro de rótulo."
            )
            ordem_classe = {"INVESTIGAR": 0, "GAP": 1, "ESPERADA": 2}
            df_ign_view = df_ign.copy()
            df_ign_view["_ordem"] = df_ign_view["Classe"].map(ordem_classe).fillna(3)
            df_ign_view = df_ign_view.sort_values("_ordem").drop(columns="_ordem")
            st.dataframe(df_ign_view, use_container_width=True, hide_index=True)
            st.caption(f"💰 Total ignorado: R$ {df_ign['Valor'].sum():,.2f}")
            if n_investigar:
                st.warning(f"❓ {n_investigar} grupo(s) em INVESTIGAR — confira antes de importar, "
                           "pode ser regra nova ou catálogo mal rotulado no BI.")
            if n_gap:
                st.warning(f"🟡 {n_gap} grupo(s) em GAP — falta cadastrar regra (aba **Editar regras**).")


# ===========================================================================
# ABA: LISTA DE REGRAS (visão geral, somente leitura)
# ===========================================================================
with tab_lista:
    st.markdown("##### Todas as regras")
    st.caption("Agrupadas por fonte e catálogo, com titular, origem e os percentuais de cada receita.")

    regras_all = data.get("regras", [])
    df_rules = rules_to_dataframe(regras_all)

    if df_rules.empty:
        st.info("Nenhuma regra cadastrada ainda. Crie a primeira na aba **Editar regras**.")
    else:
        c1, c2, c3 = st.columns(3)
        c1.metric("Regras", len(regras_all))
        c2.metric("Fontes", df_rules["Fonte"].nunique())
        c3.metric("Linhas de receita", len(df_rules))

        # Alerta: regras cujas fatias (Org % + Rights %) não somam ~100%
        fora = []
        for r in regras_all:
            soma = sum(float(i.get("org_pct") or 0) + float(i.get("rights_pct") or 0) for i in r.get("incomes", []))
            if abs(soma - 100) > 0.05:
                fora.append({
                    "Catálogo": r.get("catalogo", ""),
                    "Fonte": r.get("fonte", ""),
                    "Titular": r.get("titular") or "-",
                    "Origem": r.get("origem") or "-",
                    "Soma %": round(soma, 2),
                })
        if fora:
            with st.expander(f"⚠️ {len(fora)} regra(s) cujas fatias não somam 100%"):
                st.dataframe(pd.DataFrame(fora), use_container_width=True, hide_index=True)

        fontes = sorted(df_rules["Fonte"].unique())
        sel_fontes = st.multiselect("Filtrar por fonte", fontes, placeholder="Todas as fontes")
        view = df_rules if not sel_fontes else df_rules[df_rules["Fonte"].isin(sel_fontes)]

        pct_cfg = {
            "Org %": st.column_config.NumberColumn("Org %", format="%.2f%%"),
            "Rights %": st.column_config.NumberColumn("Rights %", format="%.2f%%"),
            "Total %": st.column_config.NumberColumn("Total %", format="%.2f%%"),
        }

        for fonte, gdf in view.groupby("Fonte"):
            n_regras = gdf[["Catálogo", "Titular", "Origem"]].drop_duplicates().shape[0]
            with st.expander(f"🎵 {fonte}  ·  {n_regras} regra(s)"):
                st.dataframe(
                    gdf.drop(columns=["Fonte"]).reset_index(drop=True),
                    use_container_width=True,
                    hide_index=True,
                    column_config=pct_cfg,
                )

        st.divider()
        with st.expander("📄 Ver tabela completa (plana)"):
            st.dataframe(view, use_container_width=True, hide_index=True, column_config=pct_cfg)

        st.download_button(
            "📥 Baixar lista de regras (CSV)",
            data=view.to_csv(index=False).encode("utf-8-sig"),
            file_name="direct_incomes_regras.csv",
            mime="text/csv",
        )


# ===========================================================================
# ABA: EDITAR REGRAS (editor completo)
# ===========================================================================
with tab_rules:
    st.markdown("##### Editor de regras")
    st.caption(
        "Cada regra é uma combinação de **Catálogo + Fonte**, com **Titular** e **Origem** opcionais. "
        "A regra mais específica vence: se houver uma regra com o titular/origem da transação, ela é "
        "usada; senão cai na regra geral de Catálogo+Fonte. O titular casa de forma tolerante "
        "(ignora acento/maiúsculas e aceita abreviações como 'Hele' → 'Helena')."
    )

    regras = data.setdefault("regras", [])

    busca = st.text_input("🔎 Buscar (catálogo, fonte, titular ou origem)", key="di_busca").strip().lower()
    idxs = list(range(len(regras)))
    if busca:
        idxs = [i for i in idxs if busca in rule_label(regras[i]).lower()]

    opcoes = ["➕ Nova regra"] + idxs
    sel = st.selectbox(
        "Selecione a regra para editar",
        opcoes,
        format_func=lambda x: "➕ Nova regra" if x == "➕ Nova regra" else rule_label(regras[x]),
        key="di_sel",
    )

    nova = sel == "➕ Nova regra"
    atual = (
        {"catalogo": "", "fonte": "", "titular": "", "origem": "", "money_in": "", "incomes": []}
        if nova else regras[sel]
    )

    with st.form("di_rule_form"):
        c1, c2 = st.columns(2)
        f_catalogo = c1.text_input("Catálogo", value=atual.get("catalogo", ""))
        f_fonte = c2.text_input("Fonte", value=atual.get("fonte", ""))

        c3, c4 = st.columns(2)
        f_titular = c3.text_input(
            "Titular / Conta (opcional)", value=atual.get("titular") or "",
            help="Ex.: ZEIDER, Z PRODUCOES, HELENA. Vazio = vale para qualquer titular.",
        )
        f_origem = c4.text_input(
            "Origem/Detalhe (opcional)", value=atual.get("origem") or "",
            help="Ex.: VENDA CATALOGO, TRANSFERIDO. Vazio = vale para qualquer origem.",
        )

        f_money_in = st.text_input("Contract - Money In", value=atual.get("money_in") or "")

        st.markdown("**Receitas (incomes)**")
        st.caption(
            "Uma linha por receita. `Organization %` + `Rights-Holder %` é a fatia do bruto "
            "que vai para esta receita. A soma de todas as linhas normalmente dá 100%."
        )
        inc_df = (
            pd.DataFrame(atual["incomes"], columns=INCOME_COLS)
            if atual.get("incomes") else pd.DataFrame(columns=INCOME_COLS)
        )
        edited = st.data_editor(
            inc_df,
            num_rows="dynamic",
            use_container_width=True,
            column_config={
                "descricao": st.column_config.TextColumn("Descrição (sem período)", width="large"),
                "money_out": st.column_config.TextColumn("Contract - Money Out", width="large"),
                "org_pct": st.column_config.NumberColumn("Organization %", min_value=0.0, max_value=100.0, step=0.01),
                "rights_pct": st.column_config.NumberColumn("Rights-Holder %", min_value=0.0, max_value=100.0, step=0.01),
            },
            key="di_inc_editor",
        )

        submitted = st.form_submit_button("💾 Salvar regra", type="primary")

    if submitted:
        incomes = []
        for _, r in edited.iterrows():
            desc = str(r.get("descricao") or "").strip()
            mout = str(r.get("money_out") or "").strip()
            if not desc and not mout:
                continue
            incomes.append({
                "descricao": desc,
                "money_out": mout,
                "org_pct": float(r.get("org_pct") or 0),
                "rights_pct": float(r.get("rights_pct") or 0),
            })

        erros = []
        if not f_catalogo.strip():
            erros.append("Catálogo é obrigatório.")
        if not f_fonte.strip():
            erros.append("Fonte é obrigatória.")
        if not incomes:
            erros.append("Adicione pelo menos uma receita.")

        if erros:
            for e in erros:
                st.error(e)
        else:
            nova_regra = {
                "catalogo": f_catalogo.strip(),
                "fonte": f_fonte.strip(),
                "titular": f_titular.strip() or None,
                "origem": f_origem.strip() or None,
                "money_in": f_money_in.strip(),
                "incomes": incomes,
            }
            nova_key = (normalize(nova_regra["catalogo"]), normalize(nova_regra["fonte"]),
                        normalize(nova_regra["titular"]), normalize(nova_regra["origem"]))
            dup = any(
                (normalize(r["catalogo"]), normalize(r["fonte"]),
                 normalize(r.get("titular")), normalize(r.get("origem"))) == nova_key
                for j, r in enumerate(regras) if nova or j != sel
            )
            if dup:
                st.warning("Já existe uma regra com esse Catálogo + Fonte + Titular + Origem. Edite-a em vez de duplicar.")
            else:
                if nova:
                    regras.append(nova_regra)
                else:
                    regras[sel] = nova_regra
                data["periodo"] = periodo
                save_rules(data)
                soma = sum(i["org_pct"] + i["rights_pct"] for i in incomes)
                st.success("Regra salva em disco. ✅")
                if abs(soma - 100) > 0.05:
                    st.warning(f"Atenção: a soma das fatias é {soma:.2f}% (esperado ~100%). Confira os percentuais.")
                st.rerun()

    if not nova:
        st.divider()
        cda, cdb, _ = st.columns([1, 1, 2])
        if cda.button("📋 Duplicar regra"):
            copia = json.loads(json.dumps(regras[sel]))
            copia["titular"] = (copia.get("titular") or "") + " (cópia)"
            regras.append(copia)
            save_rules(data)
            st.success("Regra duplicada. Edite a cópia (ajuste titular/origem).")
            st.rerun()

        if cdb.button("🗑️ Excluir regra", type="secondary"):
            regras.pop(sel)
            save_rules(data)
            st.success("Regra excluída.")
            st.rerun()

    if not nova and atual.get("incomes"):
        with st.expander("👁️ Prévia dos nomes com o período aplicado"):
            per = (periodo or "").strip()
            for inc in atual["incomes"]:
                nome = f"{per} {inc['descricao']}".strip() if per else inc["descricao"]
                st.write(f"• {nome}")
