"""
Chassi comum a todas as páginas do app.

Antes, cada página cuidava (ou não) da própria configuração: só 4 das 10
chamavam `st.set_page_config`, então título da aba, ícone e largura mudavam de
página para página; e o `st.logo` estava só no Home, sumindo nas demais — em
multipage cada página roda o próprio script.

Com `st.navigation` isso deixa de ser possível de esquecer: o entrypoint
(`Home.py`) chama `bootstrap()` uma vez por rerun, e ele vale para a página que
estiver aberta. `set_page_config` NÃO pode ser chamado dentro das páginas
quando se usa `st.navigation` — é por isso que `setup_page()` cuida só do
cabeçalho.
"""

from pathlib import Path

import streamlit as st

from utils import nav

RAIZ = Path(__file__).resolve().parents[1]
ASSETS = RAIZ / "assets"
_CSS = ASSETS / "theme.css"


def bootstrap() -> None:
    """Configuração global. Chamada só pelo entrypoint, antes de
    `st.navigation`."""
    st.set_page_config(
        page_title="Lyra",
        page_icon=str(ASSETS / "lyra_favicon.png"),
        layout="wide",
    )
    st.logo(
        str(ASSETS / "lyra_lockup_horizontal.png"),
        icon_image=str(ASSETS / "lyra_favicon.png"),
    )
    _injetar_css()


def _injetar_css() -> None:
    """Injeta assets/theme.css. Os tokens de cor vivem lá, e não espalhados em
    hex literal pelo código (era o caso do `#fff7e9` em utils/ui_components)."""
    try:
        css = _CSS.read_text(encoding="utf-8")
    except OSError:
        return
    st.markdown(f"<style>{css}</style>", unsafe_allow_html=True)


def setup_page(arquivo: str, titulo: str | None = None, descricao: str | None = None) -> None:
    """Cabeçalho padrão da página. Chame como primeira instrução de Streamlit
    da página, passando `__file__`:

        from utils.page import setup_page
        setup_page(__file__)

    Título e descrição vêm do registro em `utils/nav.py` (mesmo texto do menu
    lateral). Passe `titulo`/`descricao` só para sobrescrever pontualmente.
    """
    entrada = nav.por_caminho(arquivo)
    titulo_final = titulo or (entrada.titulo if entrada else Path(arquivo).stem)
    descricao_final = descricao or (entrada.descricao if entrada else None)

    st.title(titulo_final)
    if descricao_final:
        st.caption(descricao_final)
