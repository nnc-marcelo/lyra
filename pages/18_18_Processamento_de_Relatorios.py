import streamlit as st
import openpyxl
import io

st.title("Processamento de Relatórios")
st.caption("Transforma relatórios e prepara-os para o Reprtoir.")

template = st.selectbox("STATEMENT TEMPLATE:", ["Nikita Digital"])

# Para o template Nikita, geramos um arquivo por aba (por posição, base 1).
# "last" = última aba.
NIKITA_OUTPUTS = [
    ("DSP", 2),              # segunda aba
    ("YouTube", 3),          # terceira aba
    ("YouTube Music", "last"),  # última aba
]

uploaded = st.file_uploader("Upload do relatório (.xlsx)", type=["xlsx"])


def build_single_sheet(raw_bytes, keep_idx):
    """Retorna um xlsx em memória contendo apenas a aba do índice informado."""
    wb = openpyxl.load_workbook(io.BytesIO(raw_bytes))
    keep_name = wb.sheetnames[keep_idx]
    for name in list(wb.sheetnames):
        if name != keep_name:
            del wb[name]
    out = io.BytesIO()
    wb.save(out)
    out.seek(0)
    return out, keep_name


if uploaded:
    raw = uploaded.read()
    sheets = openpyxl.load_workbook(io.BytesIO(raw), read_only=True).sheetnames
    base_name = uploaded.name.rsplit(".", 1)[0]

    st.success(f"Arquivo carregado com {len(sheets)} aba(s). Baixe cada relatório abaixo:")

    for label, rule in NIKITA_OUTPUTS:
        keep_idx = len(sheets) - 1 if rule == "last" else rule - 1

        if keep_idx < 0 or keep_idx >= len(sheets):
            st.warning(f"{label}: aba esperada não encontrada (arquivo tem {len(sheets)} abas).")
            continue

        data, keep_name = build_single_sheet(raw, keep_idx)
        st.download_button(
            label=f"Baixar {label}  (aba: {keep_name})",
            data=data,
            file_name=f"{base_name}_{label}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            key=label,
        )
