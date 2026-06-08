import streamlit as st
import openpyxl
import io

st.title("Processamento de Relatórios")
st.caption("Transforma relatórios e prepara-os para o Reprtoir.")

# Cada template define qual aba manter (por posição, base 1).
TEMPLATES = {
    "Nikita Digital (YouTube Music)": "last",   # mantém apenas a última aba
    "Nikita Digital (YouTube)": 3,              # mantém apenas a terceira aba
    "Nikita Digital (DSP)": 2,                  # mantém apenas a segunda aba
}

template = st.selectbox("STATEMENT TEMPLATE:", list(TEMPLATES.keys()))

uploaded = st.file_uploader("Upload do relatório (.xlsx)", type=["xlsx"])

if uploaded:
    wb = openpyxl.load_workbook(io.BytesIO(uploaded.read()))
    sheets = wb.sheetnames

    rule = TEMPLATES[template]
    if rule == "last":
        keep_idx = len(sheets) - 1
    else:
        keep_idx = rule - 1  # posição base 1 -> índice base 0

    if keep_idx < 0 or keep_idx >= len(sheets):
        st.error(
            f"O arquivo possui {len(sheets)} aba(s), não foi possível localizar a aba esperada "
            f"para o template '{template}'."
        )
        st.stop()

    keep_name = sheets[keep_idx]

    # Remove todas as outras abas, mantendo apenas a desejada.
    for name in list(wb.sheetnames):
        if name != keep_name:
            del wb[name]

    output = io.BytesIO()
    wb.save(output)
    output.seek(0)

    st.success(f"Arquivo processado! Aba mantida: '{keep_name}'.")

    base_name = uploaded.name.rsplit(".", 1)[0]
    st.download_button(
        label="Baixar arquivo processado",
        data=output,
        file_name=f"{base_name}_processado.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )
