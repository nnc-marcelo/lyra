"""
Varredura de Lacunas — Royalties (visualizador)

Exibe o relatório pré-gerado pela varredura da base histórica do rpa-royalties.
A varredura roda de forma agendada (diária) numa máquina que enxerga o Z:,
grava o HTML/CSV em rpa-royalties e os copia para lyra/data/varredura_lacunas/,
fazendo push para o GitHub. O Streamlit Cloud lê o artefato direto deste repo.

Nenhuma varredura, credencial ou acesso ao Z: acontece aqui.
"""

from datetime import datetime
from pathlib import Path

import streamlit as st
import streamlit.components.v1 as components

st.set_page_config(
    page_title="Varredura de Lacunas — Royalties",
    page_icon="📊",
    layout="wide",
)

# ─────────────────────────────────────────────────────────────
# Caminho do relatório pré-gerado
# O script de varredura (rpa-royalties) grava o relatório e o
# copia para lyra/data/varredura_lacunas/ via run_varredura_diaria.bat,
# que também faz push para o GitHub. Assim o Streamlit Cloud lê
# o arquivo diretamente do próprio repo, sem depender de sibling.
# ─────────────────────────────────────────────────────────────
REPORT_DIR = Path(__file__).resolve().parents[1] / "data" / "varredura_lacunas"
HTML_PATH = REPORT_DIR / "relatorio_royalties.html"
CSV_PATH  = REPORT_DIR / "relatorio_royalties.csv"
TS_PATH   = REPORT_DIR / "last_updated.txt"

# Cadência esperada: diária. Acima disto, o relatório é considerado defasado.
STALE_AFTER_DAYS = 2

st.title("📊 Varredura de Lacunas — Royalties")
st.caption(
    "Mapa de períodos por conta/credencial da base histórica. "
    "O relatório é gerado automaticamente todo dia pela varredura do rpa-royalties."
)

if not HTML_PATH.exists():
    st.warning(
        "⚠️ Relatório ainda não gerado.\n\n"
        f"Esperado em:\n`{HTML_PATH}`\n\n"
        "Verifique se a tarefa agendada de varredura já rodou ao menos uma vez."
    )
    st.stop()

if TS_PATH.exists():
    mtime = datetime.fromisoformat(TS_PATH.read_text().strip())
else:
    mtime = datetime.fromtimestamp(HTML_PATH.stat().st_mtime)

age_days = (datetime.now() - mtime).days

if age_days >= STALE_AFTER_DAYS:
    st.warning(
        f"⚠️ Relatório possivelmente defasado — gerado há {age_days} dia(s) "
        f"({mtime:%d/%m/%Y às %H:%M}). Confira se a tarefa agendada está rodando."
    )
else:
    st.success(f"✅ Atualizado em {mtime:%d/%m/%Y às %H:%M}")

html = HTML_PATH.read_text(encoding="utf-8")

col1, col2 = st.columns(2)
with col1:
    st.download_button(
        "⬇️ Baixar relatório (HTML)",
        data=html.encode("utf-8"),
        file_name="relatorio_royalties.html",
        mime="text/html",
        use_container_width=True,
    )
with col2:
    if CSV_PATH.exists():
        st.download_button(
            "⬇️ Baixar dados (CSV)",
            data=CSV_PATH.read_bytes(),
            file_name="relatorio_royalties.csv",
            mime="text/csv",
            use_container_width=True,
        )
    else:
        st.button("⬇️ CSV indisponível", disabled=True, use_container_width=True)

st.divider()

components.html(html, height=1100, scrolling=True)
