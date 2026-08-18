"""
Registro único das páginas do app.

Fonte de verdade para navegação E cabeçalho: `Home.py` monta o menu lateral a
partir desta lista, e `utils.page.setup_page()` procura aqui a entrada da
página que está rodando para renderar título/descrição. Assim o nome que
aparece no menu e o que aparece no topo da página nunca divergem — antes cada
página repetia o próprio `st.title`, com estilos diferentes (umas com emoji,
outras não, umas usando `st.header` como título).

Para adicionar uma página: crie o arquivo em `views/` e registre aqui. Não há
mais descoberta automática por nome de arquivo (era o que produzia itens de
menu do tipo "18_18_Processamento_de_Relatorios" na barra lateral).

`icone` usa nomes de Material Symbols no formato aceito por `st.Page`
(":material/<nome>:").
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class Pagina:
    caminho: str      # relativo à raiz do repo (onde roda o Home.py)
    titulo: str       # rótulo no menu e título no topo da página
    icone: str
    secao: str
    descricao: str    # legenda sob o título; também usada nos cards do Home


PAGINAS: list[Pagina] = [
    Pagina(
        caminho="views/processamento_relatorios.py",
        titulo="Processamento de relatórios",
        icone=":material/file_upload:",
        secao="Processamento",
        descricao="Transforma relatórios das distribuidoras e prepara-os para o Reprtoir.",
    ),
    Pagina(
        caminho="views/ingrooves_breaker.py",
        titulo="Ingrooves breaker",
        icone=":material/content_cut:",
        secao="Processamento",
        descricao="Desconta 30% das receitas dos EUA e separa o relatório por artista.",
    ),
    Pagina(
        caminho="views/onerpm_pre_processamento.py",
        titulo="OneRPM pré-processamento",
        icone=":material/tune:",
        secao="Processamento",
        descricao="Normaliza os relatórios OneRPM antes do processamento principal.",
    ),
    Pagina(
        caminho="views/cruzamento_catalogo.py",
        titulo="Cruzamento com catálogo",
        icone=":material/compare_arrows:",
        secao="Catálogo",
        descricao="Concilia os relatórios recebidos com a base de obras do catálogo.",
    ),
    Pagina(
        caminho="views/varredura_lacunas.py",
        titulo="Varredura de lacunas",
        icone=":material/search:",
        secao="Catálogo",
        descricao="Mostra o relatório de royalties que deixaram de ser recebidos.",
    ),
    Pagina(
        caminho="views/withholding_calculator.py",
        titulo="Withholding calculator",
        icone=":material/percent:",
        secao="Cálculos",
        descricao="Desconta 30% das receitas dos EUA.",
    ),
    Pagina(
        caminho="views/direct_incomes.py",
        titulo="Direct incomes",
        icone=":material/payments:",
        secao="Cálculos",
        descricao="Distribui receitas diretas por catálogo, fonte e titular.",
    ),
    Pagina(
        caminho="views/douglas_cezar_ep.py",
        titulo="Douglas Cezar EP",
        icone=":material/album:",
        secao="Cálculos",
        descricao="Calcula os shares do deal e consolida as incomes do EP.",
    ),
    Pagina(
        caminho="views/organizador_comprovantes.py",
        titulo="Organizador de comprovantes",
        icone=":material/folder:",
        secao="Utilitários",
        descricao="Organiza o .zip de comprovantes ABRAMUS/UBC na estrutura da base.",
    ),
    Pagina(
        caminho="views/abramus_int_to_excel.py",
        titulo="ABRAMUS INT para Excel",
        icone=":material/table_view:",
        secao="Utilitários",
        descricao="Extrai o PDF do demonstrativo internacional da ABRAMUS para planilha.",
    ),
]

# Ordem em que as seções aparecem no menu. Seção de página não listada aqui
# vai para o fim.
ORDEM_SECOES = ["Processamento", "Catálogo", "Cálculos", "Utilitários"]


def por_caminho(caminho: str) -> Pagina | None:
    """Entrada cujo `caminho` bate com o final de `caminho` (aceita caminho
    absoluto, que é o que `__file__` entrega)."""
    normalizado = caminho.replace("\\", "/")
    for p in PAGINAS:
        if normalizado.endswith(p.caminho):
            return p
    return None
