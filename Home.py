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

from utils import metrics, nav
from utils.page import bootstrap

bootstrap()

# Rótulo e função que produz cada métrica do painel. A função devolve None
# quando a base correspondente não está disponível — ver utils/metrics.py.
METRICAS = [
    ("Faixas mapeadas", metrics.faixas_mapeadas),
    ("Obras — Irmãos Vitale", metrics.obras_catalogo),
    ("Credenciais ativas", metrics.credenciais),
    ("Última varredura", metrics.ultima_varredura),
]

# Quantas ferramentas por linha na grade de cards.
COLUNAS = 3


def _painel_metricas() -> None:
    for coluna, (rotulo, carregar) in zip(st.columns(len(METRICAS)), METRICAS):
        with coluna:
            metrica = carregar()
            if metrica is None:
                st.metric(rotulo, "—", help="Base não disponível neste ambiente.")
                continue
            st.metric(rotulo, metrica.valor, help=metrica.ajuda)
            if metrica.alerta:
                st.caption(":orange[Desatualizada]")


def _grade_ferramentas() -> None:
    for secao in nav.ORDEM_SECOES:
        paginas = [p for p in nav.PAGINAS if p.secao == secao]
        if not paginas:
            continue
        st.subheader(secao)
        # Uma grade por seção, preenchida em linhas de COLUNAS cards. As colunas
        # são criadas por linha (e não uma vez só) para que a última linha
        # incompleta não estique os cards que sobraram.
        for inicio in range(0, len(paginas), COLUNAS):
            linha = paginas[inicio : inicio + COLUNAS]
            colunas = st.columns(COLUNAS)
            for coluna, pagina in zip(colunas, linha):
                with coluna, st.container(border=True):
                    st.page_link(pagina.caminho, label=f"**{pagina.titulo}**", icon=pagina.icone)
                    st.caption(pagina.descricao)


def _pagina_inicio():
    st.image("assets/lyra_lockup_horizontal.png", width=380)
    st.header("Central de royalties e catálogo")
    st.caption(
        "Processe relatórios das distribuidoras, calcule taxas e descontos, "
        "e cruze tudo com o catálogo Nas Nuvens."
    )
    st.write("")
    _painel_metricas()
    st.divider()
    _grade_ferramentas()


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
