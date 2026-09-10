"""
Componentes de UI compartilhados entre páginas do Streamlit.

Padrão visual: tabelas HTML com cabeçalho no off-white da marca, opcionalmente
translúcido + blur. A folha de estilo vive em `assets/theme.css` (classe
`.nn-tabela`, injetada por `utils.page.bootstrap()`); aqui só se monta a
marcação. As cores vêm dos tokens `--nn-*` daquele arquivo, e não em hex
literal repetido por aqui. Indicadores de status usam uma bolinha
colorida (verde = ativo/preenchido, cinza = inativo/pendente) em vez de
texto/emoji em linha — mais rápido de escanear numa lista. Ícone no app é
Material Symbols (o `icon=` dos widgets do Streamlit), nunca emoji: o
Material é monocromático e assume a cor do tema, o emoji traz a paleta dele.

Este módulo nasceu do Organizador de Comprovantes (views/organizador_comprovantes.py) e deve ser
reusado por qualquer página que precise do mesmo visual, em vez de duplicar
a implementação localmente.
"""

import html
import re
from functools import lru_cache
from pathlib import Path

import streamlit as st

_ASSETS = Path(__file__).resolve().parents[1] / "assets"

COR_ATIVO = "var(--nn-verde, #1D9E75)"
COR_INATIVO = "var(--nn-cinza, #888780)"


def render_html_table(headers: list[str], body_rows_html: list[str], max_height: str = "420px", translucent: bool = True):
    """Tabela HTML padrão do app: cabeçalho no off-white quente da marca
    (mesmo tom de `secondaryBackgroundColor` em .streamlit/config.toml —
    sidebar, cards, expanders), com rolagem interna quando passa de
    `max_height`. `body_rows_html` já vem pronto (uma string `<tr>...</tr>`
    por linha) — use `simple_row` ou `status_dot_html` para montar essas
    linhas.

    `translucent=True` (padrão) dá o efeito vidro fosco usado no Organizador de
    Comprovantes. `translucent=False` reforça a tintura do cabeçalho — use em
    tabelas com muitas linhas visíveis por vez, onde o blur sozinho ainda deixa
    entrever o texto rolado por baixo. O estilo mora em assets/theme.css: aqui
    não entra cor literal, que quebraria no tema escuro."""
    thead_cells = "".join(f"<th>{html.escape(h)}</th>" for h in headers)
    classe = "nn-tabela" if translucent else "nn-tabela nn-tabela--solido"
    table_html = (
        f'<div class="{classe}" style="max-height:{max_height};">'
        "<table>"
        f"<thead><tr>{thead_cells}</tr></thead><tbody>"
        + "".join(body_rows_html)
        + "</tbody></table></div>"
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


# ---------------------------------------------------------------------------
# Estado vazio e veredito
# ---------------------------------------------------------------------------


@lru_cache(maxsize=1)
def _lira_svg() -> str:
    """A lira da marca, pronta para embutir em HTML.

    Lê `assets/lyra_icon.svg` (o desenho fino do kit — não o favicon, que é o
    corte pesado para 16px) e troca a cor fixa por `currentColor`, para o SVG
    herdar a cor de quem o contém. Devolve string vazia se o arquivo sumir: um
    estado vazio sem desenho ainda funciona, um ImportError na home não."""
    try:
        svg = (_ASSETS / "lyra_icon.svg").read_text(encoding="utf-8")
    except OSError:
        return ""
    svg = re.sub(r'fill="#[0-9a-fA-F]{3,8}"', 'fill="currentColor"', svg)
    # tira largura/altura fixas para o CSS mandar no tamanho
    svg = re.sub(r'\s(width|height)="[^"]*"', "", svg, count=2)
    return svg.strip()


def estado_vazio(titulo: str, detalhe: str = "") -> None:
    """O painel quando não há nada a fazer.

    Existe porque "nada pendente" é o único momento de recompensa do app, e uma
    caixa verde genérica desperdiça isso. Fica no mesmo recuo dos itens de
    pendência (não centralizado) para o painel não mudar de eixo quando a lista
    esvazia."""
    st.markdown(
        f'<div class="nn-vazio">{_lira_svg()}'
        f'<div><p class="nn-vazio-titulo">{html.escape(titulo)}</p>'
        f'{f"<p class=nn-vazio-detalhe>{html.escape(detalhe)}</p>" if detalhe else ""}'
        "</div></div>",
        unsafe_allow_html=True,
    )


def veredito(ok: bool, titulo: str, detalhe: str = "") -> None:
    """Uma conta que fecha ou não fecha.

    Para números que são a resposta da página, não mais um dado dela — o
    fechamento do recibo da RR contra o crédito bancário, por exemplo. Como
    `st.metric` no meio de outras métricas, esse número lê como o quarto de
    quatro iguais; aqui ele lê como veredito, e a cor carrega o estado (verde
    fecha, terracota não fecha) antes de o texto ser lido."""
    estado = "ok" if ok else "atencao"
    st.markdown(
        f'<div class="nn-veredito nn-veredito--{estado}">'
        f'<p class="nn-veredito-titulo">{html.escape(titulo)}</p>'
        f'{f"<p class=nn-veredito-detalhe>{html.escape(detalhe)}</p>" if detalhe else ""}'
        "</div>",
        unsafe_allow_html=True,
    )


def retomada(titulo: str, detalhe: str = "", atencao: bool = False) -> None:
    """Onde você parou da última vez nesta tela.

    Um lembrete de continuidade, não um status: tarefas que se repetem todo mês
    (processar o relatório de uma distribuidora, p. ex.) e é fácil esquecer qual
    foi o último período. Diferente do `veredito` — que é a resposta de um
    cálculo — e da bolinha de `status_dot_html`, que é estado vivo de um serviço.
    Por isso não usa verde: "tem histórico" não é um estado bom, é só um fato.

    `atencao=True` pinta de terracota e serve ao caso em que o período prestes a
    ser processado é o mesmo já registrado (está reprocessando). O título sai no
    headingFont — o período é a informação que se procura aqui, então lê como
    resposta, não como rótulo."""
    estado = "atencao" if atencao else "neutro"
    st.markdown(
        f'<div class="nn-retomada nn-retomada--{estado}">'
        f'<p class="nn-retomada-titulo">{html.escape(titulo)}</p>'
        f'{f"<p class=nn-retomada-detalhe>{html.escape(detalhe)}</p>" if detalhe else ""}'
        "</div>",
        unsafe_allow_html=True,
    )
