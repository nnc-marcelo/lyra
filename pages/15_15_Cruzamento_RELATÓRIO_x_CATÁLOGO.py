# app.py
import io
import os
import sys
import re
import unicodedata
from pathlib import Path
import pandas as pd
import streamlit as st
import zipfile
import xml.etree.ElementTree as ET
from collections import defaultdict, Counter

# Integração opcional com Reprtoir
try:
    sys.path.insert(0, str(Path(__file__).parent.parent))
    from utils.reprtoir_lookup import ReprtorirClient, lookup_obra, match_catalogo_interno
    REPRTOIR_DISPONIVEL = True
except Exception:
    REPRTOIR_DISPONIVEL = False

st.set_page_config(page_title="Cruzamento Royalties x Catálogo", layout="wide")

st.title("🎵 Cruzamento de Relatórios com Base de Catálogo")

# ---------------------------
# Caminhos Fixos
# ---------------------------
_PROJECT_ROOT = Path(__file__).parent.parent

CAMINHO_BASE_ABRAMUS = str(_PROJECT_ROOT / "data" / "mapping" / "Robo_Abramus_Base.xlsx")
CAMINHO_ABRAMUS = r"Z:\ROYALTY\Royalties Statements_Historicals\Nas Nuvens Catalog\ABRAMUS\NAS NUVENS CATALOG S.A"

CAMINHO_BASE_SONY = str(_PROJECT_ROOT / "data" / "mapping" / "Mapping_Sony.xlsx")
CAMINHO_SONY = r"Z:\ROYALTY\Royalties Statements_Historicals\Nas Nuvens Catalog\SONY MUSIC PUBLISHING"

CAMINHO_BASE_VITALE = str(_PROJECT_ROOT / "data" / "mapping" / "Lista_Obras_Catalogo_Irmaos_Vitale.xlsx")
CAMINHO_VITALE = r"Z:\ROYALTY\Royalties Statements_Historicals\Nas Nuvens Catalog\IRMAOS VITALE"

CAMINHO_BASE_INGROOVES = str(_PROJECT_ROOT / "data" / "mapping" / "mapping-artistas-ingrooves.xlsx")
CAMINHO_INGROOVES = r"Z:\ROYALTY\Royalties Statements_Historicals\Nas Nuvens Catalog\INGROOVES"

# ---------------------------
# Helpers Gerais
# ---------------------------
def read_base_xlsx(file_path: str) -> pd.DataFrame:
    """
    Lê base de catálogo em XLSX.
    """
    df = pd.read_excel(file_path, dtype=str)
    df.columns = [c.strip() for c in df.columns]
    return df

def read_mapping_sony(file_path: str) -> pd.DataFrame:
    """
    Lê a base de mapeamento Sony via XML.
    Cabeçalho está na linha 1.
    """
    with zipfile.ZipFile(file_path, 'r') as zip_ref:
        # Ler strings compartilhadas
        try:
            shared_strings_xml = zip_ref.read('xl/sharedStrings.xml')
            shared_strings_root = ET.fromstring(shared_strings_xml)
            shared_strings = []
            for si in shared_strings_root.findall('.//{http://schemas.openxmlformats.org/spreadsheetml/2006/main}t'):
                shared_strings.append(si.text if si.text else '')
        except:
            shared_strings = []
        
        # Ler planilha (sheet1.xml para Mapping_Sony)
        sheet_xml = zip_ref.read('xl/worksheets/sheet1.xml')
        sheet_root = ET.fromstring(sheet_xml)
        
        data = defaultdict(dict)
        
        for row in sheet_root.findall('.//{http://schemas.openxmlformats.org/spreadsheetml/2006/main}row'):
            row_num = int(row.get('r'))
            
            for cell in row.findall('.//{http://schemas.openxmlformats.org/spreadsheetml/2006/main}c'):
                cell_ref = cell.get('r')
                cell_type = cell.get('t')
                
                value_elem = cell.find('.//{http://schemas.openxmlformats.org/spreadsheetml/2006/main}v')
                if value_elem is not None:
                    value = value_elem.text
                    
                    if cell_type == 's' and shared_strings:
                        value = shared_strings[int(value)]
                    
                    col = ''.join([c for c in cell_ref if c.isalpha()])
                    data[row_num][col] = value
    
    # Cabeçalho na linha 1
    if 1 not in data:
        raise ValueError("Cabeçalho não encontrado na linha 1 do arquivo.")
    
    header = data[1]
    sorted_cols = sorted(header.keys())
    
    # Cria DataFrame com dados a partir da linha 2
    rows_list = []
    for row_num in range(2, max(data.keys()) + 1):
        if row_num in data:
            row_dict = {}
            for col in sorted_cols:
                col_name = header.get(col, col)
                row_dict[col_name] = data[row_num].get(col, "")
            rows_list.append(row_dict)
    
    df = pd.DataFrame(rows_list)
    return df

def normalize_catalog_column(df: pd.DataFrame) -> pd.DataFrame:
    cols = {c.upper(): c for c in df.columns}
    if "CATÁLOGO" in cols:
        cat_col = cols["CATÁLOGO"]
    elif "CATALOGO" in cols:
        cat_col = cols["CATALOGO"]
    else:
        raise ValueError("Base não tem coluna CATÁLOGO/CATALOGO.")

    if cat_col != "CATÁLOGO":
        df = df.rename(columns={cat_col: "CATÁLOGO"})

    return df


def build_lookup(df_base: pd.DataFrame, key_col: str) -> dict:
    """
    Cria um dicionário key -> catálogo (se múltiplos, junta com ' | ')
    """
    if key_col not in df_base.columns:
        return {}

    tmp = df_base[[key_col, "CATÁLOGO"]].copy()
    tmp[key_col] = tmp[key_col].astype(str).str.strip()
    tmp["CATÁLOGO"] = tmp["CATÁLOGO"].astype(str).str.strip()

    tmp = tmp.dropna(subset=[key_col, "CATÁLOGO"])
    tmp = tmp[tmp[key_col] != ""]
    tmp = tmp[tmp["CATÁLOGO"] != ""]

    grouped = (
        tmp.groupby(key_col)["CATÁLOGO"]
        .apply(lambda s: " | ".join(sorted(set(s))))
        .to_dict()
    )
    return grouped


# ---------------------------
# Helpers ABRAMUS
# ---------------------------
def read_ecad_report(source) -> pd.DataFrame:
    """
    Lê o relatório ECAD (CSV com preâmbulo) detectando automaticamente
    a linha do header e usando separador ';' e encoding ISO-8859-1.
    Aceita caminho de arquivo (str) ou objeto file-like (BytesIO).
    """
    if hasattr(source, 'read'):
        raw_bytes = source.read()
    else:
        with open(source, 'rb') as f:
            raw_bytes = f.read()
    
    text = raw_bytes.decode("ISO-8859-1", errors="replace")
    lines = text.splitlines()

    # Detecta a linha do header
    header_idx = None
    for i, line in enumerate(lines[:80]):
        if "TÍTULO DA MUSICA" in line and "CATEGORIA" in line:
            header_idx = i
            break

    if header_idx is None:
        raise ValueError("Não consegui localizar o cabeçalho da tabela no relatório.")

    df = pd.read_csv(
        io.StringIO(text),
        sep=";",
        skiprows=header_idx,
        encoding="ISO-8859-1",
        dtype=str,
    )

    df = df.loc[:, ~df.columns.str.match(r"^Unnamed")]
    df.columns = [c.strip() for c in df.columns]

    return df


def get_available_periods_abramus() -> list:
    """
    Escaneia a estrutura de pastas ABRAMUS e retorna lista de períodos disponíveis.
    Formato: [(ano, mês_num, mês_nome, caminho_completo), ...]
    """
    periods = []
    
    if not os.path.exists(CAMINHO_ABRAMUS):
        return periods
    
    # Mapeamento de mês para nome da pasta
    meses = {
        1: "Jan", 2: "Fev", 3: "Mar", 4: "Abr", 5: "Mai", 6: "Jun",
        7: "Jul", 8: "Ago", 9: "Set", 10: "Out", 11: "Nov", 12: "Dez"
    }
    
    # Percorre as pastas de ano
    for ano_folder in sorted(os.listdir(CAMINHO_ABRAMUS), reverse=True):
        ano_path = os.path.join(CAMINHO_ABRAMUS, ano_folder)
        
        if not os.path.isdir(ano_path):
            continue
        
        # Tenta extrair o ano da pasta
        try:
            ano = int(ano_folder)
        except ValueError:
            continue
        
        # Percorre as pastas de mês dentro do ano
        for mes_folder in sorted(os.listdir(ano_path)):
            mes_path = os.path.join(ano_path, mes_folder)
            
            if not os.path.isdir(mes_path):
                continue
            
            # Usa apenas o arquivo _XLS.csv
            csv_files = [f for f in os.listdir(mes_path) if f.upper().endswith('_XLS.CSV')]

            if not csv_files:
                continue

            # Extrai o número do mês da pasta
            try:
                mes_parte = mes_folder.strip().split('.')[0].strip()
                mes_num = int(mes_parte)

                if mes_num < 1 or mes_num > 12:
                    continue

                mes_nome = meses.get(mes_num, "")

            except (ValueError, IndexError):
                continue

            arquivo_csv = os.path.join(mes_path, csv_files[0])
            
            periods.append((ano, mes_num, mes_nome, arquivo_csv))
    
    return periods


# ---------------------------
# Helpers SONY
# ---------------------------
def read_excel_xml(file_path: str) -> pd.DataFrame:
    """
    Lê arquivo Excel possivelmente corrompido via XML.
    Retorna DataFrame com os dados.
    """
    with zipfile.ZipFile(file_path, 'r') as zip_ref:
        # Ler strings compartilhadas
        try:
            shared_strings_xml = zip_ref.read('xl/sharedStrings.xml')
            shared_strings_root = ET.fromstring(shared_strings_xml)
            shared_strings = []
            for si in shared_strings_root.findall('.//{http://schemas.openxmlformats.org/spreadsheetml/2006/main}t'):
                shared_strings.append(si.text if si.text else '')
        except:
            shared_strings = []
        
        # Tentar diferentes nomes de sheet
        sheet_paths = ['xl/worksheets/sheet1.xml', 'xl/worksheets/Sheet1.xml']
        sheet_xml = None
        for path in sheet_paths:
            try:
                sheet_xml = zip_ref.read(path)
                break
            except:
                continue
        
        if not sheet_xml:
            raise ValueError("Não foi possível encontrar a planilha no arquivo Excel.")
        
        sheet_root = ET.fromstring(sheet_xml)
        data = defaultdict(dict)
        
        for row in sheet_root.findall('.//{http://schemas.openxmlformats.org/spreadsheetml/2006/main}row'):
            row_num = int(row.get('r'))
            
            for cell in row.findall('.//{http://schemas.openxmlformats.org/spreadsheetml/2006/main}c'):
                cell_ref = cell.get('r')
                cell_type = cell.get('t')
                
                value_elem = cell.find('.//{http://schemas.openxmlformats.org/spreadsheetml/2006/main}v')
                if value_elem is not None:
                    value = value_elem.text
                    
                    if cell_type == 's' and shared_strings:
                        value = shared_strings[int(value)]
                    
                    col = ''.join([c for c in cell_ref if c.isalpha()])
                    data[row_num][col] = value
    
    # Converter para DataFrame
    if not data:
        return pd.DataFrame()
    
    # Identifica linha do cabeçalho (linha 10 para Sony)
    header_row = 10
    if header_row not in data:
        raise ValueError("Cabeçalho não encontrado na linha esperada (linha 10).")
    
    header = data[header_row]
    sorted_cols = sorted(header.keys())
    
    # Cria DataFrame
    rows_list = []
    for row_num in range(header_row + 1, max(data.keys()) + 1):
        if row_num in data:
            row_dict = {}
            for col in sorted_cols:
                col_name = header.get(col, col)
                row_dict[col_name] = data[row_num].get(col, "")
            rows_list.append(row_dict)
    
    df = pd.DataFrame(rows_list)
    return df


def get_available_periods_sony() -> list:
    """
    Escaneia a estrutura de pastas SONY e retorna lista de períodos disponíveis.
    Formato: [(ano, mês_num, mês_nome, caminho_completo), ...]
    """
    periods = []
    
    if not os.path.exists(CAMINHO_SONY):
        return periods
    
    meses = {
        1: "Jan", 2: "Fev", 3: "Mar", 4: "Abr", 5: "Mai", 6: "Jun",
        7: "Jul", 8: "Ago", 9: "Set", 10: "Out", 11: "Nov", 12: "Dez"
    }
    
    # Percorre as pastas de ano
    for ano_folder in sorted(os.listdir(CAMINHO_SONY), reverse=True):
        ano_path = os.path.join(CAMINHO_SONY, ano_folder)
        
        if not os.path.isdir(ano_path):
            continue
        
        try:
            ano = int(ano_folder)
        except ValueError:
            continue
        
        # Percorre as pastas de mês
        for mes_folder in sorted(os.listdir(ano_path)):
            mes_path = os.path.join(ano_path, mes_folder)
            
            if not os.path.isdir(mes_path):
                continue
            
            # Procura arquivo XLSX dentro da pasta do mês
            xlsx_files = [f for f in os.listdir(mes_path) if f.endswith('.xlsx')]
            
            if not xlsx_files:
                continue
            
            try:
                mes_parte = mes_folder.strip().split('.')[0].strip()
                mes_num = int(mes_parte)
                
                if mes_num < 1 or mes_num > 12:
                    continue
                    
                mes_nome = meses.get(mes_num, "")
                
            except (ValueError, IndexError):
                continue
            
            arquivo_xlsx = os.path.join(mes_path, xlsx_files[0])
            
            periods.append((ano, mes_num, mes_nome, arquivo_xlsx))

    return periods


# ---------------------------
# Helpers INGROOVES
# ---------------------------
def normalize_artist_text(s) -> str:
    """Normaliza nome de artista: sem acento, minúsculo, sem pontuação, espaços colapsados."""
    if not isinstance(s, str):
        return ''
    s = unicodedata.normalize('NFKD', s).encode('ASCII', 'ignore').decode('ASCII')
    s = s.lower()
    s = re.sub(r'[^\w\s]', '', s)
    return ' '.join(s.split())


def read_base_ingrooves(source) -> pd.DataFrame:
    """
    Lê a base de mapeamento de artistas Ingrooves (Artist -> Tag_Artista) e
    padroniza a coluna de catálogo para 'CATÁLOGO'.
    """
    df = pd.read_excel(source, dtype=str)
    df.columns = [c.strip() for c in df.columns]
    if "Artist" not in df.columns or "Tag_Artista" not in df.columns:
        raise ValueError(f"Base de mapeamento Ingrooves não contém as colunas necessárias (Artist, Tag_Artista). Colunas: {list(df.columns)}")
    return df.rename(columns={"Tag_Artista": "CATÁLOGO"})


def match_artist_ingrooves(artist_name, mapping_df) -> str:
    """
    Correspondência de artista Ingrooves: exata primeiro, depois por substring
    normalizada (mesma lógica usada no Ingrooves Breaker).
    """
    if not isinstance(artist_name, str) or not artist_name.strip() or mapping_df is None:
        return ""

    exact_match = mapping_df[mapping_df["Artist"] == artist_name]
    if not exact_match.empty:
        return exact_match.iloc[0]["CATÁLOGO"]

    normalized_artist = normalize_artist_text(artist_name)
    if not normalized_artist:
        return ""

    for _, row in mapping_df.iterrows():
        map_artist = row["Artist"]
        map_cat = row["CATÁLOGO"]
        if not isinstance(map_artist, str) or not isinstance(map_cat, str):
            continue
        normalized_map_artist = normalize_artist_text(map_artist)
        if normalized_map_artist and (normalized_artist in normalized_map_artist or normalized_map_artist in normalized_artist):
            return map_cat

    return ""


def read_ingrooves_dsr(source) -> pd.DataFrame:
    """Lê a aba 'Digital Sales Details' do relatório Ingrooves e remove linhas de Total."""
    df = pd.read_excel(source, sheet_name="Digital Sales Details")
    if "Sales Classification" in df.columns:
        df = df[~df["Sales Classification"].astype(str).str.contains("Total", case=False, na=False)]
    return df


def get_available_periods_ingrooves() -> list:
    """
    Escaneia a estrutura de pastas INGROOVES e retorna períodos disponíveis, usando
    apenas o arquivo DSR do label Nas_Nuvens_Catalog (ignora FAVELLE_MUSIC).
    Formato: [(ano, mês_num, mês_nome, caminho_completo), ...]
    """
    periods = []
    if not os.path.exists(CAMINHO_INGROOVES):
        return periods

    meses = {
        1: "Jan", 2: "Fev", 3: "Mar", 4: "Abr", 5: "Mai", 6: "Jun",
        7: "Jul", 8: "Ago", 9: "Set", 10: "Out", 11: "Nov", 12: "Dez"
    }

    for ano_folder in sorted(os.listdir(CAMINHO_INGROOVES), reverse=True):
        ano_path = os.path.join(CAMINHO_INGROOVES, ano_folder)
        if not os.path.isdir(ano_path):
            continue
        try:
            ano = int(ano_folder)
        except ValueError:
            continue

        for mes_folder in sorted(os.listdir(ano_path)):
            mes_path = os.path.join(ano_path, mes_folder)
            if not os.path.isdir(mes_path):
                continue

            candidatos = [
                f for f in os.listdir(mes_path)
                if f.upper().startswith("NAS_NUVENS_CATALOG") and f.upper().endswith("_DSR.XLSX")
            ]
            if not candidatos:
                continue

            try:
                mes_parte = mes_folder.strip().split('.')[0].strip()
                mes_num = int(mes_parte)
                if mes_num < 1 or mes_num > 12:
                    continue
                mes_nome = meses.get(mes_num, "")
            except (ValueError, IndexError):
                continue

            arquivo = os.path.join(mes_path, candidatos[0])
            periods.append((ano, mes_num, mes_nome, arquivo))

    return periods


# ---------------------------
# Helpers IRMÃOS VITALE
# ---------------------------
_SS_NS = "{urn:schemas-microsoft-com:office:spreadsheet}"

# Coluna de título e de valor (repasse, em R$) de cada demonstrativo
_VITALE_DEMOS = {
    "DEX":       {"titulo": "Título",         "valor": "Valor Repasse"},
    "DPV":       {"titulo": "Título",         "valor": "Valor Repasse"},
    "Terceiros": {"titulo": "Título da Obra", "valor": "Valor Repassado"},
}


def _vitale_normalize_titulo(s) -> str:
    """Normaliza título p/ cruzamento: maiúsculas, sem acento, espaços colapsados."""
    s = str(s if s is not None else "").strip().upper()
    s = unicodedata.normalize("NFKD", s)
    s = "".join(ch for ch in s if not unicodedata.combining(ch))
    s = re.sub(r"\s+", " ", s)
    return s.strip()


def read_spreadsheetml(source) -> pd.DataFrame:
    """
    Lê arquivo no formato SpreadsheetML 2003 (XML com extensão .XLS), usado pelos
    demonstrativos Irmãos Vitale. Detecta a linha do cabeçalho automaticamente
    (procura a linha com 'Ano' e 'Trimestre'). Aceita caminho (str) ou file-like.
    """
    if hasattr(source, "read"):
        root = ET.fromstring(source.read())
    else:
        root = ET.parse(source).getroot()

    ws = root.find(f".//{_SS_NS}Worksheet")
    table = ws.find(f"{_SS_NS}Table") if ws is not None else None
    if table is None:
        return pd.DataFrame()

    def parse_row(r):
        cells = {}
        col = 0
        for c in r.findall(f"{_SS_NS}Cell"):
            idx = c.get(f"{_SS_NS}Index")
            col = int(idx) if idx else col + 1
            d = c.find(f"{_SS_NS}Data")
            cells[col] = d.text if (d is not None and d.text is not None) else ""
        return cells

    parsed = [parse_row(r) for r in table.findall(f"{_SS_NS}Row")]

    header_idx = None
    for i, rc in enumerate(parsed[:20]):
        vals = {str(v).strip() for v in rc.values()}
        if "Ano" in vals and "Trimestre" in vals:
            header_idx = i
            break
    if header_idx is None:
        raise ValueError("Cabeçalho não localizado no demonstrativo (esperado 'Ano'/'Trimestre').")

    header = parsed[header_idx]
    ncol = max(header.keys()) if header else 0
    columns = [str(header.get(i, f"col{i}")).strip() for i in range(1, ncol + 1)]
    records = [[rc.get(i, "") for i in range(1, ncol + 1)] for rc in parsed[header_idx + 1:]]
    return pd.DataFrame(records, columns=columns)


def read_vitale_demonstrativo(source, tipo: str) -> pd.DataFrame:
    """
    Lê um demonstrativo Vitale e devolve formato padronizado com as colunas
    DEMONSTRATIVO, TÍTULO, VALOR (numérico, em R$). Remove linhas de subtotal
    (título vazio) — somar as linhas de detalhe reproduz exatamente os subtotais.
    """
    cfg = _VITALE_DEMOS[tipo]
    df = read_spreadsheetml(source)
    cols = ["DEMONSTRATIVO", "TÍTULO", "VALOR"]
    if df.empty:
        return pd.DataFrame(columns=cols)

    if cfg["titulo"] not in df.columns or cfg["valor"] not in df.columns:
        raise ValueError(
            f"Demonstrativo {tipo}: colunas esperadas não encontradas "
            f"('{cfg['titulo']}'/'{cfg['valor']}'). Colunas: {list(df.columns)}"
        )

    out = pd.DataFrame()
    out["TÍTULO"] = df[cfg["titulo"]].astype(str).str.strip()
    out["VALOR"] = pd.to_numeric(
        df[cfg["valor"]].astype(str).str.strip().replace("", "0"), errors="coerce"
    ).fillna(0.0)
    out["DEMONSTRATIVO"] = tipo

    out = out[(out["TÍTULO"] != "") & (out["TÍTULO"].str.lower() != "nan")]
    return out[cols]


def build_titulo_lookup(df_base: pd.DataFrame) -> dict:
    """
    Cria dicionário título_normalizado -> catálogo a partir da base Vitale
    (colunas 'Título' e 'Catálogo'). Catálogos repetidos juntam com ' | '.
    """
    cols = {c.strip().upper(): c for c in df_base.columns}
    tit_col = cols.get("TÍTULO") or cols.get("TITULO")
    cat_col = cols.get("CATÁLOGO") or cols.get("CATALOGO")
    if not tit_col or not cat_col:
        raise ValueError(f"Base não tem colunas 'Título'/'Catálogo'. Colunas: {list(df_base.columns)}")

    tmp = df_base[[tit_col, cat_col]].copy()
    tmp["__key"] = tmp[tit_col].apply(_vitale_normalize_titulo)
    tmp[cat_col] = tmp[cat_col].astype(str).str.strip()
    tmp = tmp[(tmp["__key"] != "") & (tmp[cat_col] != "") & (tmp[cat_col].str.lower() != "nan")]

    return (
        tmp.groupby("__key")[cat_col]
        .apply(lambda s: " | ".join(sorted(set(s))))
        .to_dict()
    )


def get_available_periods_vitale() -> list:
    """
    Escaneia a estrutura Vitale (ano/trimestre) e retorna períodos disponíveis.
    Para cada trimestre localiza os demonstrativos DEX/DPV/Terceiros, ignorando
    cópias e arquivos-stub bloqueados pela segurança (ex.: 85 bytes).
    Retorna: [{"ano": int, "tri": int, "label": str, "arquivos": {tipo: caminho}}, ...]
    """
    periods = []
    if not os.path.exists(CAMINHO_VITALE):
        return periods

    for ano_folder in sorted(os.listdir(CAMINHO_VITALE), reverse=True):
        ano_path = os.path.join(CAMINHO_VITALE, ano_folder)
        if not os.path.isdir(ano_path):
            continue
        try:
            ano = int(ano_folder)
        except ValueError:
            continue

        for tri_folder in sorted(os.listdir(ano_path)):
            tri_path = os.path.join(ano_path, tri_folder)
            if not os.path.isdir(tri_path):
                continue
            m = re.match(r"^\s*(\d)\s*T", tri_folder, re.IGNORECASE)
            if not m:
                continue
            tri = int(m.group(1))
            if tri < 1 or tri > 4:
                continue

            arquivos = {}
            for raiz, _dirs, files in os.walk(tri_path):
                for f in sorted(files):
                    low = f.lower()
                    if not low.endswith(".xls"):
                        continue
                    if "cop" in low:  # ignora "cópia"/"copia"/"- Copia"
                        continue
                    full = os.path.join(raiz, f)
                    try:
                        if os.path.getsize(full) < 1000:  # ignora stubs (ex.: 85 bytes)
                            continue
                    except OSError:
                        continue
                    for tipo in _VITALE_DEMOS:
                        if tipo.lower() in low and tipo not in arquivos:
                            arquivos[tipo] = full

            if arquivos:
                periods.append({
                    "ano": ano,
                    "tri": tri,
                    "label": f"{tri}T {str(ano)[2:]}",
                    "arquivos": arquivos,
                })

    return periods


# ---------------------------
# UI Principal
# ---------------------------

st.sidebar.header("⚙️ Configurações")

# Seleção de fonte
fonte = st.sidebar.selectbox(
    "Selecione a fonte de dados:",
    ["ABRAMUS", "SONY", "IRMÃOS VITALE", "INGROOVES"],
    index=0
)

st.sidebar.markdown("---")

# ---------------------------
# Lógica por Fonte
# ---------------------------

if fonte == "ABRAMUS":
    st.header("📊 ABRAMUS - Processamento de Relatórios")

    # --- Base de catálogo ---
    if os.path.exists(CAMINHO_BASE_ABRAMUS):
        base_source_abramus = CAMINHO_BASE_ABRAMUS
        st.success(f"✅ Base de catálogo carregada: `{CAMINHO_BASE_ABRAMUS}`")
    else:
        st.warning("⚠️ Base de catálogo não encontrada no caminho padrão. Faça o upload:")
        _uploaded_base_ab = st.file_uploader("Upload da base de catálogo ABRAMUS (.xlsx)", type=["xlsx"], key="base_abramus")
        if _uploaded_base_ab is None:
            st.info("Aguardando upload da base de catálogo.")
            st.stop()
        base_source_abramus = _uploaded_base_ab
        st.success("✅ Base de catálogo carregada via upload.")

    # --- Relatório ---
    periods = get_available_periods_abramus()

    if periods:
        st.subheader("Selecione o período do relatório")
        col1, col2 = st.columns(2)

        with col1:
            anos_disponiveis = sorted(list(set([p[0] for p in periods])), reverse=True)
            ano_selecionado = st.selectbox("Ano", anos_disponiveis)

        with col2:
            meses_do_ano = [p for p in periods if p[0] == ano_selecionado]
            meses_opcoes = [f"{p[1]:02d}. {p[2]} {str(p[0])[2:]}" for p in meses_do_ano]
            mes_selecionado_idx = st.selectbox("Mês", range(len(meses_opcoes)), format_func=lambda x: meses_opcoes[x])
            arquivo_selecionado = meses_do_ano[mes_selecionado_idx][3]

        mes_num_selecionado = meses_do_ano[mes_selecionado_idx][1]
        st.info(f"📁 Arquivo selecionado:\n`{arquivo_selecionado}`")
        report_source_abramus = arquivo_selecionado
    else:
        st.warning("⚠️ Relatórios ABRAMUS não encontrados na rede. Faça o upload do arquivo:")
        _uploaded_report_ab = st.file_uploader("Upload do relatório ABRAMUS (_XLS.CSV)", type=["csv"], key="report_abramus")
        if _uploaded_report_ab is None:
            st.info("Aguardando upload do relatório.")
            st.stop()
        st.success(f"✅ Arquivo `{_uploaded_report_ab.name}` carregado.")
        report_source_abramus = _uploaded_report_ab
        ano_selecionado = 0
        mes_num_selecionado = 0

    # Botão para processar
    if st.button("🚀 Processar Cruzamento", type="primary"):
        try:
            with st.spinner("Carregando base de catálogo..."):
                df_base = read_base_xlsx(base_source_abramus)
                df_base = normalize_catalog_column(df_base)

            with st.spinner("Carregando relatório ABRAMUS..."):
                df_report = read_ecad_report(report_source_abramus)

            # Verifica colunas-chave
            if "CÓD. OBRA" not in df_base.columns:
                st.warning("Base não contém coluna 'CÓD. OBRA' (necessária para categoria E).")
            if "CÓD FONOGRAMA" not in df_base.columns:
                st.warning("Base não contém coluna 'CÓD FONOGRAMA' (necessária para categorias não-E).")

            # Lookups
            obra_lookup = build_lookup(df_base, "CÓD. OBRA")
            fono_lookup = build_lookup(df_base, "CÓD FONOGRAMA")

            # Normaliza campos do relatório
            for c in ["CÓD. OBRA", "CÓD FONOGRAMA", "CATEGORIA"]:
                if c in df_report.columns:
                    df_report[c] = df_report[c].astype(str).str.strip()

            # Aplica regra: E -> obra, senão -> fonograma
            def resolve_catalog(row):
                cat = (row.get("CATEGORIA") or "").strip().upper()
                if cat == "E":
                    key = (row.get("CÓD. OBRA") or "").strip()
                    return obra_lookup.get(key, "")
                else:
                    key = (row.get("CÓD FONOGRAMA") or "").strip()
                    return fono_lookup.get(key, "")

            df_out = df_report.copy()
            df_out["CATÁLOGO"] = df_out.apply(resolve_catalog, axis=1)

            st.subheader("Resultado Agrupado por Catálogo")
            
            if "RATEIO" in df_out.columns:
                df_display = df_out[["CATÁLOGO", "RATEIO"]].copy()
                df_display["RATEIO"] = df_display["RATEIO"].astype(str).str.replace(",", ".", regex=False)
                df_display["RATEIO"] = pd.to_numeric(df_display["RATEIO"], errors="coerce")
                
                # Agrupa por catálogo e soma
                df_grouped = df_display.groupby("CATÁLOGO", as_index=False)["RATEIO"].sum()
                df_grouped = df_grouped.sort_values("RATEIO", ascending=False)
                
                st.dataframe(df_grouped, use_container_width=True, height=520)
                
                total_rateio = df_grouped["RATEIO"].sum()
                st.markdown(f"**Total RATEIO: R$ {total_rateio:,.2f}**")
                
                # Download resultado agrupado
                csv_bytes = df_grouped.to_csv(index=False, sep=";", encoding="utf-8-sig", decimal=",").encode("utf-8-sig")
                st.download_button(
                    "⬇️ Baixar resultado agrupado (CSV)",
                    data=csv_bytes,
                    file_name=f"relatorio_agrupado_abramus_{ano_selecionado}_{mes_num_selecionado:02d}.csv",
                    mime="text/csv",
                )
                
                # --- NOVO: Download resultado DETALHADO ---
                st.markdown("---")
                st.subheader("📋 Download com Detalhes das Obras")

                # Prepara dados detalhados
                df_detalhado = df_out.copy()

                # Define colunas para o relatório detalhado
                colunas_detalhadas = [
                    "CATÁLOGO", "TÍTULO DA MUSICA", "CÓD. OBRA", "CÓD FONOGRAMA", 
                    "ISWC", "AUTORES", "CATEGORIA", "RATEIO"
                ]
                colunas_detalhadas_disp = [col for col in colunas_detalhadas if col in df_detalhado.columns]

                df_detalhado_export = df_detalhado[colunas_detalhadas_disp].copy()

                # Ordena por catálogo e rateio
                if "RATEIO" in df_detalhado_export.columns:
                    df_detalhado_export["RATEIO_SORT"] = df_detalhado_export["RATEIO"].astype(str).str.replace(",", ".", regex=False)
                    df_detalhado_export["RATEIO_SORT"] = pd.to_numeric(df_detalhado_export["RATEIO_SORT"], errors="coerce")
                    df_detalhado_export = df_detalhado_export.sort_values(["CATÁLOGO", "RATEIO_SORT"], ascending=[True, False])
                    df_detalhado_export = df_detalhado_export.drop(columns=["RATEIO_SORT"])

                # Estatísticas do detalhado
                total_obras = len(df_detalhado_export)
                obras_mapeadas = len(df_detalhado_export[df_detalhado_export["CATÁLOGO"].notna() & (df_detalhado_export["CATÁLOGO"] != "")])
                obras_nao_mapeadas = total_obras - obras_mapeadas

                col_info1, col_info2, col_info3 = st.columns(3)
                with col_info1:
                    st.metric("📊 Total de Obras", total_obras)
                with col_info2:
                    st.metric("✅ Mapeadas", obras_mapeadas)
                with col_info3:
                    st.metric("❌ Não Mapeadas", obras_nao_mapeadas)

                # Preview do detalhado
                st.dataframe(df_detalhado_export.head(50), use_container_width=True, height=300)

                # Download detalhado
                csv_detalhado = df_detalhado_export.to_csv(index=False, sep=";", encoding="utf-8-sig", decimal=",").encode("utf-8-sig")
                st.download_button(
                    "⬇️ Baixar relatório DETALHADO com todas as obras (CSV)",
                    data=csv_detalhado,
                    file_name=f"relatorio_detalhado_abramus_{ano_selecionado}_{mes_num_selecionado:02d}.csv",
                    mime="text/csv",
                    type="primary"
                )
                
                # --- SEÇÃO DE OBRAS NÃO MAPEADAS ---
                st.markdown("---")
                st.subheader("🔍 Obras Não Mapeadas")
                
                df_nao_mapeadas = df_out[df_out["CATÁLOGO"].isin(["", "nan"]) | df_out["CATÁLOGO"].isna()].copy()
                
                if len(df_nao_mapeadas) > 0:
                    df_nao_mapeadas["RATEIO_NUM"] = df_nao_mapeadas["RATEIO"].astype(str).str.replace(",", ".", regex=False)
                    df_nao_mapeadas["RATEIO_NUM"] = pd.to_numeric(df_nao_mapeadas["RATEIO_NUM"], errors="coerce")
                    
                    def get_chave_agrupamento(row):
                        cat = str(row.get("CATEGORIA", "")).strip().upper()
                        if cat == "E":
                            return str(row.get("CÓD. OBRA", "")).strip()
                        else:
                            return str(row.get("CÓD FONOGRAMA", "")).strip()
                    
                    df_nao_mapeadas["CHAVE_GRUPO"] = df_nao_mapeadas.apply(get_chave_agrupamento, axis=1)
                    
                    colunas_primeiro = ["TÍTULO DA MUSICA", "CÓD. OBRA", "CÓD FONOGRAMA", "ISWC", "AUTORES", "CATEGORIA"]
                    colunas_primeiro_disp = [col for col in colunas_primeiro if col in df_nao_mapeadas.columns]
                    
                    agg_dict = {col: 'first' for col in colunas_primeiro_disp}
                    agg_dict["RATEIO_NUM"] = "sum"
                    
                    df_agrupado = df_nao_mapeadas.groupby("CHAVE_GRUPO", as_index=False).agg(agg_dict)
                    df_agrupado = df_agrupado[df_agrupado["CHAVE_GRUPO"] != ""]
                    
                    total_nao_mapeado = df_agrupado["RATEIO_NUM"].sum()
                    
                    st.warning(f"⚠️ **{len(df_agrupado)} obras únicas** não foram mapeadas | **Total: R$ {total_nao_mapeado:,.2f}**")
                    
                    df_agrupado = df_agrupado.sort_values("RATEIO_NUM", ascending=False)
                    
                    colunas_exibir = ["TÍTULO DA MUSICA", "CÓD. OBRA", "CÓD FONOGRAMA", "ISWC", "AUTORES", "CATEGORIA", "RATEIO_NUM"]
                    colunas_exibir_disp = [col for col in colunas_exibir if col in df_agrupado.columns]
                    
                    df_preview = df_agrupado[colunas_exibir_disp].copy()
                    df_preview = df_preview.rename(columns={"RATEIO_NUM": "RATEIO"})
                    
                    st.dataframe(df_preview.head(50), use_container_width=True, height=300)
                    
                    csv_nao_mapeadas = df_preview.to_csv(index=False, sep=";", encoding="utf-8-sig", decimal=",").encode("utf-8-sig")
                    st.download_button(
                        "⬇️ Baixar obras não mapeadas (CSV)",
                        data=csv_nao_mapeadas,
                        file_name=f"obras_nao_mapeadas_abramus_{ano_selecionado}_{mes_num_selecionado:02d}.csv",
                        mime="text/csv",
                        type="secondary"
                    )
                    
                    if "CATEGORIA" in df_agrupado.columns:
                        st.markdown("**Distribuição por Categoria:**")
                        cat_stats = df_agrupado.groupby("CATEGORIA").agg({
                            "RATEIO_NUM": ["count", "sum"]
                        }).round(2)
                        cat_stats.columns = ["Quantidade", "Total Rateio"]
                        st.dataframe(cat_stats, use_container_width=True)
                    
                    # --- SEÇÃO DE SUGESTÕES INTELIGENTES ---
                    st.markdown("---")
                    st.subheader("🤖 Sugestões Inteligentes de Catálogo")
                    
                    if "AUTORES" in df_nao_mapeadas.columns:
                        st.info("Analisando padrões de autores na base de catálogo...")
                        
                        autor_catalogo_map = {}
                        
                        if "AUTORES" in df_base.columns:
                            for idx, row in df_base.iterrows():
                                catalogo = str(row.get("CATÁLOGO", "")).strip()
                                autores_str = str(row.get("AUTORES", "")).strip()
                                
                                if catalogo and autores_str and catalogo != "nan" and autores_str != "nan":
                                    autores_list = [a.strip().upper() for a in autores_str.split("/")]
                                    
                                    for autor in autores_list:
                                        if autor and len(autor) > 2:
                                            if autor not in autor_catalogo_map:
                                                autor_catalogo_map[autor] = {}
                                            
                                            if catalogo not in autor_catalogo_map[autor]:
                                                autor_catalogo_map[autor][catalogo] = 0
                                            autor_catalogo_map[autor][catalogo] += 1
                            
                            st.success(f"✅ Dicionário criado: {len(autor_catalogo_map)} autores mapeados")
                            
                            def sugerir_catalogo(autores_str):
                                if not autores_str or autores_str == "nan":
                                    return "", 0, ""
                                
                                autores_list = [a.strip().upper() for a in str(autores_str).split("/")]
                                sugestoes = {}
                                autores_encontrados = []
                                
                                for autor in autores_list:
                                    if autor in autor_catalogo_map:
                                        autores_encontrados.append(autor)
                                        for catalogo, freq in autor_catalogo_map[autor].items():
                                            if catalogo not in sugestoes:
                                                sugestoes[catalogo] = 0
                                            sugestoes[catalogo] += freq
                                
                                if not sugestoes:
                                    return "", 0, ""
                                
                                melhor_catalogo = max(sugestoes, key=sugestoes.get)
                                score = sugestoes[melhor_catalogo]
                                confianca = len(autores_encontrados) / len(autores_list) * 100
                                
                                return melhor_catalogo, confianca, " / ".join(autores_encontrados)
                            
                            df_agrupado["CATÁLOGO_SUGERIDO"] = ""
                            df_agrupado["CONFIANÇA_%"] = 0.0
                            df_agrupado["AUTORES_MATCH"] = ""
                            
                            for idx in df_agrupado.index:
                                autores = df_agrupado.loc[idx, "AUTORES"] if "AUTORES" in df_agrupado.columns else ""
                                catalogo_sug, conf, autores_match = sugerir_catalogo(autores)
                                df_agrupado.loc[idx, "CATÁLOGO_SUGERIDO"] = catalogo_sug
                                df_agrupado.loc[idx, "CONFIANÇA_%"] = conf
                                df_agrupado.loc[idx, "AUTORES_MATCH"] = autores_match
                            
                            df_com_sugestao = df_agrupado[df_agrupado["CATÁLOGO_SUGERIDO"] != ""].copy()
                            df_sem_sugestao = df_agrupado[df_agrupado["CATÁLOGO_SUGERIDO"] == ""].copy()
                            
                            col_stat1, col_stat2 = st.columns(2)
                            with col_stat1:
                                st.metric("✨ Com Sugestão", len(df_com_sugestao))
                            with col_stat2:
                                st.metric("❓ Sem Sugestão", len(df_sem_sugestao))
                            
                            if len(df_com_sugestao) > 0:
                                df_com_sugestao = df_com_sugestao.sort_values("CONFIANÇA_%", ascending=False)
                                
                                st.success(f"✨ **{len(df_com_sugestao)} obras** com sugestões encontradas!")
                                
                                colunas_sugestao = [
                                    "TÍTULO DA MUSICA", "AUTORES", "CÓD. OBRA", "CÓD FONOGRAMA", "ISWC", "CATÁLOGO_SUGERIDO", "AUTORES_MATCH", 
                                    "CONFIANÇA_%", 
                                    "CATEGORIA", "RATEIO_NUM"
                                ]
                                colunas_disp_sug = [col for col in colunas_sugestao if col in df_com_sugestao.columns]
                                
                                df_preview_sug = df_com_sugestao[colunas_disp_sug].copy()
                                
                                df_preview_sug["CONFIANÇA_%"] = df_preview_sug["CONFIANÇA_%"].round(0).astype(int)
                                if "RATEIO_NUM" in df_preview_sug.columns:
                                    df_preview_sug = df_preview_sug.rename(columns={"RATEIO_NUM": "RATEIO"})
                                
                                st.dataframe(df_preview_sug.head(100), use_container_width=True, height=400)
                                
                                st.markdown("**Distribuição de Sugestões:**")
                                
                                rateio_col = "RATEIO" if "RATEIO" in df_com_sugestao.columns else "RATEIO_NUM"
                                
                                sug_stats = df_com_sugestao.groupby("CATÁLOGO_SUGERIDO").agg({
                                    rateio_col: ["count", "sum"],
                                    "CONFIANÇA_%": "mean"
                                }).round(2)
                                sug_stats.columns = ["Quantidade", "Total Rateio", "Confiança Média %"]
                                sug_stats = sug_stats.sort_values("Quantidade", ascending=False)
                                st.dataframe(sug_stats, use_container_width=True)
                            
                            st.markdown("---")
                            st.markdown("### 📥 Download Completo")
                            
                            colunas_download = [
                                "TÍTULO DA MUSICA", "AUTORES", "CÓD. OBRA", "CÓD FONOGRAMA", "ISWC", "CATÁLOGO_SUGERIDO", "AUTORES_MATCH", 
                                "CONFIANÇA_%", 
                                "CATEGORIA", "RATEIO_NUM"
                            ]
                            colunas_download_disp = [col for col in colunas_download if col in df_agrupado.columns]
                            
                            df_download_completo = df_agrupado[colunas_download_disp].copy()
                            
                            df_download_completo["CONFIANÇA_%"] = df_download_completo["CONFIANÇA_%"].round(0).astype(int)
                            
                            if "RATEIO_NUM" in df_download_completo.columns:
                                df_download_completo = df_download_completo.rename(columns={"RATEIO_NUM": "RATEIO"})
                            
                            df_download_completo = df_download_completo.sort_values(
                                ["CONFIANÇA_%", "RATEIO" if "RATEIO" in df_download_completo.columns else "RATEIO_NUM"], 
                                ascending=[False, False]
                            )
                            
                            csv_completo = df_download_completo.to_csv(index=False, sep=";", encoding="utf-8-sig", decimal=",").encode("utf-8-sig")
                            
                            st.info(f"📊 Este arquivo contém **{len(df_download_completo)} obras** ({len(df_com_sugestao)} com sugestão + {len(df_sem_sugestao)} sem sugestão)")
                            
                            st.download_button(
                                "⬇️ Baixar TODAS as obras não mapeadas (com e sem sugestões)",
                                data=csv_completo,
                                file_name=f"obras_completo_abramus_{ano_selecionado}_{mes_num_selecionado:02d}.csv",
                                mime="text/csv",
                                type="primary"
                            )
                        
                        else:
                            st.warning("⚠️ Coluna 'AUTORES' não encontrada na base de catálogo.")

                    # --- SEÇÃO REPRTOIR (ABRAMUS) ---
                    st.markdown("---")
                    st.subheader("🔎 Buscar no Reprtoir")
                    if not REPRTOIR_DISPONIVEL:
                        st.info("ℹ️ Integração com Reprtoir não disponível. Verifique o arquivo `.env` com `REPRTOIR_API_KEY`.")
                    else:
                        st.caption("Consulta a API do Reprtoir para identificar obras não mapeadas via ISWC ou título+autores.")
                        _rep_key_ab = f"reprtoir_abramus_{ano_selecionado}_{mes_num_selecionado:02d}"
                        if st.button("🔎 Buscar no Reprtoir", key="btn_reprtoir_abramus"):
                            try:
                                _client_rep = ReprtorirClient()
                                _cats_internos = sorted(df_base["CATÁLOGO"].dropna().astype(str).unique().tolist()) if "CATÁLOGO" in df_base.columns else []
                                _resultados_rep = []
                                _progress_rep = st.progress(0)
                                _total_rep = len(df_agrupado)
                                for _i_rep, (_, _row_rep) in enumerate(df_agrupado.iterrows()):
                                    _progress_rep.progress((_i_rep + 1) / max(_total_rep, 1))
                                    _iswc = str(_row_rep.get("ISWC", "")).strip()
                                    _titulo = str(_row_rep.get("TÍTULO DA MUSICA", "")).strip()
                                    _autores = [a.strip() for a in str(_row_rep.get("AUTORES", "")).split("/") if a.strip()]
                                    _obra_rep = lookup_obra(_client_rep, _iswc, _titulo, _autores)
                                    if _obra_rep:
                                        _cat_rep = (_obra_rep.get("catalog") or {}).get("name", "")
                                        _cat_int, _score_rep = match_catalogo_interno(_cat_rep, _cats_internos)
                                        _resultados_rep.append({
                                            "CHAVE_GRUPO": _row_rep["CHAVE_GRUPO"],
                                            "CATÁLOGO_REPRTOIR": _cat_rep,
                                            "CATÁLOGO_INTERNO_SUGERIDO": _cat_int,
                                            "CONFIANÇA_REPRTOIR_%": _score_rep,
                                            "FONTE_REPRTOIR": _obra_rep.get("_fonte", ""),
                                        })
                                _progress_rep.empty()
                                st.session_state[_rep_key_ab] = _resultados_rep
                            except Exception as _e_rep:
                                st.error(f"❌ Erro ao consultar Reprtoir: {_e_rep}")

                        if st.session_state.get(_rep_key_ab):
                            _df_rep = pd.DataFrame(st.session_state[_rep_key_ab])
                            _df_com_rep = df_agrupado.merge(_df_rep, on="CHAVE_GRUPO", how="inner")
                            st.success(f"✅ **{len(_df_com_rep)} obras** identificadas pelo Reprtoir!")
                            _cols_rep = ["TÍTULO DA MUSICA", "ISWC", "AUTORES", "CATÁLOGO_REPRTOIR", "CATÁLOGO_INTERNO_SUGERIDO", "CONFIANÇA_REPRTOIR_%", "FONTE_REPRTOIR", "RATEIO_NUM"]
                            _cols_rep_disp = [c for c in _cols_rep if c in _df_com_rep.columns]
                            st.dataframe(_df_com_rep[_cols_rep_disp].sort_values("CONFIANÇA_REPRTOIR_%", ascending=False).head(100), use_container_width=True, height=400)
                            _csv_rep = _df_com_rep[_cols_rep_disp].to_csv(index=False, sep=";", encoding="utf-8-sig", decimal=",").encode("utf-8-sig")
                            st.download_button("⬇️ Baixar resultados Reprtoir (CSV)", data=_csv_rep, file_name=f"reprtoir_abramus_{ano_selecionado}_{mes_num_selecionado:02d}.csv", mime="text/csv", key="dl_reprtoir_abramus")

                else:
                    st.success("✅ Todas as obras foram mapeadas com sucesso!")
                
            else:
                st.warning("Coluna 'RATEIO' não encontrada no relatório.")
                st.dataframe(df_out, use_container_width=True, height=520)

            st.success("✅ Processamento concluído!")

        except Exception as e:
            st.error(f"❌ Erro ao processar: {e}")
            import traceback
            st.code(traceback.format_exc())

# ---------------------------
# SONY
# ---------------------------
elif fonte == "SONY":
    st.header("🎵 SONY MUSIC PUBLISHING - Processamento de Relatórios")

    # --- Base de mapeamento ---
    if os.path.exists(CAMINHO_BASE_SONY):
        base_source_sony = CAMINHO_BASE_SONY
        st.success(f"✅ Base de mapeamento carregada: `{CAMINHO_BASE_SONY}`")
    else:
        st.warning("⚠️ Base de mapeamento não encontrada no caminho padrão. Faça o upload:")
        _uploaded_base_so = st.file_uploader("Upload da base de mapeamento Sony (.xlsx)", type=["xlsx"], key="base_sony")
        if _uploaded_base_so is None:
            st.info("Aguardando upload da base de mapeamento.")
            st.stop()
        base_source_sony = _uploaded_base_so
        st.success("✅ Base de mapeamento carregada via upload.")

    # --- Relatório ---
    periods = get_available_periods_sony()

    if periods:
        st.subheader("Selecione o período do relatório")
        col1, col2 = st.columns(2)

        with col1:
            anos_disponiveis = sorted(list(set([p[0] for p in periods])), reverse=True)
            ano_selecionado = st.selectbox("Ano", anos_disponiveis)

        with col2:
            meses_do_ano = [p for p in periods if p[0] == ano_selecionado]
            meses_opcoes = [f"{p[1]:02d}. {p[2]} {str(p[0])[2:]}" for p in meses_do_ano]
            mes_selecionado_idx = st.selectbox("Mês", range(len(meses_opcoes)), format_func=lambda x: meses_opcoes[x])
            arquivo_selecionado = meses_do_ano[mes_selecionado_idx][3]

        mes_num_selecionado = meses_do_ano[mes_selecionado_idx][1]
        st.info(f"📁 Arquivo selecionado:\n`{arquivo_selecionado}`")
        report_source_sony = arquivo_selecionado
    else:
        st.warning("⚠️ Relatórios SONY não encontrados na rede. Faça o upload do arquivo:")
        _uploaded_report_so = st.file_uploader("Upload do relatório SONY (.xlsx)", type=["xlsx"], key="report_sony")
        if _uploaded_report_so is None:
            st.info("Aguardando upload do relatório.")
            st.stop()
        st.success(f"✅ Arquivo `{_uploaded_report_so.name}` carregado.")
        report_source_sony = _uploaded_report_so
        ano_selecionado = 0
        mes_num_selecionado = 0

    # Botão para processar
    if st.button("🚀 Processar Cruzamento", type="primary"):
        try:
            with st.spinner("Carregando base de mapeamento Sony..."):
                df_base_sony = read_mapping_sony(base_source_sony)

                # Renomeia Catalogo -> CATÁLOGO (padronização)
                if "Catalogo" in df_base_sony.columns:
                    df_base_sony = df_base_sony.rename(columns={"Catalogo": "CATÁLOGO"})

                # Verifica colunas necessárias
                if "Song No." not in df_base_sony.columns or "CATÁLOGO" not in df_base_sony.columns:
                    st.error(f"❌ Base de mapeamento não contém as colunas necessárias")
                    st.error(f"Colunas encontradas: {list(df_base_sony.columns)}")
                    st.stop()

            with st.spinner("Carregando relatório Sony..."):
                df_report = read_excel_xml(report_source_sony)
                
                if "Song No." not in df_report.columns:
                    st.error("❌ Relatório não contém a coluna 'Song No.'")
                    st.error(f"Colunas encontradas: {list(df_report.columns)}")
                    st.stop()

            # Cria lookup Song No. -> Catálogo
            song_lookup = build_lookup(df_base_sony, "Song No.")
            
            st.info(f"📚 Lookup criado: {len(song_lookup)} músicas mapeadas")

            # Normaliza Song No. no relatório
            df_report["Song No."] = df_report["Song No."].astype(str).str.strip()

            # Aplica mapeamento
            df_out = df_report.copy()
            df_out["CATÁLOGO"] = df_out["Song No."].map(song_lookup).fillna("")

            st.subheader("Resultado Agrupado por Catálogo")
            
            if "RoyAmt" in df_out.columns:
                df_display = df_out[["CATÁLOGO", "RoyAmt"]].copy()
                df_display["RoyAmt"] = pd.to_numeric(df_display["RoyAmt"], errors="coerce")
                
                # Agrupa por catálogo e soma
                df_grouped = df_display.groupby("CATÁLOGO", as_index=False)["RoyAmt"].sum()
                df_grouped = df_grouped.sort_values("RoyAmt", ascending=False)
                df_grouped = df_grouped.rename(columns={"RoyAmt": "Royalties"})
                
                st.dataframe(df_grouped, use_container_width=True, height=520)
                
                total_roy = df_grouped["Royalties"].sum()
                st.markdown(f"**Total Royalties: ${total_roy:,.2f}**")
                
                # Download resultado agrupado
                csv_bytes = df_grouped.to_csv(index=False, sep=";", encoding="utf-8-sig", decimal=",").encode("utf-8-sig")
                st.download_button(
                    "⬇️ Baixar resultado agrupado (CSV)",
                    data=csv_bytes,
                    file_name=f"relatorio_agrupado_sony_{ano_selecionado}_{mes_num_selecionado:02d}.csv",
                    mime="text/csv",
                )
                
                # --- NOVO: Download resultado DETALHADO ---
                st.markdown("---")
                st.subheader("📋 Download com Detalhes das Músicas")

                # Prepara dados detalhados
                df_detalhado = df_out.copy()

                # Define colunas para o relatório detalhado
                colunas_detalhadas = [
                    "CATÁLOGO", "Song No.", "Song", "Writer", 
                    "Source", "Inc Typ", "RoyAmt"
                ]
                colunas_detalhadas_disp = [col for col in colunas_detalhadas if col in df_detalhado.columns]

                df_detalhado_export = df_detalhado[colunas_detalhadas_disp].copy()

                # Ordena por catálogo e royalties
                if "RoyAmt" in df_detalhado_export.columns:
                    df_detalhado_export["RoyAmt_SORT"] = pd.to_numeric(df_detalhado_export["RoyAmt"], errors="coerce")
                    df_detalhado_export = df_detalhado_export.sort_values(["CATÁLOGO", "RoyAmt_SORT"], ascending=[True, False])
                    df_detalhado_export = df_detalhado_export.drop(columns=["RoyAmt_SORT"])

                # Estatísticas do detalhado
                total_musicas = len(df_detalhado_export)
                musicas_mapeadas = len(df_detalhado_export[df_detalhado_export["CATÁLOGO"].notna() & (df_detalhado_export["CATÁLOGO"] != "")])
                musicas_nao_mapeadas = total_musicas - musicas_mapeadas

                col_info1, col_info2, col_info3 = st.columns(3)
                with col_info1:
                    st.metric("📊 Total de Registros", total_musicas)
                with col_info2:
                    st.metric("✅ Mapeados", musicas_mapeadas)
                with col_info3:
                    st.metric("❌ Não Mapeados", musicas_nao_mapeadas)

                # Preview do detalhado
                st.dataframe(df_detalhado_export.head(50), use_container_width=True, height=300)

                # Download detalhado
                csv_detalhado = df_detalhado_export.to_csv(index=False, sep=";", encoding="utf-8-sig", decimal=",").encode("utf-8-sig")
                st.download_button(
                    "⬇️ Baixar relatório DETALHADO com todas as músicas (CSV)",
                    data=csv_detalhado,
                    file_name=f"relatorio_detalhado_sony_{ano_selecionado}_{mes_num_selecionado:02d}.csv",
                    mime="text/csv",
                    type="primary"
                )
                
                # --- SEÇÃO DE OBRAS NÃO MAPEADAS ---
                st.markdown("---")
                st.subheader("🔍 Músicas Não Mapeadas")
                
                df_nao_mapeadas = df_out[df_out["CATÁLOGO"].isin(["", "nan"]) | df_out["CATÁLOGO"].isna()].copy()
                
                if len(df_nao_mapeadas) > 0:
                    df_nao_mapeadas["RoyAmt_NUM"] = pd.to_numeric(df_nao_mapeadas["RoyAmt"], errors="coerce")
                    
                    # Agrupa por Song No.
                    colunas_primeiro = ["Song", "Writer", "Source", "Inc Typ"]
                    colunas_primeiro_disp = [col for col in colunas_primeiro if col in df_nao_mapeadas.columns]
                    
                    agg_dict = {col: 'first' for col in colunas_primeiro_disp}
                    agg_dict["RoyAmt_NUM"] = "sum"
                    
                    df_agrupado = df_nao_mapeadas.groupby("Song No.", as_index=False).agg(agg_dict)
                    
                    total_nao_mapeado = df_agrupado["RoyAmt_NUM"].sum()
                    
                    st.warning(f"⚠️ **{len(df_agrupado)} músicas únicas** não foram mapeadas | **Total: ${total_nao_mapeado:,.2f}**")
                    
                    df_agrupado = df_agrupado.sort_values("RoyAmt_NUM", ascending=False)
                    
                    colunas_exibir = ["Song No.", "Song", "Writer", "Source", "Inc Typ", "RoyAmt_NUM"]
                    colunas_exibir_disp = [col for col in colunas_exibir if col in df_agrupado.columns]
                    
                    df_preview = df_agrupado[colunas_exibir_disp].copy()
                    df_preview = df_preview.rename(columns={"RoyAmt_NUM": "Royalties"})
                    
                    st.dataframe(df_preview.head(50), use_container_width=True, height=300)
                    
                    csv_nao_mapeadas = df_preview.to_csv(index=False, sep=";", encoding="utf-8-sig", decimal=",").encode("utf-8-sig")
                    st.download_button(
                        "⬇️ Baixar músicas não mapeadas (CSV)",
                        data=csv_nao_mapeadas,
                        file_name=f"obras_nao_mapeadas_sony_{ano_selecionado}_{mes_num_selecionado:02d}.csv",
                        mime="text/csv",
                        type="secondary"
                    )
                    
                    # Estatísticas por Source
                    if "Source" in df_agrupado.columns:
                        st.markdown("**Distribuição por Source:**")
                        source_stats = df_agrupado.groupby("Source").agg({
                            "RoyAmt_NUM": ["count", "sum"]
                        }).round(2)
                        source_stats.columns = ["Quantidade", "Total Royalties"]
                        st.dataframe(source_stats, use_container_width=True)
                    
                    # --- SEÇÃO DE SUGESTÕES INTELIGENTES ---
                    st.markdown("---")
                    st.subheader("🤖 Sugestões Inteligentes de Catálogo")
                    
                    if "Writer" in df_nao_mapeadas.columns:
                        st.info("Analisando padrões de autores na base de mapeamento...")
                        
                        autor_catalogo_map = {}
                        
                        if "Writer" in df_base_sony.columns:
                            for idx, row in df_base_sony.iterrows():
                                catalogo = str(row.get("CATÁLOGO", "")).strip()
                                writers_str = str(row.get("Writer", "")).strip()
                                
                                if catalogo and writers_str and catalogo != "nan" and writers_str != "nan":
                                    # Separa por ; e depois por , para pegar autores individuais
                                    writers_list = []
                                    for part in writers_str.split(";"):
                                        for writer in part.split(","):
                                            writer_clean = writer.strip().upper()
                                            # Remove "NC:" prefix
                                            writer_clean = writer_clean.replace("NC:", "").strip()
                                            if writer_clean:
                                                writers_list.append(writer_clean)
                                    
                                    for writer in writers_list:
                                        if writer and len(writer) > 2:
                                            if writer not in autor_catalogo_map:
                                                autor_catalogo_map[writer] = {}
                                            
                                            if catalogo not in autor_catalogo_map[writer]:
                                                autor_catalogo_map[writer][catalogo] = 0
                                            autor_catalogo_map[writer][catalogo] += 1
                            
                            st.success(f"✅ Dicionário criado: {len(autor_catalogo_map)} autores mapeados")
                            
                            def sugerir_catalogo(writers_str):
                                if not writers_str or writers_str == "nan":
                                    return "", 0, ""
                                
                                writers_list = []
                                for part in str(writers_str).split(";"):
                                    for writer in part.split(","):
                                        writer_clean = writer.strip().upper()
                                        writer_clean = writer_clean.replace("NC:", "").strip()
                                        if writer_clean:
                                            writers_list.append(writer_clean)
                                
                                sugestoes = {}
                                autores_encontrados = []
                                
                                for writer in writers_list:
                                    if writer in autor_catalogo_map:
                                        autores_encontrados.append(writer)
                                        for catalogo, freq in autor_catalogo_map[writer].items():
                                            if catalogo not in sugestoes:
                                                sugestoes[catalogo] = 0
                                            sugestoes[catalogo] += freq
                                
                                if not sugestoes:
                                    return "", 0, ""
                                
                                melhor_catalogo = max(sugestoes, key=sugestoes.get)
                                score = sugestoes[melhor_catalogo]
                                confianca = len(autores_encontrados) / len(writers_list) * 100 if writers_list else 0
                                
                                return melhor_catalogo, confianca, " / ".join(autores_encontrados[:3])  # Limita a 3 nomes
                            
                            df_agrupado["CATÁLOGO_SUGERIDO"] = ""
                            df_agrupado["CONFIANÇA_%"] = 0.0
                            df_agrupado["AUTORES_MATCH"] = ""
                            
                            for idx in df_agrupado.index:
                                writers = df_agrupado.loc[idx, "Writer"] if "Writer" in df_agrupado.columns else ""
                                catalogo_sug, conf, autores_match = sugerir_catalogo(writers)
                                df_agrupado.loc[idx, "CATÁLOGO_SUGERIDO"] = catalogo_sug
                                df_agrupado.loc[idx, "CONFIANÇA_%"] = conf
                                df_agrupado.loc[idx, "AUTORES_MATCH"] = autores_match
                            
                            df_com_sugestao = df_agrupado[df_agrupado["CATÁLOGO_SUGERIDO"] != ""].copy()
                            df_sem_sugestao = df_agrupado[df_agrupado["CATÁLOGO_SUGERIDO"] == ""].copy()
                            
                            col_stat1, col_stat2 = st.columns(2)
                            with col_stat1:
                                st.metric("✨ Com Sugestão", len(df_com_sugestao))
                            with col_stat2:
                                st.metric("❓ Sem Sugestão", len(df_sem_sugestao))
                            
                            if len(df_com_sugestao) > 0:
                                df_com_sugestao = df_com_sugestao.sort_values("CONFIANÇA_%", ascending=False)
                                
                                st.success(f"✨ **{len(df_com_sugestao)} músicas** com sugestões encontradas!")
                                
                                colunas_sugestao = [
                                    "Song No.", "Song", "Writer", "CATÁLOGO_SUGERIDO", "AUTORES_MATCH", 
                                    "CONFIANÇA_%", 
                                    "Source", "Inc Typ", "RoyAmt_NUM"
                                ]
                                colunas_disp_sug = [col for col in colunas_sugestao if col in df_com_sugestao.columns]
                                
                                df_preview_sug = df_com_sugestao[colunas_disp_sug].copy()
                                
                                df_preview_sug["CONFIANÇA_%"] = df_preview_sug["CONFIANÇA_%"].round(0).astype(int)
                                if "RoyAmt_NUM" in df_preview_sug.columns:
                                    df_preview_sug = df_preview_sug.rename(columns={"RoyAmt_NUM": "Royalties"})
                                
                                st.dataframe(df_preview_sug.head(100), use_container_width=True, height=400)
                                
                                st.markdown("**Distribuição de Sugestões:**")
                                
                                roy_col = "Royalties" if "Royalties" in df_com_sugestao.columns else "RoyAmt_NUM"
                                
                                sug_stats = df_com_sugestao.groupby("CATÁLOGO_SUGERIDO").agg({
                                    roy_col: ["count", "sum"],
                                    "CONFIANÇA_%": "mean"
                                }).round(2)
                                sug_stats.columns = ["Quantidade", "Total Royalties", "Confiança Média %"]
                                sug_stats = sug_stats.sort_values("Quantidade", ascending=False)
                                st.dataframe(sug_stats, use_container_width=True)
                            
                            st.markdown("---")
                            st.markdown("### 📥 Download Completo")
                            
                            colunas_download = [
                                "Song No.", "Song", "Writer", "CATÁLOGO_SUGERIDO", "AUTORES_MATCH", 
                                "CONFIANÇA_%", 
                                "Source", "Inc Typ", "RoyAmt_NUM"
                            ]
                            colunas_download_disp = [col for col in colunas_download if col in df_agrupado.columns]
                            
                            df_download_completo = df_agrupado[colunas_download_disp].copy()
                            
                            df_download_completo["CONFIANÇA_%"] = df_download_completo["CONFIANÇA_%"].round(0).astype(int)
                            
                            if "RoyAmt_NUM" in df_download_completo.columns:
                                df_download_completo = df_download_completo.rename(columns={"RoyAmt_NUM": "Royalties"})
                            
                            df_download_completo = df_download_completo.sort_values(
                                ["CONFIANÇA_%", "Royalties" if "Royalties" in df_download_completo.columns else "RoyAmt_NUM"], 
                                ascending=[False, False]
                            )
                            
                            csv_completo = df_download_completo.to_csv(index=False, sep=";", encoding="utf-8-sig", decimal=",").encode("utf-8-sig")
                            
                            st.info(f"📊 Este arquivo contém **{len(df_download_completo)} músicas** ({len(df_com_sugestao)} com sugestão + {len(df_sem_sugestao)} sem sugestão)")
                            
                            st.download_button(
                                "⬇️ Baixar TODAS as músicas não mapeadas (com e sem sugestões)",
                                data=csv_completo,
                                file_name=f"obras_completo_sony_{ano_selecionado}_{mes_num_selecionado:02d}.csv",
                                mime="text/csv",
                                type="primary"
                            )
                        
                        else:
                            st.warning("⚠️ Coluna 'Writer' não encontrada na base de mapeamento.")

                    # --- SEÇÃO REPRTOIR (SONY) ---
                    st.markdown("---")
                    st.subheader("🔎 Buscar no Reprtoir")
                    if not REPRTOIR_DISPONIVEL:
                        st.info("ℹ️ Integração com Reprtoir não disponível. Verifique o arquivo `.env` com `REPRTOIR_API_KEY`.")
                    else:
                        st.caption("Consulta a API do Reprtoir para identificar músicas não mapeadas via título+autores.")
                        _rep_key_so = f"reprtoir_sony_{ano_selecionado}_{mes_num_selecionado:02d}"
                        if st.button("🔎 Buscar no Reprtoir", key="btn_reprtoir_sony"):
                            try:
                                _client_rep = ReprtorirClient()
                                _cats_internos = sorted(df_base_sony["CATÁLOGO"].dropna().astype(str).unique().tolist()) if "CATÁLOGO" in df_base_sony.columns else []
                                _resultados_rep = []
                                _progress_rep = st.progress(0)
                                _total_rep = len(df_agrupado)
                                for _i_rep, (_, _row_rep) in enumerate(df_agrupado.iterrows()):
                                    _progress_rep.progress((_i_rep + 1) / max(_total_rep, 1))
                                    _titulo = str(_row_rep.get("Song", "")).strip()
                                    _writer_raw = str(_row_rep.get("Writer", ""))
                                    _autores = []
                                    for _part in _writer_raw.split(";"):
                                        for _w in _part.split(","):
                                            _w_clean = _w.strip().replace("NC:", "").strip()
                                            if _w_clean:
                                                _autores.append(_w_clean)
                                    _obra_rep = lookup_obra(_client_rep, "", _titulo, _autores)
                                    if _obra_rep:
                                        _cat_rep = (_obra_rep.get("catalog") or {}).get("name", "")
                                        _cat_int, _score_rep = match_catalogo_interno(_cat_rep, _cats_internos)
                                        _resultados_rep.append({
                                            "Song No.": _row_rep["Song No."],
                                            "CATÁLOGO_REPRTOIR": _cat_rep,
                                            "CATÁLOGO_INTERNO_SUGERIDO": _cat_int,
                                            "CONFIANÇA_REPRTOIR_%": _score_rep,
                                            "FONTE_REPRTOIR": _obra_rep.get("_fonte", ""),
                                        })
                                _progress_rep.empty()
                                st.session_state[_rep_key_so] = _resultados_rep
                            except Exception as _e_rep:
                                st.error(f"❌ Erro ao consultar Reprtoir: {_e_rep}")

                        if st.session_state.get(_rep_key_so):
                            _df_rep = pd.DataFrame(st.session_state[_rep_key_so])
                            _df_com_rep = df_agrupado.merge(_df_rep, on="Song No.", how="inner")
                            st.success(f"✅ **{len(_df_com_rep)} músicas** identificadas pelo Reprtoir!")
                            _cols_rep = ["Song No.", "Song", "Writer", "CATÁLOGO_REPRTOIR", "CATÁLOGO_INTERNO_SUGERIDO", "CONFIANÇA_REPRTOIR_%", "FONTE_REPRTOIR", "RoyAmt_NUM"]
                            _cols_rep_disp = [c for c in _cols_rep if c in _df_com_rep.columns]
                            st.dataframe(_df_com_rep[_cols_rep_disp].sort_values("CONFIANÇA_REPRTOIR_%", ascending=False).head(100), use_container_width=True, height=400)
                            _csv_rep = _df_com_rep[_cols_rep_disp].to_csv(index=False, sep=";", encoding="utf-8-sig", decimal=",").encode("utf-8-sig")
                            st.download_button("⬇️ Baixar resultados Reprtoir (CSV)", data=_csv_rep, file_name=f"reprtoir_sony_{ano_selecionado}_{mes_num_selecionado:02d}.csv", mime="text/csv", key="dl_reprtoir_sony")

                else:
                    st.success("✅ Todas as músicas foram mapeadas com sucesso!")

            else:
                st.warning("Coluna 'RoyAmt' não encontrada no relatório.")
                st.dataframe(df_out, use_container_width=True, height=520)

            st.success("✅ Processamento concluído!")

        except Exception as e:
            st.error(f"❌ Erro ao processar: {e}")
            import traceback
            st.code(traceback.format_exc())

# ---------------------------
# IRMÃOS VITALE
# ---------------------------
elif fonte == "IRMÃOS VITALE":
    st.header("🎼 IRMÃOS VITALE - Processamento de Relatórios")

    # --- Base de catálogo ---
    if os.path.exists(CAMINHO_BASE_VITALE):
        base_source_vitale = CAMINHO_BASE_VITALE
        st.success(f"✅ Base de catálogo carregada: `{CAMINHO_BASE_VITALE}`")
    else:
        st.warning("⚠️ Base de catálogo não encontrada no caminho padrão. Faça o upload:")
        _uploaded_base_vi = st.file_uploader("Upload da base de catálogo Irmãos Vitale (.xlsx)", type=["xlsx"], key="base_vitale")
        if _uploaded_base_vi is None:
            st.info("Aguardando upload da base de catálogo.")
            st.stop()
        base_source_vitale = _uploaded_base_vi
        st.success("✅ Base de catálogo carregada via upload.")

    # --- Relatórios (trimestrais) ---
    periods = get_available_periods_vitale()

    if periods:
        st.subheader("Selecione o período do relatório")
        col1, col2 = st.columns(2)

        with col1:
            anos_disponiveis = sorted({p["ano"] for p in periods}, reverse=True)
            ano_selecionado = st.selectbox("Ano", anos_disponiveis)

        with col2:
            tris_do_ano = [p for p in periods if p["ano"] == ano_selecionado]
            tri_opcoes = [f"{p['tri']}º Trimestre" for p in tris_do_ano]
            tri_idx = st.selectbox("Trimestre", range(len(tri_opcoes)), format_func=lambda x: tri_opcoes[x])
            periodo_sel = tris_do_ano[tri_idx]

        tri_num_selecionado = periodo_sel["tri"]
        vitale_sources = periodo_sel["arquivos"]
        st.info("📁 Demonstrativos encontrados: " + ", ".join(sorted(vitale_sources.keys())))
    else:
        st.warning("⚠️ Relatórios Irmãos Vitale não encontrados na rede. Faça o upload dos demonstrativos (.XLS):")
        _uploaded_reports_vi = st.file_uploader(
            "Upload dos demonstrativos Vitale (DEX / DPV / Terceiros)",
            type=["xls"], accept_multiple_files=True, key="reports_vitale"
        )
        if not _uploaded_reports_vi:
            st.info("Aguardando upload dos demonstrativos.")
            st.stop()
        vitale_sources = {}
        for _up in _uploaded_reports_vi:
            _low = _up.name.lower()
            for _tipo in _VITALE_DEMOS:
                if _tipo.lower() in _low:
                    vitale_sources[_tipo] = _up
        if not vitale_sources:
            st.error("❌ Não identifiquei DEX/DPV/Terceiros nos nomes dos arquivos enviados.")
            st.stop()
        st.success("✅ Demonstrativos carregados: " + ", ".join(sorted(vitale_sources.keys())))
        ano_selecionado = 0
        tri_num_selecionado = 0

    # Botão para processar
    if st.button("🚀 Processar Cruzamento", type="primary"):
        try:
            with st.spinner("Carregando base de catálogo..."):
                df_base = read_base_xlsx(base_source_vitale)
                titulo_lookup = build_titulo_lookup(df_base)
            st.info(f"📚 Lookup criado: {len(titulo_lookup)} títulos mapeados na base")

            partes = []
            for _tipo, _src in vitale_sources.items():
                with st.spinner(f"Lendo demonstrativo {_tipo}..."):
                    partes.append(read_vitale_demonstrativo(_src, _tipo))
            df_all = pd.concat(partes, ignore_index=True) if partes else pd.DataFrame()

            if df_all.empty:
                st.warning("Nenhum dado encontrado nos demonstrativos.")
                st.stop()

            # Cruzamento por título normalizado
            df_all["__key"] = df_all["TÍTULO"].apply(_vitale_normalize_titulo)
            df_all["CATÁLOGO"] = df_all["__key"].map(titulo_lookup).fillna("")

            # --- Resultado agrupado por catálogo ---
            st.subheader("Resultado Agrupado por Catálogo")
            df_grouped = (
                df_all.groupby("CATÁLOGO", as_index=False)["VALOR"].sum()
                .sort_values("VALOR", ascending=False)
                .rename(columns={"VALOR": "Valor Repassado"})
            )
            st.dataframe(df_grouped, use_container_width=True, height=520)

            total_valor = df_grouped["Valor Repassado"].sum()
            st.markdown(f"**Total Repassado: R$ {total_valor:,.2f}**")

            csv_bytes = df_grouped.to_csv(index=False, sep=";", encoding="utf-8-sig", decimal=",").encode("utf-8-sig")
            st.download_button(
                "⬇️ Baixar resultado agrupado (CSV)",
                data=csv_bytes,
                file_name=f"relatorio_agrupado_vitale_{ano_selecionado}_{tri_num_selecionado}T.csv",
                mime="text/csv",
            )

            # --- Distribuição por demonstrativo ---
            st.markdown("**Distribuição por Demonstrativo:**")
            demo_stats = (
                df_all.groupby("DEMONSTRATIVO")
                .agg(Registros=("VALOR", "count"), Total=("VALOR", "sum"))
                .round(2).sort_values("Total", ascending=False)
            )
            st.dataframe(demo_stats, use_container_width=True)

            # --- Detalhado por obra ---
            st.markdown("---")
            st.subheader("📋 Download com Detalhes das Obras")

            df_detalhado = (
                df_all.groupby(["CATÁLOGO", "TÍTULO", "DEMONSTRATIVO"], as_index=False)["VALOR"].sum()
                .sort_values(["CATÁLOGO", "VALOR"], ascending=[True, False])
                .rename(columns={"VALOR": "Valor Repassado"})
            )

            total_obras = df_all["__key"].nunique()
            obras_mapeadas = df_all[df_all["CATÁLOGO"] != ""]["__key"].nunique()
            obras_nao_mapeadas = total_obras - obras_mapeadas

            c1, c2, c3 = st.columns(3)
            with c1:
                st.metric("📊 Obras (títulos únicos)", total_obras)
            with c2:
                st.metric("✅ Mapeadas", obras_mapeadas)
            with c3:
                st.metric("❌ Não Mapeadas", obras_nao_mapeadas)

            st.dataframe(df_detalhado.head(50), use_container_width=True, height=300)
            csv_det = df_detalhado.to_csv(index=False, sep=";", encoding="utf-8-sig", decimal=",").encode("utf-8-sig")
            st.download_button(
                "⬇️ Baixar relatório DETALHADO (CSV)",
                data=csv_det,
                file_name=f"relatorio_detalhado_vitale_{ano_selecionado}_{tri_num_selecionado}T.csv",
                mime="text/csv", type="primary",
            )

            # --- Obras não mapeadas ---
            st.markdown("---")
            st.subheader("🔍 Obras Não Mapeadas")
            df_nm = df_all[df_all["CATÁLOGO"] == ""].copy()
            if len(df_nm) > 0:
                df_nm_grp = (
                    df_nm.groupby("TÍTULO", as_index=False)
                    .agg(
                        Valor=("VALOR", "sum"),
                        Demonstrativos=("DEMONSTRATIVO", lambda s: " | ".join(sorted(set(s)))),
                    )
                    .sort_values("Valor", ascending=False)
                    .rename(columns={"Valor": "Valor Repassado"})
                )
                total_nm = df_nm_grp["Valor Repassado"].sum()
                st.warning(f"⚠️ **{len(df_nm_grp)} títulos** não mapeados | **Total: R$ {total_nm:,.2f}**")
                st.dataframe(df_nm_grp.head(100), use_container_width=True, height=300)
                csv_nm = df_nm_grp.to_csv(index=False, sep=";", encoding="utf-8-sig", decimal=",").encode("utf-8-sig")
                st.download_button(
                    "⬇️ Baixar obras não mapeadas (CSV)",
                    data=csv_nm,
                    file_name=f"obras_nao_mapeadas_vitale_{ano_selecionado}_{tri_num_selecionado}T.csv",
                    mime="text/csv", type="secondary",
                )
            else:
                st.success("✅ Todas as obras foram mapeadas com sucesso!")

            st.success("✅ Processamento concluído!")

        except Exception as e:
            st.error(f"❌ Erro ao processar: {e}")
            import traceback
            st.code(traceback.format_exc())

# ---------------------------
# INGROOVES
# ---------------------------
elif fonte == "INGROOVES":
    st.header("🎧 INGROOVES - Processamento de Relatórios")
    st.caption("Desconta 30% das receitas dos EUA e cruza por artista com a base de mapeamento. Usa apenas o DSR do label Nas_Nuvens_Catalog.")

    # --- Base de mapeamento ---
    if os.path.exists(CAMINHO_BASE_INGROOVES):
        base_source_ingrooves = CAMINHO_BASE_INGROOVES
        st.success(f"✅ Base de mapeamento carregada: `{CAMINHO_BASE_INGROOVES}`")
    else:
        st.warning("⚠️ Base de mapeamento não encontrada no caminho padrão. Faça o upload:")
        _uploaded_base_ig = st.file_uploader("Upload da base de mapeamento Ingrooves (.xlsx)", type=["xlsx"], key="base_ingrooves")
        if _uploaded_base_ig is None:
            st.info("Aguardando upload da base de mapeamento.")
            st.stop()
        base_source_ingrooves = _uploaded_base_ig
        st.success("✅ Base de mapeamento carregada via upload.")

    # --- Relatório ---
    periods = get_available_periods_ingrooves()

    if periods:
        st.subheader("Selecione o período do relatório")
        col1, col2 = st.columns(2)

        with col1:
            anos_disponiveis = sorted(list(set([p[0] for p in periods])), reverse=True)
            ano_selecionado = st.selectbox("Ano", anos_disponiveis)

        with col2:
            meses_do_ano = [p for p in periods if p[0] == ano_selecionado]
            meses_opcoes = [f"{p[1]:02d}. {p[2]} {str(p[0])[2:]}" for p in meses_do_ano]
            mes_selecionado_idx = st.selectbox("Mês", range(len(meses_opcoes)), format_func=lambda x: meses_opcoes[x])
            arquivo_selecionado = meses_do_ano[mes_selecionado_idx][3]

        mes_num_selecionado = meses_do_ano[mes_selecionado_idx][1]
        st.info(f"📁 Arquivo selecionado:\n`{arquivo_selecionado}`")
        report_source_ingrooves = arquivo_selecionado
    else:
        st.warning("⚠️ Relatórios Ingrooves não encontrados na rede. Faça o upload do arquivo:")
        _uploaded_report_ig = st.file_uploader("Upload do relatório Ingrooves (Nas_Nuvens_Catalog_*_DSR.xlsx)", type=["xlsx"], key="report_ingrooves")
        if _uploaded_report_ig is None:
            st.info("Aguardando upload do relatório.")
            st.stop()
        st.success(f"✅ Arquivo `{_uploaded_report_ig.name}` carregado.")
        report_source_ingrooves = _uploaded_report_ig
        ano_selecionado = 0
        mes_num_selecionado = 0

    # Botão para processar
    if st.button("🚀 Processar Cruzamento", type="primary"):
        try:
            with st.spinner("Carregando base de mapeamento Ingrooves..."):
                df_base_ig = read_base_ingrooves(base_source_ingrooves)

            with st.spinner("Carregando relatório Ingrooves..."):
                df_report = read_ingrooves_dsr(report_source_ingrooves)

            if "Net Dollars after Fees" not in df_report.columns:
                st.error(f"❌ Relatório não contém a coluna 'Net Dollars after Fees'. Colunas: {list(df_report.columns)}")
                st.stop()

            # Desconto de 30% nas receitas dos EUA
            original_total = df_report["Net Dollars after Fees"].sum()
            df_report["Net Dollars after Fees"] = df_report.apply(
                lambda row: row["Net Dollars after Fees"] * 0.7 if row.get("Territory") == "United States"
                else row["Net Dollars after Fees"],
                axis=1
            )
            discounted_total = df_report["Net Dollars after Fees"].sum()
            total_withheld = original_total - discounted_total

            st.write(f"O valor Original é **USD {original_total:,.2f}**")
            st.write(f"O total de withholding aplicado (30% EUA) é **USD {total_withheld:,.2f}**")
            st.write(f":red[O valor Net menos withholding é **USD {discounted_total:,.2f}**]")

            # Isola linhas Non-transactional antes do mapeamento, igual ao Ingrooves Breaker
            NON_TRANSACTIONAL_LABEL = "Ajustes Non-Transactional"
            if "Sales Description" in df_report.columns:
                mask_nt = df_report["Sales Description"].astype(str).str.contains("non-transactional", case=False, na=False)
            else:
                mask_nt = pd.Series(False, index=df_report.index)

            df_out = df_report.copy()
            df_out["CATÁLOGO"] = ""
            df_out.loc[mask_nt, "CATÁLOGO"] = NON_TRANSACTIONAL_LABEL

            with st.spinner("Cruzando artistas com a base de mapeamento..."):
                artist_cache = {}

                def resolve_catalogo(artist):
                    if artist not in artist_cache:
                        artist_cache[artist] = match_artist_ingrooves(artist, df_base_ig)
                    return artist_cache[artist]

                idx_to_map = df_out.index[~mask_nt]
                df_out.loc[idx_to_map, "CATÁLOGO"] = df_out.loc[idx_to_map, "Artist"].apply(resolve_catalogo)

            st.subheader("Resultado Agrupado por Catálogo")

            df_grouped = df_out.groupby("CATÁLOGO", as_index=False)["Net Dollars after Fees"].sum()
            df_grouped = df_grouped.sort_values("Net Dollars after Fees", ascending=False)
            df_grouped = df_grouped.rename(columns={"Net Dollars after Fees": "Net Dollars"})

            st.dataframe(df_grouped, use_container_width=True, height=520)

            total_net = df_grouped["Net Dollars"].sum()
            st.markdown(f"**Total Net Dollars: USD {total_net:,.2f}**")

            csv_bytes = df_grouped.to_csv(index=False, sep=";", encoding="utf-8-sig", decimal=",").encode("utf-8-sig")
            st.download_button(
                "⬇️ Baixar resultado agrupado (CSV)",
                data=csv_bytes,
                file_name=f"relatorio_agrupado_ingrooves_{ano_selecionado}_{mes_num_selecionado:02d}.csv",
                mime="text/csv",
            )

            # --- Download resultado DETALHADO ---
            st.markdown("---")
            st.subheader("📋 Download com Detalhes das Faixas")

            colunas_detalhadas = [
                "CATÁLOGO", "Artist", "Song", "Label", "Album Title", "ISRC",
                "Territory", "Sales Description", "Net Dollars after Fees"
            ]
            colunas_detalhadas_disp = [c for c in colunas_detalhadas if c in df_out.columns]
            df_detalhado_export = df_out[colunas_detalhadas_disp].copy()
            df_detalhado_export = df_detalhado_export.sort_values(
                ["CATÁLOGO", "Net Dollars after Fees"], ascending=[True, False]
            )

            total_linhas = len(df_detalhado_export)
            linhas_mapeadas = len(df_detalhado_export[df_detalhado_export["CATÁLOGO"] != ""])
            linhas_nao_mapeadas = total_linhas - linhas_mapeadas

            col_info1, col_info2, col_info3 = st.columns(3)
            with col_info1:
                st.metric("📊 Total de Linhas", total_linhas)
            with col_info2:
                st.metric("✅ Mapeadas", linhas_mapeadas)
            with col_info3:
                st.metric("❌ Não Mapeadas", linhas_nao_mapeadas)

            st.dataframe(df_detalhado_export.head(50), use_container_width=True, height=300)

            csv_detalhado = df_detalhado_export.to_csv(index=False, sep=";", encoding="utf-8-sig", decimal=",").encode("utf-8-sig")
            st.download_button(
                "⬇️ Baixar relatório DETALHADO com todas as faixas (CSV)",
                data=csv_detalhado,
                file_name=f"relatorio_detalhado_ingrooves_{ano_selecionado}_{mes_num_selecionado:02d}.csv",
                mime="text/csv",
                type="primary"
            )

            # --- SEÇÃO DE ARTISTAS NÃO MAPEADOS ---
            st.markdown("---")
            st.subheader("🔍 Artistas Não Mapeados")

            df_nao_mapeadas = df_out[(df_out["CATÁLOGO"] == "") & (~mask_nt)].copy()

            # Linhas sem nome de artista não são "não mapeadas": não há o que mapear.
            # Separadas aqui porque groupby("Artist") descarta silenciosamente valores nulos.
            mask_sem_artist = df_nao_mapeadas["Artist"].isna() | (df_nao_mapeadas["Artist"].astype(str).str.strip() == "")
            df_sem_artist = df_nao_mapeadas[mask_sem_artist]
            df_nao_mapeadas = df_nao_mapeadas[~mask_sem_artist]

            if len(df_sem_artist) > 0:
                total_sem_artist = df_sem_artist["Net Dollars after Fees"].sum()
                st.info(
                    f"ℹ️ **{len(df_sem_artist)} linha(s)** do relatório vieram sem nome de artista preenchido "
                    f"(não é possível mapear sem essa informação) | **Total: USD {total_sem_artist:,.2f}**"
                )

            if len(df_nao_mapeadas) > 0:
                df_nm_grp = df_nao_mapeadas.groupby("Artist", as_index=False)["Net Dollars after Fees"].sum()
                df_nm_grp = df_nm_grp.sort_values("Net Dollars after Fees", ascending=False)
                df_nm_grp = df_nm_grp.rename(columns={"Net Dollars after Fees": "Net Dollars"})

                total_nao_mapeado = df_nm_grp["Net Dollars"].sum()
                st.warning(f"⚠️ **{len(df_nm_grp)} artistas únicos** não foram encontrados na base de mapeamento | **Total: USD {total_nao_mapeado:,.2f}**")

                st.dataframe(df_nm_grp.head(100), use_container_width=True, height=300)

                # Template no mesmo formato da planilha de mapeamento (Artist, Label, Album Title,
                # Song, ISRC, Tag_Artista), pronto para preencher e colar em mapping-artistas-ingrooves.xlsx
                colunas_template = ["Artist", "Label", "Album Title", "Song", "ISRC"]
                colunas_template_disp = [c for c in colunas_template if c in df_nao_mapeadas.columns]
                df_template = df_nao_mapeadas[colunas_template_disp].drop_duplicates().sort_values("Artist")
                df_template["Tag_Artista"] = ""

                st.markdown(
                    "**Template para adicionar à base de mapeamento** — preencha a coluna `Tag_Artista` "
                    "e cole as linhas em `mapping-artistas-ingrooves.xlsx`:"
                )
                st.dataframe(df_template.head(100), use_container_width=True, height=300)

                csv_template = df_template.to_csv(index=False, sep=";", encoding="utf-8-sig").encode("utf-8-sig")
                st.download_button(
                    "⬇️ Baixar template de mapeamento (artistas não mapeados)",
                    data=csv_template,
                    file_name=f"template_mapeamento_ingrooves_{ano_selecionado}_{mes_num_selecionado:02d}.csv",
                    mime="text/csv",
                    type="secondary"
                )
            elif len(df_sem_artist) == 0:
                st.success("✅ Todos os artistas foram mapeados com sucesso!")

            st.success("✅ Processamento concluído!")

        except Exception as e:
            st.error(f"❌ Erro ao processar: {e}")
            import traceback
            st.code(traceback.format_exc())