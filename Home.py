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
    ("Obras nas bases", metrics.bases_cruzamento),
    ("Credenciais ativas", metrics.credenciais),
    ("Última varredura", metrics.ultima_varredura),
]

TITULO_POR_CAMINHO = {p.caminho: p.titulo for p in nav.PAGINAS}


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


def _tabela_bases() -> None:
    """Uma linha por fonte do cruzamento. Existe porque a métrica agregada
    esconde duas coisas que importam: a unidade não é a mesma nas quatro
    (obra × faixa) e cada base é atualizada por um caminho diferente, então
    saber qual está velha é metade da informação."""
    bases = metrics.bases_por_fonte()
    if not bases:
        return
    st.subheader("Bases de cruzamento")
    st.dataframe(
        [
            {
                "Fonte": b.fonte,
                "Itens": b.itens,
                "Unidade": b.unidade,
                "Catálogos": b.catalogos,
                "Atualizada": b.atualizada,
            }
            for b in bases
        ],
        hide_index=True,
        width="stretch",
        column_config={
            "Itens": st.column_config.NumberColumn(format="%d"),
            "Catálogos": st.column_config.NumberColumn(
                format="%d", help="Catálogos distintos dentro da base. A Ingrooves agrupa por tag de artista, não por catálogo."
            ),
            "Atualizada": st.column_config.DatetimeColumn(format="DD/MM/YYYY HH:mm"),
        },
    )


def _painel_pendencias() -> None:
    """O que está esperando ação. Não repete o menu lateral: cada item existe
    por causa de um fato apurado nas bases, e o link é só o caminho para
    resolvê-lo."""
    st.subheader("Pendências")
    itens = metrics.pendencias()
    if not itens:
        st.success("Nada pendente nas bases.", icon=":material/check_circle:")
        return
    for item in itens:
        with st.container(border=True):
            marcador = ":orange[▲]" if item.atencao else ":gray[•]"
            st.markdown(f"{marcador} **{item.titulo}**")
            st.caption(item.detalhe)
            st.page_link(
                item.pagina,
                label=f"Abrir {TITULO_POR_CAMINHO.get(item.pagina, item.pagina)}",
                icon=":material/arrow_forward:",
            )


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
    _painel_pendencias()
    st.divider()
    _tabela_bases()


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
