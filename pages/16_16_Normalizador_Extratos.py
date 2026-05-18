import streamlit as st
import pandas as pd
import io

st.title("Editor de Extratos Bancários")

banco = st.selectbox("Selecione o banco:", ["Itaú", "Bradesco"])

def insert_cols_after_lancamento(df):
    cols = list(df.columns)
    lanc_idx = None
    for i, c in enumerate(cols):
        if "lan" in str(c).lower():
            lanc_idx = i
            break
    if lanc_idx is None:
        lanc_idx = 1
    df.insert(lanc_idx + 1, "Código", "")
    df.insert(lanc_idx + 2, "Classificação", "")
    return df

def drop_saldo_col(df):
    for c in df.columns:
        if "saldo" in str(c).lower():
            df = df.drop(columns=[c])
            break
    return df

def parse_br_number(series):
    """Convert Brazilian number strings (1.234,56) to float."""
    return (
        series.str.strip()
        .str.replace(".", "", regex=False)
        .str.replace(",", ".", regex=False)
        .pipe(pd.to_numeric, errors="coerce")
    )

# ─── ITAÚ ────────────────────────────────────────────────────────────────────
if banco == "Itaú":
    uploaded = st.file_uploader("Upload do extrato Itaú (.xlsx)", type=["xlsx"])
    if uploaded:
        raw = pd.read_excel(uploaded, header=None)

        header_row = 9
        headers = raw.iloc[header_row].tolist()
        data = raw.iloc[header_row + 1:].reset_index(drop=True)
        data.columns = headers

        data = drop_saldo_col(data)
        data = insert_cols_after_lancamento(data)

        st.success("Arquivo processado com sucesso!")
        st.dataframe(data.head(20))

        csv_bytes = data.to_csv(index=False, sep=";", encoding="utf-8-sig").encode("utf-8-sig")
        st.download_button(
            label="Baixar CSV",
            data=csv_bytes,
            file_name="extrato_itau.csv",
            mime="text/csv",
        )

# ─── BRADESCO ─────────────────────────────────────────────────────────────────
else:
    uploaded = st.file_uploader("Upload do extrato Bradesco (.csv)", type=["csv"])
    if uploaded:
        content = uploaded.read().decode("latin-1")
        lines = content.splitlines()

        if len(lines) < 3:
            st.error("Arquivo com menos de 3 linhas.")
            st.stop()

        header_line = lines[2]
        sep = ";" if ";" in header_line else ","

        cleaned = "\n".join(lines[2:])
        df = pd.read_csv(io.StringIO(cleaned), sep=sep, dtype=str, encoding="latin-1", on_bad_lines="skip")

        # Convert numeric columns at read time — proper BR format (1.234,56 → 1234.56)
        for col in df.columns:
            col_lower = str(col).lower()
            if any(k in col_lower for k in ["créd", "déb", "cred", "deb", "valor"]):
                df[col] = parse_br_number(df[col])

        df = drop_saldo_col(df)
        df = insert_cols_after_lancamento(df)

        # Find first "Total" in column A and drop that row + everything below
        col_a = df.columns[0]
        total_idx = None
        for i, val in enumerate(df[col_a]):
            if str(val).strip().lower() == "total":
                total_idx = i
                break

        if total_idx is not None:
            df = df.iloc[:total_idx].reset_index(drop=True)

        st.success("Arquivo processado com sucesso!")
        st.dataframe(df.head(20))

        csv_bytes = df.to_csv(index=False, sep=";", encoding="utf-8-sig").encode("utf-8-sig")
        st.download_button(
            label="Baixar CSV",
            data=csv_bytes,
            file_name="extrato_bradesco.csv",
            mime="text/csv",
        )