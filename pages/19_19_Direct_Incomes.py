import streamlit as st
import pandas as pd
import json
from pathlib import Path
from io import BytesIO
from datetime import datetime

# ============================================================================
# Direct Incomes
# Calcula a distribuição de receitas diretas (Power BI -> Reprtoir) a partir
# de regras por (Catálogo, Fonte[, Histórico]) que são editáveis pelo app.
# As regras ficam em data/direct_incomes/regras.json (persistidas em disco).
# ============================================================================

st.title("Direct Incomes")
st.caption(
    "Distribui receitas diretas por catálogo/fonte e gera o arquivo pronto "
    "para o Reprtoir. As regras de cálculo são editáveis aqui mesmo, sem mexer no código."
)

RULES_PATH = Path(__file__).resolve().parent.parent / "data" / "direct_incomes" / "regras.json"

INCOME_COLS = ["descricao", "money_out", "org_pct", "rights_pct"]

# Colunas esperadas no CSV exportado do Power BI
COL_DATA = "Data Pagamento"
COL_CATALOGO = "Catalogo"
COL_FONTE = "Fonte"
COL_HISTORICO = "Historico"
COL_VALOR = "Valor"


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
    if r.get("historico"):
        partes.append(r["historico"])
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
                "Histórico": r.get("historico") or "",
                "Money In": r.get("money_in") or "",
                "Receita": inc.get("descricao", ""),
                "Money Out": inc.get("money_out", ""),
                "Org %": org,
                "Rights %": rights,
                "Total %": round(org + rights, 2),
            })
    df = pd.DataFrame(rows)
    if not df.empty:
        df = df.sort_values(["Fonte", "Catálogo", "Histórico"], kind="stable").reset_index(drop=True)
    return df


# Estado: carrega as regras uma vez por sessão
if "di_rules" not in st.session_state:
    st.session_state.di_rules = load_rules()

data = st.session_state.di_rules


# ---------------------------------------------------------------------------
# Cálculo
# ---------------------------------------------------------------------------
def build_lookup(regras):
    """Indexa as regras por (cat, fonte) ou (cat, fonte, hist)."""
    lut = {}
    for r in regras:
        cat, fonte, hist = r["catalogo"], r["fonte"], r.get("historico")
        key = (cat, fonte, hist) if hist else (cat, fonte)
        lut[key] = r
    return lut


def coerce_money(series):
    """Converte a coluna de valor para número, aceitando 1234.56 e 1.234,56."""
    s = series.astype(str).str.strip()
    num = pd.to_numeric(s, errors="coerce")
    # Se muitos falharam, tenta formato brasileiro (milhar '.' e decimal ',')
    if num.isna().mean() > 0.3:
        s2 = s.str.replace(".", "", regex=False).str.replace(",", ".", regex=False)
        num = pd.to_numeric(s2, errors="coerce")
    return num.fillna(0.0)


def norm_date(value):
    if isinstance(value, pd.Timestamp):
        return value.strftime("%Y-%m-%d")
    if isinstance(value, str):
        try:
            return pd.to_datetime(value).strftime("%Y-%m-%d")
        except Exception:
            return datetime.now().strftime("%Y-%m-%d")
    try:
        return pd.to_datetime(value).strftime("%Y-%m-%d")
    except Exception:
        return datetime.now().strftime("%Y-%m-%d")


def processar(df_input, data):
    """Agrupa o CSV, aplica as regras e devolve (df_receitas, df_ignorados)."""
    regras = data.get("regras", [])
    periodo = (data.get("periodo") or "").strip()
    lut = build_lookup(regras)
    keys = set(lut.keys())

    df = df_input.copy()
    if COL_HISTORICO not in df.columns:
        df[COL_HISTORICO] = pd.NA

    # Remove rodapés/linhas de junk do export do Power BI
    # (linha "Total", "Filtros aplicados:", linhas em branco — ficam sem Catálogo/Fonte)
    df = df[df[COL_CATALOGO].notna() & df[COL_FONTE].notna()].copy()

    # Normaliza chaves (espaços acidentais), datas e valores
    df[COL_CATALOGO] = df[COL_CATALOGO].astype(str).str.strip()
    df[COL_FONTE] = df[COL_FONTE].astype(str).str.strip()
    df[COL_DATA] = pd.to_datetime(df[COL_DATA], errors="coerce")
    df[COL_VALOR] = coerce_money(df[COL_VALOR])

    def group_key(row):
        cat, fonte, hist = row[COL_CATALOGO], row[COL_FONTE], row[COL_HISTORICO]
        if pd.notna(hist) and (cat, fonte, hist) in keys:
            return (cat, fonte, hist)
        return (cat, fonte)

    df["_gk"] = df.apply(group_key, axis=1)
    grouped = (
        df.groupby("_gk", dropna=False)
        .agg(
            Catalogo=(COL_CATALOGO, "first"),
            Fonte=(COL_FONTE, "first"),
            Historico=(COL_HISTORICO, "first"),
            Valor=(COL_VALOR, "sum"),
            Data=(COL_DATA, "max"),
        )
        .reset_index(drop=True)
    )
    grouped["Valor"] = grouped["Valor"].round(2)

    receitas = []
    ignorados = []

    for _, row in grouped.iterrows():
        cat, fonte, hist = row["Catalogo"], row["Fonte"], row["Historico"]
        valor = float(row["Valor"])
        data_pg = norm_date(row["Data"])

        rule = lut.get((cat, fonte, hist)) if pd.notna(hist) else None
        if rule is None:
            rule = lut.get((cat, fonte))

        if rule is None or valor <= 0:
            ignorados.append({
                "Catalogo": cat,
                "Fonte": fonte,
                "Historico": hist if pd.notna(hist) else "-",
                "Valor": valor,
                "Data": data_pg,
                "Motivo": "Sem regra" if rule is None else "Valor <= 0",
            })
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


# ---------------------------------------------------------------------------
# Período (compartilhado entre as duas abas)
# ---------------------------------------------------------------------------
periodo = st.text_input(
    "Período (prefixo dos nomes das receitas)",
    value=data.get("periodo", ""),
    help="Ex.: 2025Q4. Aplicado automaticamente no início de cada nome de receita.",
)
if periodo != data.get("periodo", ""):
    data["periodo"] = periodo  # persiste só ao salvar regras; calc usa o valor atual

st.caption(f"📚 {len(data.get('regras', []))} regras carregadas de `data/direct_incomes/regras.json`")

tab_calc, tab_lista, tab_rules = st.tabs(["🧮 Calcular", "📋 Lista de regras", "⚙️ Editar regras"])


# ===========================================================================
# ABA: CALCULAR
# ===========================================================================
with tab_calc:
    st.markdown("##### Processar extrato do Power BI")
    st.caption(
        f"O arquivo deve conter as colunas: `{COL_DATA}`, `{COL_CATALOGO}`, "
        f"`{COL_FONTE}`, `{COL_HISTORICO}` (opcional) e `{COL_VALOR}`. "
        "Linhas de rodapé do Power BI (Total, Filtros aplicados, em branco) são ignoradas automaticamente."
    )

    uploaded = st.file_uploader(
        "Faça o upload do extrato do Power BI (.csv, .xlsx ou .xls)",
        type=["csv", "xlsx", "xls"],
    )

    if uploaded is not None:
        try:
            uploaded.seek(0)
            if uploaded.name.lower().endswith(".csv"):
                df_input = pd.read_csv(uploaded, sep=None, engine="python")
            else:
                df_input = pd.read_excel(uploaded)
        except Exception as e:
            st.error(f"Não consegui ler o arquivo: {e}")
            df_input = None

        if df_input is not None:
            faltando = [c for c in (COL_DATA, COL_CATALOGO, COL_FONTE, COL_VALOR) if c not in df_input.columns]
            if faltando:
                st.error(f"Colunas obrigatórias não encontradas: {faltando}")
                st.write("Colunas disponíveis:", list(df_input.columns))
            else:
                st.success(f"Arquivo carregado: {len(df_input)} transações.")
                with st.expander("Ver dados originais"):
                    st.dataframe(df_input, use_container_width=True)

                if st.button("Processar receitas", type="primary"):
                    df_out, df_ign = processar(df_input, data)
                    st.session_state["di_result"] = df_out
                    st.session_state["di_ignorados"] = df_ign

    # Resultado (persiste no estado para não sumir ao baixar)
    if "di_result" in st.session_state:
        df_out = st.session_state["di_result"]
        df_ign = st.session_state["di_ignorados"]

        st.divider()
        c1, c2, c3 = st.columns(3)
        c1.metric("Receitas geradas", len(df_out))
        c2.metric("Ignoradas", len(df_ign))
        bruto = df_out["Gross Amount"].drop_duplicates().sum() if len(df_out) else 0.0
        c3.metric("Bruto distribuído", f"R$ {bruto:,.2f}")

        if len(df_out):
            st.markdown("##### Resultado")
            st.dataframe(df_out, use_container_width=True)

            # Validação: soma dos Net por Gross deve fechar com o Gross
            val = df_out.groupby("Gross Amount").agg(Net=("Net Amount (*)", "sum")).reset_index()
            val["Diferença"] = (val["Gross Amount"] - val["Net"]).round(2)
            ok = (val["Diferença"].abs() < 0.01).all()
            if ok:
                st.success(f"✅ Validação de totais OK ({len(val)}/{len(val)} grupos fecham com o bruto).")
            else:
                st.warning("⚠️ Há grupos cujo Net não fecha com o Gross:")
                st.dataframe(val[val["Diferença"].abs() >= 0.01], use_container_width=True)

            # Download CSV pronto para o Reprtoir
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
            st.markdown("##### ⚠️ Transações ignoradas (sem regra)")
            st.dataframe(df_ign, use_container_width=True)
            st.caption(f"💰 Total ignorado: R$ {df_ign['Valor'].sum():,.2f}")


# ===========================================================================
# ABA: LISTA DE REGRAS (visão geral, somente leitura)
# ===========================================================================
with tab_lista:
    st.markdown("##### Todas as regras")
    st.caption("Agrupadas por fonte e catálogo, com os percentuais de cada receita.")

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
                    "Histórico": r.get("historico") or "-",
                    "Soma %": round(soma, 2),
                })
        if fora:
            with st.expander(f"⚠️ {len(fora)} regra(s) cujas fatias não somam 100%"):
                st.dataframe(pd.DataFrame(fora), use_container_width=True, hide_index=True)

        # Filtro por fonte
        fontes = sorted(df_rules["Fonte"].unique())
        sel_fontes = st.multiselect("Filtrar por fonte", fontes, placeholder="Todas as fontes")
        view = df_rules if not sel_fontes else df_rules[df_rules["Fonte"].isin(sel_fontes)]

        pct_cfg = {
            "Org %": st.column_config.NumberColumn("Org %", format="%.2f%%"),
            "Rights %": st.column_config.NumberColumn("Rights %", format="%.2f%%"),
            "Total %": st.column_config.NumberColumn("Total %", format="%.2f%%"),
        }

        # Agrupado por fonte -> (catálogo / histórico)
        for fonte, g in view.groupby("Fonte"):
            n_regras = g[["Catálogo", "Histórico"]].drop_duplicates().shape[0]
            with st.expander(f"🎵 {fonte}  ·  {n_regras} regra(s)"):
                st.dataframe(
                    g.drop(columns=["Fonte"]).reset_index(drop=True),
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
# ABA: REGRAS (editor completo)
# ===========================================================================
with tab_rules:
    st.markdown("##### Editor de regras")
    st.caption(
        "Cada regra é uma combinação de **Catálogo + Fonte (+ Histórico opcional)**. "
        "O Histórico tem prioridade: se existir uma regra com o histórico exato da transação, "
        "ela é usada; senão cai na regra geral de Catálogo+Fonte."
    )

    regras = data.setdefault("regras", [])

    # Filtro de busca + seleção
    busca = st.text_input("🔎 Buscar (catálogo, fonte ou histórico)", key="di_busca").strip().lower()
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
        {"catalogo": "", "fonte": "", "historico": "", "money_in": "", "incomes": []}
        if nova else regras[sel]
    )

    with st.form("di_rule_form"):
        c1, c2 = st.columns(2)
        f_catalogo = c1.text_input("Catálogo", value=atual.get("catalogo", ""))
        f_fonte = c2.text_input("Fonte", value=atual.get("fonte", ""))

        c3, c4 = st.columns(2)
        f_historico = c3.text_input(
            "Histórico (opcional)", value=atual.get("historico") or "",
            help="Deixe vazio para a regra geral de Catálogo+Fonte.",
        )
        f_money_in = c4.text_input("Contract - Money In", value=atual.get("money_in") or "")

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
        # Limpa linhas vazias e normaliza
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
                "historico": f_historico.strip() or None,
                "money_in": f_money_in.strip(),
                "incomes": incomes,
            }
            # Detecta duplicidade de chave (em outra posição)
            nova_key = (nova_regra["catalogo"], nova_regra["fonte"], nova_regra["historico"])
            dup = any(
                (r["catalogo"], r["fonte"], r.get("historico")) == nova_key
                for j, r in enumerate(regras) if nova or j != sel
            )
            if dup:
                st.warning("Já existe uma regra com esse Catálogo + Fonte + Histórico. Edite-a em vez de duplicar.")
            else:
                if nova:
                    regras.append(nova_regra)
                else:
                    regras[sel] = nova_regra
                data["periodo"] = periodo  # garante período atual no arquivo
                save_rules(data)
                soma = sum(i["org_pct"] + i["rights_pct"] for i in incomes)
                st.success("Regra salva em disco. ✅")
                if abs(soma - 100) > 0.05:
                    st.warning(f"Atenção: a soma das fatias é {soma:.2f}% (esperado ~100%). Confira os percentuais.")
                st.rerun()

    # Ações fora do formulário (duplicar / excluir) — só para regra existente
    if not nova:
        st.divider()
        cda, cdb, _ = st.columns([1, 1, 2])
        if cda.button("📋 Duplicar regra"):
            copia = json.loads(json.dumps(regras[sel]))
            copia["historico"] = (copia.get("historico") or "") + " (cópia)"
            regras.append(copia)
            save_rules(data)
            st.success("Regra duplicada. Edite a cópia (ajuste o histórico).")
            st.rerun()

        if cdb.button("🗑️ Excluir regra", type="secondary"):
            regras.pop(sel)
            save_rules(data)
            st.success("Regra excluída.")
            st.rerun()

    # Prévia de como os nomes ficam com o período aplicado
    if not nova and atual.get("incomes"):
        with st.expander("👁️ Prévia dos nomes com o período aplicado"):
            per = (periodo or "").strip()
            for inc in atual["incomes"]:
                nome = f"{per} {inc['descricao']}".strip() if per else inc["descricao"]
                st.write(f"• {nome}")
