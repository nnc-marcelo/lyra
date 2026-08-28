"""
Leitura das bases de catálogo/mapeamento usadas no cruzamento.

Este módulo existe porque as mesmas bases são lidas em dois lugares: a página
de cruzamento (views/cruzamento_catalogo.py), que processa os relatórios, e o
Home (utils/metrics.py), que só conta o que há em cada uma. Importar a página
para reusar a função não é opção — o script dela roda a UI inteira ao ser
importado —, então as funções puras moram aqui.

Nada aqui pode depender de `streamlit`: é o que mantém o módulo importável dos
dois lados e testável sem subir o app.
"""

import re
import xml.etree.ElementTree as ET
import zipfile
from collections import defaultdict

import pandas as pd

_NS = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"


def read_mapping_sony(file_path: str) -> pd.DataFrame:
    """Lê a base de mapeamento Sony descompactando o xlsx e lendo o XML.

    O openpyxl (e portanto `pd.read_excel`) falha neste arquivo com "could not
    read stylesheet ... invalid XML": ele vem de um exportador que grava um
    stylesheet quebrado. Os dados em si estão íntegros, então lê-se sheet1.xml
    direto, resolvendo as células de texto pela tabela de strings
    compartilhadas. Cabeçalho na linha 1.
    """
    with zipfile.ZipFile(file_path, "r") as zip_ref:
        try:
            shared_root = ET.fromstring(zip_ref.read("xl/sharedStrings.xml"))
            shared_strings = [si.text or "" for si in shared_root.findall(f".//{_NS}t")]
        except (KeyError, ET.ParseError):
            shared_strings = []

        sheet_root = ET.fromstring(zip_ref.read("xl/worksheets/sheet1.xml"))

        data: defaultdict[int, dict[str, str]] = defaultdict(dict)
        for row in sheet_root.findall(f".//{_NS}row"):
            row_num = int(row.get("r"))
            for cell in row.findall(f".//{_NS}c"):
                value_elem = cell.find(f".//{_NS}v")
                if value_elem is None or value_elem.text is None:
                    continue
                value = value_elem.text
                if cell.get("t") == "s" and shared_strings:
                    value = shared_strings[int(value)]
                col = re.sub(r"[^A-Z]", "", cell.get("r"))
                data[row_num][col] = value

    if 1 not in data:
        raise ValueError("Cabeçalho não encontrado na linha 1 do arquivo.")

    header = data[1]
    sorted_cols = sorted(header)
    rows_list = [
        {header.get(col, col): data[row_num].get(col, "") for col in sorted_cols}
        for row_num in range(2, max(data) + 1)
        if row_num in data
    ]
    return pd.DataFrame(rows_list)


_CATALOGO_ALIASES = ("CATÁLOGO", "CATALOGO", "CATALOGO CORRETO", "CATÁLOGO CORRETO")


def _catalog_col(df: pd.DataFrame):
    """Nome real da coluna de catálogo em `df`, ou None."""
    cols = {str(c).strip().upper(): c for c in df.columns}
    for alias in _CATALOGO_ALIASES:
        if alias in cols:
            return cols[alias]
    return None


def normalize_catalog_column(df: pd.DataFrame) -> pd.DataFrame:
    """Renomeia a coluna de catálogo para `CATÁLOGO`.

    Cada fonte grafa do seu jeito — ABRAMUS manda "CATÁLOGO" (ou "CATALOGO
    CORRETO" na base nova, com as colunas de ISWC/ISRC), Sony "Catalogo",
    Irmãos Vitale "Catálogo" — e o resto do código espera um nome só.
    """
    cat_col = _catalog_col(df)
    if cat_col is None:
        raise ValueError(
            "Base não tem coluna de catálogo (esperado uma de: "
            + ", ".join(_CATALOGO_ALIASES)
            + f"). Colunas encontradas: {list(df.columns)}"
        )
    if cat_col != "CATÁLOGO":
        df = df.rename(columns={cat_col: "CATÁLOGO"})
    return df


def read_catalog_base(source, dtype=str) -> pd.DataFrame:
    """Lê uma base de catálogo em XLSX de forma robusta a arquivos com várias
    abas (planilhas), cabeçalho fora da primeira aba, ou aba de rascunho.

    Percorre TODAS as abas e devolve, já com `.columns` limpo (strip) e a coluna
    de catálogo renomeada para `CATÁLOGO`, a primeira aba que tenha uma coluna de
    catálogo reconhecível. Prefere a aba que também tenha `CÓD. OBRA`. Se nenhuma
    servir, levanta ValueError listando abas e colunas — mensagem acionável em
    vez do `pd.read_excel` cego, que pegava a aba 0 (bug em produção quando a aba
    boa não era a primeira).
    """
    planilhas = pd.read_excel(source, sheet_name=None, dtype=dtype)

    candidatas = []
    for nome, df in planilhas.items():
        df = df.copy()
        df.columns = [str(c).strip() for c in df.columns]
        if _catalog_col(df) is not None:
            tem_cod_obra = any(str(c).strip().upper() == "CÓD. OBRA" for c in df.columns)
            candidatas.append((0 if tem_cod_obra else 1, nome, df))

    if not candidatas:
        resumo = {n: list(d.columns) for n, d in planilhas.items()}
        raise ValueError(
            "Nenhuma aba do arquivo tem coluna de catálogo "
            f"({', '.join(_CATALOGO_ALIASES)}). Abas e colunas: {resumo}"
        )

    candidatas.sort(key=lambda t: t[0])
    _, _nome, df = candidatas[0]
    return normalize_catalog_column(df)


def read_mapping_xlsx(source, dtype=str) -> pd.DataFrame:
    """Lê um xlsx de mapeamento (catálogo, artistas, etc.) escolhendo a ABA
    principal quando o arquivo tem várias.

    Genérico (não exige coluna de catálogo, ao contrário de `read_catalog_base`):
    prefere a aba com coluna de catálogo; senão a com `Artist`; senão a de maior
    volume (linhas × colunas). Só faz `strip` nos nomes de coluna — não renomeia
    nada.
    """
    planilhas = pd.read_excel(source, sheet_name=None, dtype=dtype)
    if not planilhas:
        return pd.DataFrame()

    def _prep(df):
        df = df.copy()
        df.columns = [str(c).strip() for c in df.columns]
        return df

    abas = {n: _prep(d) for n, d in planilhas.items()}

    for nome, df in abas.items():
        if _catalog_col(df) is not None:
            return df
    for nome, df in abas.items():
        if any(str(c).strip().lower() == "artist" for c in df.columns):
            return df
    return max(abas.values(), key=lambda d: d.shape[0] * max(d.shape[1], 1))
