"""Leitura do extrato exportado do BI (colunas Data/Catalogo/Fonte/Titular/Valor).

Compartilhado porque o mesmo tipo de exportação é lido em dois lugares:
`views/direct_incomes.py` (calcula as receitas diretas por regra) e
`views/douglas_cezar_ep.py` (usa o extrato "RR" só para validar o valor
recebido e descobrir a data de pagamento). Importar uma página para reusar a
função não é opção — o script dela roda a UI inteira ao ser importado —,
então a leitura pura mora aqui. Sem `streamlit`: é o que mantém o módulo
importável dos dois lados e testável sem subir o app.
"""

import unicodedata

import pandas as pd

# Nomes de coluna aceitos no extrato do BI. Cada campo aceita variações de
# nome; a leitura escolhe a primeira que existir.
COL_CANDIDATES = {
    "data": ["Data Pagamento", "Data"],
    "catalogo": ["Catalogo", "Catálogo"],
    "fonte": ["Fonte"],
    "titular": ["Titular / Conta", "Titular", "Titular/Conta"],
    "origem": ["Origem/Detalhe", "Origem / Detalhe", "Origem"],
    "valor": ["Valor BRL", "Valor"],
    "processamento": ["Processamento"],
    "motivo": ["Motivo Processamento", "Motivo"],
}


def normalize(s):
    """Maiúsculas, sem acento, espaços colapsados — para comparar chaves."""
    s = str(s if s is not None else "")
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode()
    return " ".join(s.upper().split())


def coerce_money(series):
    """Converte a coluna de valor para número, aceitando 1234.56 e 1.234,56."""
    s = series.astype(str).str.strip()
    num = pd.to_numeric(s, errors="coerce")
    if num.isna().mean() > 0.3:
        s2 = s.str.replace(".", "", regex=False).str.replace(",", ".", regex=False)
        num = pd.to_numeric(s2, errors="coerce")
    return num.fillna(0.0)


def pick_col(df, names):
    low = {str(c).strip().lower(): c for c in df.columns}
    for n in names:
        if n.lower() in low:
            return low[n.lower()]
    for c in df.columns:
        cl = str(c).strip().lower()
        if any(cl.startswith(n.lower()) for n in names):
            return c
    return None


def read_bi_extract(uploaded, apenas_direct_income=True):
    """Lê o extrato do BI e devolve (df_normalizado, info). df tem colunas:
    Catalogo, Fonte, Titular, Origem, Valor, Data[, Processamento, Motivo].

    `apenas_direct_income=False` mantém todas as linhas do catálogo/fonte,
    mesmo as ainda sem `Motivo Processamento` preenchido — necessário para
    conciliar um recebimento que ainda não foi classificado no BI.
    """
    if hasattr(uploaded, "seek"):
        uploaded.seek(0)
    nome = getattr(uploaded, "name", str(uploaded)).lower()
    if nome.endswith(".csv"):
        raw = pd.read_csv(uploaded, sep=None, engine="python")
    else:
        raw = pd.read_excel(uploaded)

    cols = {k: pick_col(raw, v) for k, v in COL_CANDIDATES.items()}
    faltando = [k for k in ("data", "catalogo", "fonte", "valor") if cols[k] is None]
    if faltando:
        return None, {"erro": f"Colunas obrigatórias não encontradas: {faltando}",
                      "disponiveis": list(raw.columns)}

    df = pd.DataFrame({
        "Catalogo": raw[cols["catalogo"]],
        "Fonte": raw[cols["fonte"]],
        "Titular": raw[cols["titular"]] if cols["titular"] else "",
        "Origem": raw[cols["origem"]] if cols["origem"] else "",
        "Valor": raw[cols["valor"]],
        "Data": raw[cols["data"]],
    })
    if cols["processamento"]:
        df["Processamento"] = raw[cols["processamento"]]
    if cols["motivo"]:
        df["Motivo"] = raw[cols["motivo"]]

    n_total = len(df)

    # Remove rodapés do BI (Total / Filtros aplicados / em branco): sem catálogo/fonte
    df = df[df["Catalogo"].notna() & df["Fonte"].notna()].copy()
    n_sem_rodape = len(df)

    # Mantém apenas as linhas de Direct Income (coluna Motivo Processamento)
    n_proc = None
    if apenas_direct_income and "Motivo" in df.columns:
        mask = df["Motivo"].astype(str).str.contains("Direct Income", case=False, na=False)
        df = df[mask].copy()
        n_proc = len(df)

    for c in ("Catalogo", "Fonte", "Titular", "Origem"):
        df[c] = df[c].fillna("").astype(str).str.strip()
    df["Data"] = pd.to_datetime(df["Data"], errors="coerce")
    df["Valor"] = coerce_money(df["Valor"])

    info = {"n_total": n_total, "n_rodape": n_total - n_sem_rodape, "n_proc": n_proc, "n_final": len(df)}
    return df, info
