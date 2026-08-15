"""
Componentes de UI compartilhados entre páginas do Streamlit.

Padrão visual: tabelas HTML com cabeçalho no off-white da marca, opcionalmente
translúcido + blur. A folha de estilo vive em `assets/theme.css` (classe
`.nn-tabela`, injetada por `utils.page.bootstrap()`); aqui só se monta a
marcação. As cores vêm dos tokens `--nn-*` daquele arquivo, e não em hex
literal repetido por aqui. Indicadores de status usam uma bolinha
colorida (verde = ativo/preenchido, cinza = inativo/pendente) em vez de
texto/emoji em linha — mais rápido de escanear numa lista.

Este módulo nasceu do Organizador de Comprovantes (views/organizador_comprovantes.py) e deve ser
reusado por qualquer página que precise do mesmo visual, em vez de duplicar
a implementação localmente.
"""

import html

import streamlit as st

ICON_MAPEADO = "🟢"
ICON_PENDENTE = "⚪"
ICON_AVISO = "⚠️"
ICON_INFO = "ℹ️"
ICON_SUCESSO = "✅"
ICON_ERRO = "❌"

COR_ATIVO = "var(--nn-verde, #1D9E75)"
COR_INATIVO = "var(--nn-cinza, #888780)"


def render_html_table(headers: list[str], body_rows_html: list[str], max_height: str = "420px", translucent: bool = True):
    """Tabela HTML padrão do app: cabeçalho no off-white quente da marca
    (mesmo tom de `secondaryBackgroundColor` em .streamlit/config.toml —
    sidebar, cards, expanders), com rolagem interna quando passa de
    `max_height`. `body_rows_html` já vem pronto (uma string `<tr>...</tr>`
    por linha) — use `simple_row` ou `status_dot_html` para montar essas
    linhas.

    `translucent=True` (padrão) dá o efeito vidro fosco (opacidade 0.92 +
    blur) usado no Organizador de Comprovantes. `translucent=False` deixa o
    cabeçalho sólido (`#fff7e9` opaco, sem blur) — use em tabelas com muitas
    linhas visíveis por vez, onde mesmo opacidade alta ainda deixa entrever
    o texto rolado por baixo."""
    thead_cells = "".join(f"<th>{html.escape(h)}</th>" for h in headers)
    header_bg = (
        "background:color-mix(in srgb, var(--nn-offwhite) 92%, transparent); backdrop-filter:blur(6px);"
        if translucent
        else ""
    )
    table_html = (
        f'<div class="nn-tabela" style="max-height:{max_height};">'
        "<table>"
        f'<thead style="{header_bg}">'
        f"<tr>{thead_cells}</tr></thead><tbody>" + "".join(body_rows_html) + "</tbody></table></div>"
    )
    st.markdown(table_html, unsafe_allow_html=True)


def simple_row(cells: list, style: str = "") -> str:
    """Uma linha `<tr>` com células de texto simples (escapadas). Para células
    com HTML embutido (ex.: bolinha de status), monte a `<tr>` manualmente."""
    tds = "".join(f"<td>{html.escape(str(c))}</td>" for c in cells)
    return f'<tr style="{style}">{tds}</tr>'


def status_dot_html(active: bool, color_active: str = COR_ATIVO, color_inactive: str = COR_INATIVO) -> str:
    """Bolinha de 8px indicando status (verde = ativo, cinza = inativo).
    Retorna HTML cru — use dentro de uma célula, antes do texto do label."""
    color = color_active if active else color_inactive
    return (
        f'<span style="display:inline-block;width:8px;height:8px;border-radius:50%;'
        f'background:{color};margin-right:8px;"></span>'
    )


def render_status_table(headers: list[str], rows: list[dict], status_key: str, label_key: str, max_height: str = "300px", translucent: bool = True):
    """Tabela com bolinha de status na primeira coluna (junto do label) e as
    demais colunas como texto simples. Linhas inativas ficam esmaecidas.

    `rows`: lista de dicts, cada um com pelo menos `status_key` (bool) e
    `label_key` (texto da 1ª coluna); as demais chaves usadas são os nomes
    em `headers[1:]`. Ver `render_html_table` para o parâmetro `translucent`.
    """
    rows_html = []
    for r in rows:
        active = bool(r.get(status_key))
        primeira_celula = f'<td>{status_dot_html(active)}{html.escape(str(r.get(label_key, "")))}</td>'
        outras_celulas = "".join(
            f"<td>{html.escape(str(r.get(h, '')))}</td>" for h in headers[1:]
        )
        style = "" if active else "opacity: 0.6;"
        rows_html.append(f'<tr style="{style}">{primeira_celula}{outras_celulas}</tr>')
    render_html_table(headers, rows_html, max_height=max_height, translucent=translucent)
