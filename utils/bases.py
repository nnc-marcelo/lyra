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


def normalize_catalog_column(df: pd.DataFrame) -> pd.DataFrame:
    """Renomeia a coluna de catálogo para `CATÁLOGO`.

    Cada fonte grafa do seu jeito — ABRAMUS manda "CATÁLOGO" (ou "CATALOGO
    CORRETO" na base nova, com as colunas de ISWC/ISRC), Sony "Catalogo",
    Irmãos Vitale "Catálogo" — e o resto do código espera um nome só.
    """
    cols = {c.upper(): c for c in df.columns}
    for alias in ("CATÁLOGO", "CATALOGO", "CATALOGO CORRETO", "CATÁLOGO CORRETO"):
        if alias in cols:
            cat_col = cols[alias]
            break
    else:
        raise ValueError("Base não tem coluna CATÁLOGO/CATALOGO.")

    if cat_col != "CATÁLOGO":
        df = df.rename(columns={cat_col: "CATÁLOGO"})

    return df
