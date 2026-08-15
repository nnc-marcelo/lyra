import streamlit as st
import streamlit_shadcn_ui as ui

st.title("Teste - streamlit-shadcn-ui")

st.subheader("Botões")
c1, c2, c3 = st.columns(3)
with c1:
    ui.button(text="Default", key="btn_default")
with c2:
    ui.button(text="Secondary", variant="secondary", key="btn_secondary")
with c3:
    ui.button(text="Destructive", variant="destructive", key="btn_destructive")

st.subheader("Card metric")
cols = st.columns(3)
with cols[0]:
    ui.metric_card(title="Total Comprovantes", content="128", description="+12 esse mes", key="card1")
with cols[1]:
    ui.metric_card(title="Pendentes", content="7", description="-3 esse mes", key="card2")
with cols[2]:
    ui.metric_card(title="Titulares", content="34", description="sem alteracao", key="card3")

st.subheader("Tabs")
tabs = ui.tabs(options=["Tab A", "Tab B", "Tab C"], default_value="Tab A", key="tabs1")
st.write("Tab selecionada:", tabs)

st.subheader("Input + Switch")
val = ui.input(default_value="", placeholder="Digite algo", key="input1")
st.write("Valor:", val)
sw = ui.switch(default_checked=True, label="Ativo", key="switch1")
st.write("Switch:", sw)
