"""
Entrypoint do app (lyra) — Central de royalties e catálogo da Nas Nuvens.

A navegação é declarada aqui com `st.navigation`, e não mais pela descoberta
automática da pasta `pages/`. O que se ganha: nomes legíveis no menu (antes
saía o nome do arquivo, "18_18_Processamento_de_Relatorios"), agrupamento por
seção (eram 10 ferramentas numa lista plana) e um único ponto onde a
configuração global da página é aplicada — ver utils/page.py.

As páginas ficam em `views/`. O diretório NÃO pode se chamar `pages/`: com esse
nome o Streamlit monta a navegação automática por conta própria, ignorando o
que está declarado aqui.
"""

import streamlit as st

from utils import nav
from utils.page import bootstrap

bootstrap()


def _pagina_inicio():
    st.image("assets/lyra_lockup_horizontal.png", width=380)
    st.header("Central de royalties e catálogo")
    st.caption(
        "Processe relatórios das distribuidoras, calcule taxas e descontos, "
        "e cruze tudo com o catálogo Nas Nuvens."
    )
    st.divider()
    for secao in nav.ORDEM_SECOES:
        paginas = [p for p in nav.PAGINAS if p.secao == secao]
        if not paginas:
            continue
        st.subheader(secao)
        for pagina in paginas:
            st.page_link(pagina.caminho, label=pagina.titulo, icon=pagina.icone)
            st.caption(pagina.descricao)


inicio = st.Page(_pagina_inicio, title="Início", icon=":material/home:", default=True)

secoes: dict[str, list] = {"": [inicio]}
for secao in nav.ORDEM_SECOES:
    secoes[secao] = []
for pagina in nav.PAGINAS:
    secoes.setdefault(pagina.secao, []).append(
        st.Page(pagina.caminho, title=pagina.titulo, icon=pagina.icone)
    )

# Página de teste do shadcn-ui: só aparece se a lib estiver instalada. Ela não
# está no requirements.txt, então no Streamlit Cloud a seção simplesmente não
# existe, em vez de derrubar o app com ImportError.
try:
    import streamlit_shadcn_ui  # noqa: F401

    secoes["Dev"] = [
        st.Page("views/_teste_shadcn.py", title="Teste shadcn-ui", icon=":material/science:")
    ]
except ImportError:
    pass

st.navigation({k: v for k, v in secoes.items() if v}).run()
