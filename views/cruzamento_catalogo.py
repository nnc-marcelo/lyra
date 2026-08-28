# app.py
import io
import os
import sys
import re
import base64
import unicodedata
from io import BytesIO
from datetime import datetime, timedelta
from pathlib import Path
import pandas as pd
import requests
import streamlit as st
import zipfile
import xml.etree.ElementTree as ET
from collections import defaultdict, Counter

sys.path.insert(0, str(Path(__file__).parent.parent))
from utils.ui_components import render_html_table, simple_row, render_status_table
from utils.page import setup_page
# Leitores das bases: compartilhados com o Home (utils/metrics.py), que conta o
# conteudo de cada base sem importar esta pagina.
from utils.bases import (
    read_mapping_sony,
    normalize_catalog_column,
    read_catalog_base,
    read_mapping_xlsx,
)

# Integração opcional com Reprtoir — temporariamente DESATIVADA (reativação em
# breve). Manter em False força as seções de "Buscar no Reprtoir" a só exibirem
# o aviso de indisponibilidade, sem tentar consultar a API.
REPRTOIR_DISPONIVEL = False
REPRTOIR_MSG_DESATIVADO = (
    "🚧 A busca no Reprtoir está **temporariamente desativada** e será reativada em breve."
)
try:
    from utils.reprtoir_lookup import ReprtorirClient, lookup_obra, match_catalogo_interno  # noqa: F401
except Exception:
    pass

setup_page(__file__)

with st.expander("ℹ️ O que é esta página e como usar", expanded=False):
    st.markdown(
        """
**O que faz**

Concilia o relatório de uma distribuidora (o rendimento **obra a obra** do período) com a
**base de mapeamento** do catálogo (a planilha que diz "esta obra é do catálogo X") e devolve
**quanto do repasse foi de cada catálogo**, mais o detalhamento linha a linha e a lista do que
não casou.

**As quatro fontes**

| Fonte | Relatório | Chave de cruzamento | Base |
| --- | --- | --- | --- |
| **ABRAMUS** | ECAD `_XLS.csv` (uma linha por execução) | `CÓD. OBRA` ou `ISWC` (cat. E) / `CÓD FONOGRAMA` ou `ISRC` (demais), **sempre dentro da mesma categoria** | `Abramus Base_2026-08-27.xlsx` |
| **Sony** | planilha Sony (cabeçalho na linha 10) | `Song No.` → catálogo | `Mapping_Sony.xlsx` |
| **Irmãos Vitale** | demonstrativos DEX / DPV / Terceiros | título normalizado → catálogo | `Lista_Obras_Catalogo_Irmaos_Vitale.xlsx` |
| **Ingrooves** | DSR, aba `Digital Sales Details` | artista → tag de artista (exato, depois por trecho) | `mapping-artistas-ingrooves.xlsx` |

**A lógica do cruzamento ABRAMUS**

1. **Mesma categoria** — linha `E` do relatório só casa com linha `E` da base; `PF` com `PF`; `I` com `I`.
2. **Código *ou* ID** — para `E`, casa se bater `CÓD. OBRA` **ou** `ISWC`; para as demais, `CÓD FONOGRAMA` **ou** `ISRC`. Basta um. (A ABRAMUS renumera códigos entre períodos; o ISWC é estável.)
3. **Conflito** — se código e ISWC/ISRC apontam catálogos diferentes, ou a base tem a mesma obra em dois catálogos (`MIDAS | POLLO`): usa o do código e marca a linha para revisão.

**As abas do resultado**

- **Agrupado por Catálogo** — o número final (total de `RATEIO` por catálogo). Conflitos vêm com ⚠️ e um bloco "Requer revisão".
- **Detalhado** — uma linha por execução, com o catálogo resolvido; baixa em XLSX.
- **Não Mapeados** — o que não casou, agrupado por obra e ordenado por valor. É a lista de trabalho.
- **Revisar** (ABRAMUS) — casou só pelo ISWC/ISRC (código não bateu — ver coluna `CÓD. NA BASE`) e conflitos.

**Como usar**

1. Escolha a fonte na barra lateral e confira a base carregada.
2. Selecione o período (ou faça upload do relatório se estiver fora da rede `Z:`).
3. Clique em **Processar Cruzamento**.
4. Confira o **Agrupado**, depois **Não Mapeados** e **Revisar**.
5. Na aba de não mapeados, preencha o `CATÁLOGO` das obras que sobraram e **salve na base** —
   grava um commit e o app reinicia com o mapeamento atualizado (dá para desfazer pelo botão
   "Última gravação").
"""
    )

# ---------------------------
# Caminhos Fixos
# ---------------------------
_PROJECT_ROOT = Path(__file__).parent.parent

CAMINHO_BASE_ABRAMUS = str(_PROJECT_ROOT / "data" / "mapping" / "Abramus Base_2026-08-27.xlsx")
CAMINHO_ABRAMUS = r"Z:\ROYALTY\Royalties Statements_Historicals\Nas Nuvens Catalog\ABRAMUS\NAS NUVENS CATALOG S.A"

CAMINHO_BASE_SONY = str(_PROJECT_ROOT / "data" / "mapping" / "Mapping_Sony.xlsx")
CAMINHO_SONY = r"Z:\ROYALTY\Royalties Statements_Historicals\Nas Nuvens Catalog\SONY MUSIC PUBLISHING"

CAMINHO_BASE_VITALE = str(_PROJECT_ROOT / "data" / "mapping" / "Lista_Obras_Catalogo_Irmaos_Vitale.xlsx")
CAMINHO_VITALE = r"Z:\ROYALTY\Royalties Statements_Historicals\Nas Nuvens Catalog\IRMAOS VITALE"

CAMINHO_BASE_INGROOVES = str(_PROJECT_ROOT / "data" / "mapping" / "mapping-artistas-ingrooves.xlsx")
CAMINHO_INGROOVES = r"Z:\ROYALTY\Royalties Statements_Historicals\Nas Nuvens Catalog\INGROOVES"

# ---------------------------
# GitHub (salvar mapeamento colaborativo direto no repositório)
# ---------------------------
GITHUB_MAPPING_PATH = "data/mapping/mapping-artistas-ingrooves.xlsx"
GITHUB_MAPPING_PATH_ABRAMUS = "data/mapping/Abramus Base_2026-08-27.xlsx"


def get_github_config():
    """
    Lê credenciais do GitHub em st.secrets (seção [github]: token, repo, branch).
    Retorna None se não estiver configurado, para o app funcionar normalmente
    sem essa funcionalidade (ex.: ambiente local sem secrets.toml).
    """
    try:
        cfg = st.secrets["github"]
        token = cfg["token"]
    except Exception:
        return None
    if not token:
        return None
    return {
        "token": token,
        "repo": cfg.get("repo", "nnc-marcelo/lyra"),
        "branch": cfg.get("branch", "main"),
    }


def _github_headers(token: str) -> dict:
    return {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }


def github_fetch_mapping(gh_config: dict, path: str = GITHUB_MAPPING_PATH):
    """Busca a versão mais recente do arquivo de mapeamento direto do GitHub."""
    url = f"https://api.github.com/repos/{gh_config['repo']}/contents/{path}"
    resp = requests.get(
        url, headers=_github_headers(gh_config["token"]),
        params={"ref": gh_config["branch"]}, timeout=30
    )
    resp.raise_for_status()
    data = resp.json()
    content = base64.b64decode(data["content"])
    df = read_mapping_xlsx(BytesIO(content))
    return df, data["sha"]


def github_commits_do_arquivo(gh_config: dict, path: str = GITHUB_MAPPING_PATH, quantidade: int = 2):
    """
    Últimos commits que tocaram o arquivo de mapeamento, do mais recente para o
    mais antigo. É a única memória que sobrevive ao restart do app: como salvar
    dispara um redeploy no Streamlit Cloud, o session_state se perde, mas o
    histórico do GitHub continua lá.
    """
    url = f"https://api.github.com/repos/{gh_config['repo']}/commits"
    resp = requests.get(
        url, headers=_github_headers(gh_config["token"]),
        params={"path": path, "sha": gh_config["branch"], "per_page": quantidade}, timeout=30
    )
    resp.raise_for_status()
    return [
        {
            "sha": c["sha"],
            "mensagem": c["commit"]["message"].splitlines()[0],
            "data": c["commit"]["committer"]["date"],
            "autor": c["commit"]["author"]["name"],
            "url": c["html_url"],
        }
        for c in resp.json()
    ]


def github_restaurar_versao(gh_config: dict, path: str, sha_commit: str, commit_message: str):
    """
    Republica o arquivo como estava em `sha_commit`, criando um novo commit.
    Preferido a apagar histórico: o desfazer vira mais uma entrada no log, então
    dá para desfazer o desfazer.
    """
    url = f"https://api.github.com/repos/{gh_config['repo']}/contents/{path}"
    headers = _github_headers(gh_config["token"])

    antigo = requests.get(url, headers=headers, params={"ref": sha_commit}, timeout=30)
    antigo.raise_for_status()
    conteudo_antigo = antigo.json()["content"]

    atual = requests.get(url, headers=headers, params={"ref": gh_config["branch"]}, timeout=30)
    atual.raise_for_status()
    sha_atual = atual.json()["sha"]

    payload = {
        "message": commit_message,
        "content": conteudo_antigo,
        "sha": sha_atual,
        "branch": gh_config["branch"],
    }
    resp = requests.put(url, headers=headers, json=payload, timeout=30)
    resp.raise_for_status()
    return resp.json()


def github_save_mapping(gh_config: dict, df_novo: pd.DataFrame, sha: str, commit_message: str, path: str = GITHUB_MAPPING_PATH):
    """Sobe uma nova versão do arquivo de mapeamento, criando um commit no repositório."""
    output = BytesIO()
    df_novo.to_excel(output, index=False)
    content_b64 = base64.b64encode(output.getvalue()).decode("ascii")

    url = f"https://api.github.com/repos/{gh_config['repo']}/contents/{path}"
    payload = {
        "message": commit_message,
        "content": content_b64,
        "sha": sha,
        "branch": gh_config["branch"],
    }
    resp = requests.put(url, headers=_github_headers(gh_config["token"]), json=payload, timeout=30)
    resp.raise_for_status()
    return resp.json()


def _formata_data_commit(iso: str) -> str:
    """'2026-08-14T18:32:05Z' -> '14/08 15:32' (horário de Brasília)."""
    try:
        dt = datetime.strptime(iso, "%Y-%m-%dT%H:%M:%SZ") - timedelta(hours=3)
        return dt.strftime("%d/%m às %H:%M")
    except (ValueError, TypeError):
        return iso or "?"


def render_ultima_gravacao(gh_config: dict, path: str, state_key: str, item_label: str = "faixa(s)"):
    """
    Mostra a última gravação feita na base e permite desfazê-la.

    Existe porque a confirmação de salvamento não sobrevivia: o commit dispara um
    redeploy no Streamlit Cloud, o app reinicia e a mensagem de sucesso some junto
    com a sessão — dava a impressão de que nada tinha sido salvo. Aqui a
    informação vem do histórico do GitHub, então continua visível depois do
    restart.
    """
    if gh_config is None:
        return

    try:
        commits = github_commits_do_arquivo(gh_config, path=path, quantidade=2)
    except Exception as e:
        st.caption(f"⚠️ Não foi possível consultar o histórico da base: {e}")
        return

    if not commits:
        return

    ultimo = commits[0]
    st.info(
        f"🕒 **Última gravação na base:** {_formata_data_commit(ultimo['data'])} "
        f"por {ultimo['autor']} — [ver no GitHub]({ultimo['url']})  \n"
        f"`{ultimo['mensagem']}`"
    )

    # Só oferece desfazer para gravações feitas pelo app, e se houver versão
    # anterior do arquivo para restaurar.
    if "via app" not in ultimo["mensagem"] or len(commits) < 2:
        return

    anterior = commits[1]
    confirmar_key = f"confirmar_undo_{state_key}"

    if not st.session_state.get(confirmar_key):
        if st.button("↩️ Desfazer esta gravação", key=f"btn_undo_{state_key}"):
            st.session_state[confirmar_key] = True
            st.rerun()
        return

    st.warning(
        f"Isto devolve a base ao estado de {_formata_data_commit(anterior['data'])} "
        f"(`{anterior['mensagem']}`), descartando o que foi gravado depois. "
        "O histórico é preservado: o desfazer entra como um novo commit."
    )
    col_sim, col_nao = st.columns(2)
    with col_sim:
        if st.button("✅ Confirmar desfazer", type="primary", key=f"btn_undo_ok_{state_key}"):
            try:
                with st.spinner("Restaurando versão anterior..."):
                    github_restaurar_versao(
                        gh_config, path, anterior["sha"],
                        commit_message=f"data: desfaz '{ultimo['mensagem']}' via app",
                    )
                st.session_state[confirmar_key] = False
                st.success(
                    "✅ Base restaurada à versão anterior. "
                    "O app vai reiniciar em instantes com o mapeamento de volta ao que era."
                )
            except Exception as e:
                st.error(f"❌ Erro ao restaurar: {e}")
    with col_nao:
        if st.button("Cancelar", key=f"btn_undo_cancel_{state_key}"):
            st.session_state[confirmar_key] = False
            st.rerun()


def save_linhas_no_mapeamento(
    gh_config: dict,
    df_linhas: pd.DataFrame,
    commit_message: str,
    path: str = GITHUB_MAPPING_PATH,
    dedup_cols=("ISRC",),
    count_col: str = "Artist",
    count_label: str = "artista(s)",
    item_label: str = "faixa(s)",
):
    """
    Busca a versão atual da base no GitHub, descarta linhas cuja chave de dedup
    (dedup_cols) já exista, concatena as novas e sobe a versão atualizada. Usado
    tanto pela edição inline quanto pelo upload em massa do template preenchido
    (Ingrooves e ABRAMUS).
    """
    with st.spinner("Buscando versão atual do mapeamento no GitHub..."):
        df_mapping_atual, sha_atual = github_fetch_mapping(gh_config, path=path)

    # As bases gravam o cabeçalho de catálogo de jeitos diferentes ("CATÁLOGO",
    # "CATALOGO", "CATALOGO CORRETO" na base nova da ABRAMUS). Normaliza os dois
    # lados para "CATÁLOGO" antes de concatenar (senão o pd.concat cria colunas
    # paralelas cheias de NaN) e, no fim, devolve o nome original da base.
    _cat_col_original = None
    if "CATÁLOGO" in df_linhas.columns:
        for _alias in ("CATÁLOGO", "CATALOGO", "CATALOGO CORRETO", "CATÁLOGO CORRETO"):
            if _alias in df_mapping_atual.columns:
                _cat_col_original = _alias
                break
        try:
            df_mapping_atual = normalize_catalog_column(df_mapping_atual)
        except ValueError:
            pass

    dedup_cols_disp = [c for c in dedup_cols if c in df_mapping_atual.columns and c in df_linhas.columns]
    if dedup_cols_disp:
        # Uma linha nova é duplicata se QUALQUER coluna de dedup já tiver aquele
        # valor na base — compara coluna a coluna, não uma chave concatenada
        # "a|b". A chave concatenada quebrava na base ABRAMUS: as obras de
        # categoria E têm CÓD. OBRA mas ~metade não tem CÓD FONOGRAMA, então a
        # chave "cod|nan" nunca batia (a linha da base caía no dropna how="any")
        # e toda obra E era regravada a cada save/importação.
        ja_existe = pd.Series(False, index=df_linhas.index)
        for _c in dedup_cols_disp:
            existentes = set(df_mapping_atual[_c].dropna().astype(str).str.strip()) - {"", "nan"}
            col_novas = df_linhas[_c].fillna("").astype(str).str.strip()
            ja_existe |= col_novas.ne("") & col_novas.isin(existentes)
        df_novas_linhas = df_linhas[~ja_existe]
    else:
        df_novas_linhas = df_linhas

    if df_novas_linhas.empty:
        st.info(f"Essas {item_label} já estão na base de mapeamento (nada novo pra salvar).")
        return

    df_mapping_final = pd.concat([df_mapping_atual, df_novas_linhas], ignore_index=True)
    if _cat_col_original and _cat_col_original != "CATÁLOGO":
        df_mapping_final = df_mapping_final.rename(columns={"CATÁLOGO": _cat_col_original})
    with st.spinner("Salvando no GitHub..."):
        github_save_mapping(gh_config, df_mapping_final, sha_atual, commit_message=commit_message, path=path)

    count_val = df_novas_linhas[count_col].nunique() if count_col in df_novas_linhas.columns else len(df_novas_linhas)
    st.success(
        f"✅ {count_val} {count_label} "
        f"({len(df_novas_linhas)} {item_label}) salvos na base de mapeamento! "
        f"O app vai reiniciar em instantes com o mapeamento atualizado."
    )

# ---------------------------
# Helpers Gerais
# ---------------------------
XLSX_MIME = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


def df_to_xlsx_bytes(df: pd.DataFrame, sheet_name: str = "Sheet1") -> bytes:
    """Serializa um DataFrame como XLSX (bytes), pronto para st.download_button."""
    output = BytesIO()
    with pd.ExcelWriter(output, engine="xlsxwriter") as writer:
        df.to_excel(writer, index=False, sheet_name=sheet_name)
    return output.getvalue()


def preview_dataframe(df: pd.DataFrame, height: int = 600) -> None:
    """
    Exibe o DataFrame completo. Antes as tabelas eram truncadas em 50/100 linhas;
    o st.dataframe é virtualizado (renderiza só as linhas visíveis), então mostrar
    tudo rola bem mesmo com dezenas de milhares de linhas.
    """
    st.dataframe(df, use_container_width=True, height=height)


def read_base_xlsx(file_path: str) -> pd.DataFrame:
    """
    Lê base de catálogo em XLSX. Robusto a arquivos com várias abas: escolhe a
    aba que tem a coluna de catálogo (a coluna já sai renomeada para `CATÁLOGO`).
    """
    return read_catalog_base(file_path)

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


def build_lookup_abramus(
    df_base: pd.DataFrame, code_col: str, id_col: str, categoria: str | None = None
) -> tuple[dict, dict]:
    """
    Cruzamento ABRAMUS com a base nova (colunas de ISWC/ISRC):
    categoria E -> CÓD. OBRA + ISWC ; demais -> CÓD FONOGRAMA + ISRC.

    O cruzamento respeita a CATEGORIA: a linha do relatório só casa com linhas
    da base de MESMA categoria (E com E, PF com PF, I com I). `categoria` = o
    valor exato a filtrar; None não filtra (base antiga, sem a coluna).

    Retorna (por_codigo, por_id, id_para_codigo):
      - por_codigo:     <código> -> catálogo
      - por_id:         <ISWC/ISRC> -> catálogo
      - id_para_codigo: <ISWC/ISRC> -> código(s) que a base tem para esse ID
        (para mostrar, na análise, qual código da base corresponde)
    A linha casa se o CÓDIGO **ou** o ID bater (não precisa dos dois). Valores
    repetidos juntam com ' | '.
    """
    if code_col not in df_base.columns or "CATÁLOGO" not in df_base.columns:
        return {}, {}, {}

    if categoria is not None and "CATEGORIA" in df_base.columns:
        cat = df_base["CATEGORIA"].astype(str).str.strip().str.upper()
        df_base = df_base[cat == str(categoria).strip().upper()]
    df_base = df_base.reset_index(drop=True)

    tmp = df_base[[code_col, "CATÁLOGO"]].copy()
    tmp["__cod"] = tmp[code_col].astype(str).str.strip()
    tmp["__id"] = (
        df_base[id_col].astype(str).str.strip() if id_col in df_base.columns else ""
    )
    tmp["CATÁLOGO"] = tmp["CATÁLOGO"].astype(str).str.strip()
    tmp = tmp[(tmp["CATÁLOGO"] != "") & (tmp["CATÁLOGO"].str.lower() != "nan")]

    def _join(s):
        return " | ".join(sorted(set(s)))

    validos = lambda col: tmp[(tmp[col] != "") & (tmp[col].str.lower() != "nan")]
    por_codigo = validos("__cod").groupby("__cod")["CATÁLOGO"].apply(_join).to_dict()
    _com_id = validos("__id")
    por_id = _com_id.groupby("__id")["CATÁLOGO"].apply(_join).to_dict()
    id_para_codigo = (
        _com_id[(_com_id["__cod"] != "") & (_com_id["__cod"].str.lower() != "nan")]
        .groupby("__id")["__cod"].apply(_join).to_dict()
    )
    return por_codigo, por_id, id_para_codigo


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
    st.caption("Cruza por CÓD. OBRA ou ISWC (categoria E) / CÓD FONOGRAMA ou ISRC (demais categorias), sempre dentro da mesma categoria da base.")

    # --- Base de catálogo ---
    if os.path.exists(CAMINHO_BASE_ABRAMUS):
        base_source_abramus = CAMINHO_BASE_ABRAMUS
        st.success(f"✅ Base de catálogo carregada: `{CAMINHO_BASE_ABRAMUS}`")
    else:
        st.warning("⚠️ Base de catálogo não encontrada no caminho padrão. Faça o upload:")
        _uploaded_base_ab = st.file_uploader("Upload da base de catálogo ABRAMUS (.xlsx)", type=["xlsx"])
        if _uploaded_base_ab is None:
            st.info("Aguardando upload da base de catálogo.")
            st.stop()
        base_source_abramus = _uploaded_base_ab
        st.success("✅ Base de catálogo carregada via upload.")

    # --- Editar base de catálogo completa ---
    with st.expander("✏️ Editar base de catálogo completa"):
        gh_config_mapping_ab = get_github_config()
        sha_mapping_ab = None
        df_mapping_full_ab = None

        if gh_config_mapping_ab is not None:
            try:
                df_mapping_full_ab, sha_mapping_ab = github_fetch_mapping(gh_config_mapping_ab, path=GITHUB_MAPPING_PATH_ABRAMUS)
            except Exception as e:
                st.error(f"❌ Erro ao buscar base no GitHub: {e}")
        elif isinstance(base_source_abramus, str) and os.path.exists(base_source_abramus):
            try:
                df_mapping_full_ab = read_mapping_xlsx(base_source_abramus)
            except Exception as e:
                st.error(f"❌ Erro ao carregar base de catálogo: {e}")
        else:
            st.caption("Edição indisponível: nem GitHub configurado, nem arquivo local encontrado (base veio de upload).")

        if df_mapping_full_ab is not None:
            st.caption(
                f"{len(df_mapping_full_ab)} registro(s). Use a lupa no canto superior da tabela para buscar "
                "por título, ISWC/ISRC, código de obra/fonograma, categoria etc. Também dá para adicionar ou apagar linhas."
            )
            df_mapping_editado_ab = st.data_editor(
                df_mapping_full_ab,
                use_container_width=True,
                height=400,
                num_rows="dynamic",
                key="editor_mapping_completo_abramus",
                hide_index=True,
            )

            if gh_config_mapping_ab is not None:
                if st.button("💾 Salvar alterações na base de catálogo", type="primary"):
                    try:
                        with st.spinner("Salvando no GitHub..."):
                            github_save_mapping(
                                gh_config_mapping_ab,
                                df_mapping_editado_ab,
                                sha_mapping_ab,
                                commit_message="data: edita base de catálogo ABRAMUS via app",
                                path=GITHUB_MAPPING_PATH_ABRAMUS,
                            )
                        st.success("✅ Base de catálogo atualizada! O app vai reiniciar em instantes.")
                    except Exception as e:
                        st.error(f"❌ Erro ao salvar no GitHub: {e}")
            else:
                if st.button("💾 Salvar alterações na base de catálogo (arquivo local)", type="primary"):
                    try:
                        df_mapping_editado_ab.to_excel(base_source_abramus, index=False)
                        st.success("✅ Base de catálogo salva localmente!")
                    except Exception as e:
                        st.error(f"❌ Erro ao salvar localmente: {e}")

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
        _uploaded_report_ab = st.file_uploader("Upload do relatório ABRAMUS (_XLS.CSV)", type=["csv"])
        if _uploaded_report_ab is None:
            st.info("Aguardando upload do relatório.")
            st.stop()
        st.success(f"✅ Arquivo `{_uploaded_report_ab.name}` carregado.")
        report_source_abramus = _uploaded_report_ab
        ano_selecionado = 0
        mes_num_selecionado = 0

    # Chave do período atual, usada para: (1) cachear o resultado no session_state
    # sobrevivendo a reruns causados pela edição do data_editor, e (2) nomear
    # arquivos/widgets de forma estável.
    if periods:
        period_suffix = f"{ano_selecionado}_{mes_num_selecionado:02d}"
    else:
        period_suffix = re.sub(r"[^A-Za-z0-9_-]", "_", getattr(report_source_abramus, "name", "upload"))

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
            if "ISWC" not in df_base.columns:
                st.warning("Base não contém coluna 'ISWC' (cruzamento da categoria E cai só no código).")
            if "CÓD FONOGRAMA" not in df_base.columns:
                st.warning("Base não contém coluna 'CÓD FONOGRAMA' (necessária para categorias não-E).")
            if "ISRC" not in df_base.columns:
                st.warning("Base não contém coluna 'ISRC' (cruzamento das demais categorias cai só no código).")

            # Normaliza campos do relatório
            for c in ["CÓD. OBRA", "CÓD FONOGRAMA", "CATEGORIA", "ISWC", "ISRC"]:
                if c in df_report.columns:
                    df_report[c] = df_report[c].astype(str).str.strip()

            # Lookups POR CATEGORIA: a linha do relatório só casa com linhas da
            # base de MESMA categoria (E com E, PF com PF, I com I). Categoria E
            # cruza por CÓD. OBRA ou ISWC; as demais por CÓD FONOGRAMA ou ISRC —
            # basta um dos dois bater.
            _cats_relatorio = (
                sorted(c for c in df_report.get("CATEGORIA", pd.Series(dtype=str)).unique() if c and c.lower() != "nan")
                if "CATEGORIA" in df_report.columns else []
            )
            _lookups = {}
            for _cat in _cats_relatorio:
                if _cat.upper() == "E":
                    _lookups[_cat] = ("CÓD. OBRA", "ISWC", *build_lookup_abramus(df_base, "CÓD. OBRA", "ISWC", categoria=_cat))
                else:
                    _lookups[_cat] = ("CÓD FONOGRAMA", "ISRC", *build_lookup_abramus(df_base, "CÓD FONOGRAMA", "ISRC", categoria=_cat))

            def resolve_catalog(row):
                """Retorna (catálogo, como_casou, cod_na_base). como_casou ∈
                {'', 'codigo', 'iswc_isrc', 'conflito'}.
                'conflito' = mapeamento contraditório, precisa de revisão manual:
                  (a) código e ISWC/ISRC apontam catálogos diferentes, ou
                  (b) o próprio código/ISWC está cadastrado na base com mais de
                      um catálogo (valor vem com ' | ').
                cod_na_base = o CÓD. OBRA/FONOGRAMA que a base tem para aquele
                ISWC/ISRC, preenchido só quando o código da linha não bateu."""
                cat = (row.get("CATEGORIA") or "").strip()
                entry = _lookups.get(cat)
                if entry is None:
                    return "", "", ""
                cod_col, id_col, por_codigo, por_id, id_para_codigo = entry
                cod = (row.get(cod_col) or "").strip()
                sec = (row.get(id_col) or "").strip()

                val_cod = por_codigo.get(cod, "") if cod and cod.lower() != "nan" else ""
                val_id = por_id.get(sec, "") if sec and sec.lower() != "nan" else ""
                cod_base = id_para_codigo.get(sec, "") if sec and sec.lower() != "nan" else ""

                if val_cod and val_id and val_cod != val_id:
                    return val_cod, "conflito", cod_base  # código vs ISWC/ISRC
                escolhido = val_cod or val_id
                if not escolhido:
                    return "", "", ""
                if " | " in escolhido:
                    return escolhido, "conflito", ("" if val_cod else cod_base)  # base ambígua
                if val_cod:
                    return val_cod, "codigo", ""
                return val_id, "iswc_isrc", cod_base

            df_out = df_report.copy()
            df_out[["CATÁLOGO", "CASOU_POR", "CÓD. NA BASE"]] = df_out.apply(
                resolve_catalog, axis=1, result_type="expand"
            )

            _n_so_id = int((df_out["CASOU_POR"] == "iswc_isrc").sum())
            _n_conflito = int((df_out["CASOU_POR"] == "conflito").sum())
            _msgs = []
            if _n_so_id:
                _msgs.append(f"{_n_so_id} casada(s) só pelo ISWC/ISRC (CÓD. OBRA não bateu)")
            if _n_conflito:
                _msgs.append(f"{_n_conflito} CONFLITO(s) de catálogo na base")
            if _msgs:
                st.caption("ℹ️ " + " · ".join(_msgs) + " — ver aba de revisão")

            # Guarda o resultado no session_state: a edição do data_editor abaixo
            # dispara reruns da página, e sem isso o app voltaria pra tela inicial
            # (o "if st.button" só é True no exato clique, não nos reruns seguintes).
            st.session_state["abramus_result"] = {
                "period_suffix": period_suffix,
                "df_out": df_out,
                "df_base": df_base,
            }
        except Exception as e:
            st.error(f"❌ Erro ao processar: {e}")
            import traceback
            st.code(traceback.format_exc())

    # --- Renderização dos resultados (fora do botão, para sobreviver a reruns) ---
    resultado = st.session_state.get("abramus_result")
    if resultado and resultado["period_suffix"] == period_suffix:
        df_out = resultado["df_out"]
        df_base = resultado["df_base"]

        st.success("✅ Processamento concluído!")
        st.subheader("Resultado Agrupado por Catálogo")

        if "RATEIO" not in df_out.columns:
            st.warning("Coluna 'RATEIO' não encontrada no relatório.")
            st.dataframe(df_out, use_container_width=True, height=520)
        else:
            df_out["RATEIO"] = df_out["RATEIO"].astype(str).str.replace(",", ".", regex=False)
            df_out["RATEIO"] = pd.to_numeric(df_out["RATEIO"], errors="coerce")

            df_nao_mapeadas_raw = df_out[df_out["CATÁLOGO"].isin(["", "nan"]) | df_out["CATÁLOGO"].isna()].copy()

            df_so_iswc = df_out[df_out["CASOU_POR"].isin(["iswc_isrc", "conflito"])].copy()
            _n_obras_iswc = (
                df_so_iswc["CÓD. OBRA"].nunique() if "CÓD. OBRA" in df_so_iswc.columns else len(df_so_iswc)
            )

            _tab_labels = ["📊 Agrupado por Catálogo", "📋 Detalhado", "🔍 Não Mapeados"]
            if not df_so_iswc.empty:
                _tab_labels.append(f"⚠️ Revisar — ISWC/ISRC e conflitos ({_n_obras_iswc})")
            _tabs = st.tabs(_tab_labels)
            tab_agrupado, tab_detalhado, tab_nao_mapeados = _tabs[0], _tabs[1], _tabs[2]
            tab_so_iswc = _tabs[3] if not df_so_iswc.empty else None

            with tab_agrupado:
                df_grouped = df_out.groupby("CATÁLOGO", as_index=False)["RATEIO"].sum()
                df_grouped = df_grouped.sort_values("RATEIO", ascending=False)

                render_html_table(
                    ["Catálogo", "RATEIO"],
                    [
                        simple_row([
                            ("⚠️ " if " | " in str(r["CATÁLOGO"]) else "") + (r["CATÁLOGO"] or "(sem catálogo)"),
                            f"R$ {r['RATEIO']:,.2f}",
                        ])
                        for _, r in df_grouped.iterrows()
                    ],
                    max_height="480px",
                    translucent=False,
                )

                total_rateio = df_grouped["RATEIO"].sum()
                st.markdown(f"**Total RATEIO: R$ {total_rateio:,.2f}**")

                # Conflitos (catálogo contraditório) e casados só por ISWC/ISRC —
                # mostrados aqui também, não só na aba de revisão.
                _conf = df_out[df_out["CASOU_POR"] == "conflito"]
                _isw = df_out[df_out["CASOU_POR"] == "iswc_isrc"]
                if not _conf.empty or not _isw.empty:
                    _linhas = []
                    _tem_cod_obra = "CÓD. OBRA" in df_out.columns
                    _n_obras = lambda d: d["CÓD. OBRA"].nunique() if _tem_cod_obra else len(d)
                    if not _conf.empty:
                        for _c, _g in _conf.groupby("CATÁLOGO"):
                            _linhas.append(f"- ⚠️ **{_c}** — R$ {_g['RATEIO'].sum():,.2f} ({_n_obras(_g)} obra(s)) · *catálogo contraditório na base*")
                    if not _isw.empty:
                        _linhas.append(f"- ℹ️ casadas só pelo ISWC/ISRC — R$ {_isw['RATEIO'].sum():,.2f} ({_n_obras(_isw)} obra(s))")
                    st.markdown(
                        "**Requer revisão** (detalhe na aba *Revisar*):\n" + "\n".join(_linhas)
                    )

                xlsx_bytes = df_to_xlsx_bytes(df_grouped)
                st.download_button(
                    "⬇️ Baixar resultado agrupado (XLSX)",
                    data=xlsx_bytes,
                    file_name=f"relatorio_agrupado_abramus_{period_suffix}.xlsx",
                    mime=XLSX_MIME,
                )

            with tab_detalhado:
                st.subheader("📋 Download com Detalhes das Obras")

                df_detalhado = df_out.copy()

                colunas_detalhadas = [
                    "CATÁLOGO", "TÍTULO DA MUSICA", "CÓD. OBRA", "CÓD FONOGRAMA",
                    "ISWC", "ISRC", "AUTORES", "INTERPRETE", "CATEGORIA",
                    "PARTICIPAÇÃO", "RATEIO"
                ]
                colunas_detalhadas_disp = [col for col in colunas_detalhadas if col in df_detalhado.columns]

                df_detalhado_export = df_detalhado[colunas_detalhadas_disp].copy()

                if "RATEIO" in df_detalhado_export.columns:
                    df_detalhado_export = df_detalhado_export.sort_values(["CATÁLOGO", "RATEIO"], ascending=[True, False])

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

                preview_dataframe(df_detalhado_export)

                xlsx_detalhado = df_to_xlsx_bytes(df_detalhado_export)
                st.download_button(
                    "⬇️ Baixar relatório DETALHADO com todas as obras (XLSX)",
                    data=xlsx_detalhado,
                    file_name=f"relatorio_detalhado_abramus_{period_suffix}.xlsx",
                    mime=XLSX_MIME,
                    type="primary"
                )

            if tab_so_iswc is not None:
                with tab_so_iswc:
                    st.subheader("⚠️ Obras para revisar")
                    st.markdown(
                        "- **`iswc_isrc`** — o CÓD. OBRA/FONOGRAMA do relatório não existe na base; "
                        "casou pelo ISWC/ISRC. Compare `CÓD. OBRA` (relatório) com `CÓD. NA BASE` — "
                        "normalmente a ABRAMUS renumerou a obra.\n"
                        "- **`conflito`** — mapeamento contraditório: ou código e ISWC/ISRC apontam "
                        "catálogos diferentes, ou a **própria base** cadastrou o mesmo código/ISWC "
                        "com mais de um catálogo (aparece como `X | Y`). Precisa acertar a base."
                    )

                    # Uma linha por obra (o relatório traz várias execuções da
                    # mesma obra); soma o RATEIO.
                    _grp_iswc = [
                        c for c in ["CATÁLOGO", "CASOU_POR", "TÍTULO DA MUSICA", "CÓD. OBRA",
                                    "CÓD. NA BASE", "CÓD FONOGRAMA", "ISWC", "ISRC", "AUTORES", "CATEGORIA"]
                        if c in df_so_iswc.columns
                    ]
                    if "RATEIO" in df_so_iswc.columns:
                        df_so_iswc_view = (
                            df_so_iswc.groupby(_grp_iswc, as_index=False, dropna=False)["RATEIO"].sum()
                            .sort_values("RATEIO", ascending=False)
                        )
                    else:
                        df_so_iswc_view = df_so_iswc[_grp_iswc].drop_duplicates()

                    _c1, _c2 = st.columns(2)
                    _c1.metric("Obras p/ analisar", len(df_so_iswc_view))
                    if "RATEIO" in df_so_iswc_view.columns:
                        _c2.metric("RATEIO envolvido", f"R$ {df_so_iswc_view['RATEIO'].sum():,.2f}")

                    preview_dataframe(df_so_iswc_view)
                    st.download_button(
                        "⬇️ Baixar (XLSX)",
                        data=df_to_xlsx_bytes(df_so_iswc_view),
                        file_name=f"abramus_casados_por_iswc_{period_suffix}.xlsx",
                        mime=XLSX_MIME,
                    )

            with tab_nao_mapeados:
                df_nao_mapeadas = df_nao_mapeadas_raw

                if len(df_nao_mapeadas) > 0:
                    df_nao_mapeadas["RATEIO_NUM"] = df_nao_mapeadas["RATEIO"]

                    def get_chave_agrupamento(row):
                        cat = str(row.get("CATEGORIA", "")).strip().upper()
                        if cat == "E":
                            return str(row.get("CÓD. OBRA", "")).strip()
                        else:
                            return str(row.get("CÓD FONOGRAMA", "")).strip()

                    df_nao_mapeadas["CHAVE_GRUPO"] = df_nao_mapeadas.apply(get_chave_agrupamento, axis=1)

                    colunas_primeiro = ["TÍTULO DA MUSICA", "CÓD. OBRA", "CÓD FONOGRAMA", "ISWC", "ISRC", "AUTORES", "CATEGORIA"]
                    colunas_primeiro_disp = [col for col in colunas_primeiro if col in df_nao_mapeadas.columns]

                    agg_dict = {col: 'first' for col in colunas_primeiro_disp}
                    agg_dict["RATEIO_NUM"] = "sum"

                    df_agrupado = df_nao_mapeadas.groupby("CHAVE_GRUPO", as_index=False).agg(agg_dict)
                    df_agrupado = df_agrupado[df_agrupado["CHAVE_GRUPO"] != ""]

                    total_nao_mapeado = df_agrupado["RATEIO_NUM"].sum()

                    st.warning(f"⚠️ **{len(df_agrupado)} obras únicas** não foram mapeadas | **Total: R$ {total_nao_mapeado:,.2f}**")

                    df_agrupado = df_agrupado.sort_values("RATEIO_NUM", ascending=False)

                    colunas_exibir = ["TÍTULO DA MUSICA", "CÓD. OBRA", "CÓD FONOGRAMA", "ISWC", "ISRC", "AUTORES", "CATEGORIA", "RATEIO_NUM"]
                    colunas_exibir_disp = [col for col in colunas_exibir if col in df_agrupado.columns]

                    df_preview = df_agrupado[colunas_exibir_disp].copy()
                    df_preview = df_preview.rename(columns={"RATEIO_NUM": "RATEIO"})

                    preview_dataframe(df_preview)

                    if "CATEGORIA" in df_agrupado.columns:
                        st.markdown("**Distribuição por Categoria:**")
                        cat_stats = df_agrupado.groupby("CATEGORIA").agg({
                            "RATEIO_NUM": ["count", "sum"]
                        }).round(2)
                        cat_stats.columns = ["Quantidade", "Total Rateio"]
                        st.dataframe(cat_stats, use_container_width=True)

                    # --- RESOLUÇÃO: preencher CATÁLOGO para as obras não mapeadas ---
                    st.markdown("---")
                    st.subheader("✏️ Resolver Obras Não Mapeadas")

                    # Estrutura da base nova da ABRAMUS (com ISRC/CATEGORIA, sem
                    # AUTORES). O CATEGORIA é essencial: o cruzamento casa E-com-E,
                    # PF-com-PF etc., então obra salva sem categoria não casaria.
                    # "CATÁLOGO" é renomeado para "CATALOGO CORRETO" ao gravar.
                    colunas_mapeamento_abramus = [
                        c for c in ["TÍTULO DA MUSICA", "CÓD. OBRA", "ISWC", "CÓD FONOGRAMA",
                                    "ISRC", "CATEGORIA"]
                        if c in df_agrupado.columns
                    ] + ["CATÁLOGO"]

                    render_ultima_gravacao(
                        gh_config_mapping_ab, GITHUB_MAPPING_PATH_ABRAMUS,
                        state_key=f"abramus_{period_suffix}", item_label="linha(s)",
                    )
                    modo_resolucao_ab = st.radio(
                        "Como preencher o `CATÁLOGO`?",
                        ["✏️ Editar na tela", "📤 Importar arquivo preenchido"],
                        horizontal=True,
                        key=f"modo_resolucao_abramus_{period_suffix}",
                    )

                    if modo_resolucao_ab == "✏️ Editar na tela":
                        # AUTORES entra como contexto para decidir o catálogo, mas
                        # não é gravado (a base nova não tem essa coluna).
                        colunas_template_ab = ["TÍTULO DA MUSICA", "AUTORES", "CÓD. OBRA", "CÓD FONOGRAMA", "ISWC", "ISRC", "CATEGORIA"]
                        colunas_template_ab_disp = [c for c in colunas_template_ab if c in df_agrupado.columns]
                        df_template_ab = df_agrupado[colunas_template_ab_disp].drop_duplicates().sort_values("TÍTULO DA MUSICA").reset_index(drop=True)
                        df_template_ab["CATÁLOGO"] = ""

                        st.markdown(
                            "**Preencha `CATÁLOGO`** — mesma estrutura da base de catálogo, "
                            "pronta para salvar direto ou baixar e colar na base ABRAMUS "
                            "(a coluna vira `CATALOGO CORRETO` ao gravar):"
                        )

                        editor_key_ab = f"editor_abramus_naomapeados_{period_suffix}"
                        df_editado_ab = st.data_editor(
                            df_template_ab,
                            use_container_width=True,
                            height=300,
                            key=editor_key_ab,
                            disabled=colunas_template_ab_disp,
                            hide_index=True,
                        )

                        preenchidos_ab = df_editado_ab[df_editado_ab["CATÁLOGO"].astype(str).str.strip() != ""]

                        st.caption(f"**Status de preenchimento** — {len(preenchidos_ab)} de {len(df_editado_ab)} obra(s) já com `CATÁLOGO`:")
                        render_status_table(
                            ["Título", "Catálogo"],
                            [
                                {
                                    "preenchido": bool(str(row["CATÁLOGO"]).strip()),
                                    "Título": row["TÍTULO DA MUSICA"],
                                    "Catálogo": row["CATÁLOGO"] or "—",
                                }
                                for _, row in df_editado_ab.iterrows()
                            ],
                            status_key="preenchido",
                            label_key="Título",
                            max_height="200px",
                            translucent=False,
                        )

                        col_save1_ab, col_save2_ab = st.columns(2)

                        with col_save1_ab:
                            xlsx_template_ab = df_to_xlsx_bytes(df_editado_ab)
                            st.download_button(
                                "⬇️ Baixar template de catálogo (XLSX)",
                                data=xlsx_template_ab,
                                file_name=f"template_catalogo_abramus_{period_suffix}.xlsx",
                                mime=XLSX_MIME,
                                type="secondary"
                            )

                        with col_save2_ab:
                            if gh_config_mapping_ab is None:
                                st.caption("💾 Salvar direto na base de catálogo não está configurado neste ambiente.")
                            else:
                                if st.button(
                                    f"💾 Salvar {len(preenchidos_ab)} obra(s) na base",
                                    type="primary",
                                    disabled=preenchidos_ab.empty,
                                    key=f"btn_save_{editor_key_ab}",
                                ):
                                    try:
                                        df_novas_linhas_ab = preenchidos_ab[colunas_mapeamento_abramus]
                                        save_linhas_no_mapeamento(
                                            gh_config_mapping_ab,
                                            df_novas_linhas_ab,
                                            commit_message=f"data: adiciona {df_novas_linhas_ab['TÍTULO DA MUSICA'].nunique()} obra(s) ao catálogo ABRAMUS via app",
                                            path=GITHUB_MAPPING_PATH_ABRAMUS,
                                            dedup_cols=["CÓD. OBRA", "CÓD FONOGRAMA"],
                                            count_col="TÍTULO DA MUSICA",
                                            count_label="obra(s)",
                                            item_label="linha(s)",
                                        )
                                    except Exception as e:
                                        st.error(f"❌ Erro ao salvar no GitHub: {e}")

                    else:
                        st.caption(
                            "Envie o CSV/XLSX (baixado na aba de edição, ou de outro processamento), já com "
                            "`CATÁLOGO` preenchido, para adicionar várias obras de uma vez."
                        )

                        if gh_config_mapping_ab is None:
                            st.caption("💾 Importar direto para a base de catálogo não está configurado neste ambiente.")
                        else:
                            arquivo_importado_ab = st.file_uploader(
                                "Selecione o template preenchido (.csv ou .xlsx)",
                                type=["csv", "xlsx"],
                                key=f"upload_template_abramus_{period_suffix}",
                            )

                            if arquivo_importado_ab is not None:
                                try:
                                    if arquivo_importado_ab.name.lower().endswith(".csv"):
                                        df_importado_ab = pd.read_csv(arquivo_importado_ab, sep=None, engine="python", dtype=str, encoding="utf-8-sig")
                                    else:
                                        df_importado_ab = pd.read_excel(arquivo_importado_ab, dtype=str)
                                    df_importado_ab.columns = [c.strip() for c in df_importado_ab.columns]

                                    colunas_faltando_ab = [c for c in colunas_mapeamento_abramus if c not in df_importado_ab.columns]
                                    if colunas_faltando_ab:
                                        st.error(f"❌ Colunas faltando no arquivo importado: {colunas_faltando_ab}")
                                        st.caption(f"Colunas encontradas no arquivo: {list(df_importado_ab.columns)}")
                                    else:
                                        df_importado_preenchido_ab = df_importado_ab[
                                            df_importado_ab["CATÁLOGO"].astype(str).str.strip() != ""
                                        ]
                                        st.info(f"📄 {len(df_importado_preenchido_ab)} de {len(df_importado_ab)} linha(s) têm `CATÁLOGO` preenchido.")

                                        render_status_table(
                                            ["Título", "Catálogo"],
                                            [
                                                {
                                                    "preenchido": bool(str(row["CATÁLOGO"]).strip()),
                                                    "Título": row["TÍTULO DA MUSICA"],
                                                    "Catálogo": row["CATÁLOGO"] or "—",
                                                }
                                                for _, row in df_importado_ab.iterrows()
                                            ],
                                            status_key="preenchido",
                                            label_key="Título",
                                            max_height="200px",
                                            translucent=False,
                                        )

                                        if st.button(
                                            f"💾 Salvar {len(df_importado_preenchido_ab)} obra(s) importada(s) na base",
                                            type="primary",
                                            disabled=df_importado_preenchido_ab.empty,
                                            key=f"btn_save_import_abramus_{period_suffix}",
                                        ):
                                            try:
                                                df_novas_linhas_ab = df_importado_preenchido_ab[colunas_mapeamento_abramus].copy()
                                                save_linhas_no_mapeamento(
                                                    gh_config_mapping_ab,
                                                    df_novas_linhas_ab,
                                                    commit_message=(
                                                        f"data: importa {df_novas_linhas_ab['TÍTULO DA MUSICA'].nunique()} obra(s) "
                                                        f"ao catálogo ABRAMUS via app (upload em massa)"
                                                    ),
                                                    path=GITHUB_MAPPING_PATH_ABRAMUS,
                                                    dedup_cols=["CÓD. OBRA", "CÓD FONOGRAMA"],
                                                    count_col="TÍTULO DA MUSICA",
                                                    count_label="obra(s)",
                                                    item_label="linha(s)",
                                                )
                                            except Exception as e:
                                                st.error(f"❌ Erro ao salvar no GitHub: {e}")
                                except Exception as e:
                                    st.error(f"❌ Erro ao ler o arquivo importado: {e}")

                    # --- SEÇÃO REPRTOIR (ABRAMUS) ---
                    st.markdown("---")
                    st.subheader("🔎 Buscar no Reprtoir")
                    if not REPRTOIR_DISPONIVEL:
                        st.info(REPRTOIR_MSG_DESATIVADO)
                    else:
                        st.caption("Consulta a API do Reprtoir para identificar obras não mapeadas via ISWC ou título+autores.")
                        _rep_key_ab = f"reprtoir_abramus_{period_suffix}"
                        if st.button("🔎 Buscar no Reprtoir"):
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
                            preview_dataframe(
                                _df_com_rep[_cols_rep_disp].sort_values("CONFIANÇA_REPRTOIR_%", ascending=False))
                            _xlsx_rep = df_to_xlsx_bytes(_df_com_rep[_cols_rep_disp])
                            st.download_button("⬇️ Baixar resultados Reprtoir (XLSX)", data=_xlsx_rep, file_name=f"reprtoir_abramus_{period_suffix}.xlsx", mime=XLSX_MIME)

                else:
                    st.success("✅ Todas as obras foram mapeadas com sucesso!")

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
        _uploaded_base_so = st.file_uploader("Upload da base de mapeamento Sony (.xlsx)", type=["xlsx"])
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
        _uploaded_report_so = st.file_uploader("Upload do relatório SONY (.xlsx)", type=["xlsx"])
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

            st.success("✅ Processamento concluído!")
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
                xlsx_bytes = df_to_xlsx_bytes(df_grouped)
                st.download_button(
                    "⬇️ Baixar resultado agrupado (XLSX)",
                    data=xlsx_bytes,
                    file_name=f"relatorio_agrupado_sony_{ano_selecionado}_{mes_num_selecionado:02d}.xlsx",
                    mime=XLSX_MIME,
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
                preview_dataframe(df_detalhado_export)

                # Download detalhado
                xlsx_detalhado = df_to_xlsx_bytes(df_detalhado_export)
                st.download_button(
                    "⬇️ Baixar relatório DETALHADO com todas as músicas (XLSX)",
                    data=xlsx_detalhado,
                    file_name=f"relatorio_detalhado_sony_{ano_selecionado}_{mes_num_selecionado:02d}.xlsx",
                    mime=XLSX_MIME,
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

                    preview_dataframe(df_preview)
                    
                    xlsx_nao_mapeadas = df_to_xlsx_bytes(df_preview)
                    st.download_button(
                        "⬇️ Baixar músicas não mapeadas (XLSX)",
                        data=xlsx_nao_mapeadas,
                        file_name=f"obras_nao_mapeadas_sony_{ano_selecionado}_{mes_num_selecionado:02d}.xlsx",
                        mime=XLSX_MIME,
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
                                
                                preview_dataframe(df_preview_sug)
                                
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
                            
                            xlsx_completo = df_to_xlsx_bytes(df_download_completo)

                            st.info(f"📊 Este arquivo contém **{len(df_download_completo)} músicas** ({len(df_com_sugestao)} com sugestão + {len(df_sem_sugestao)} sem sugestão)")

                            st.download_button(
                                "⬇️ Baixar TODAS as músicas não mapeadas (com e sem sugestões)",
                                data=xlsx_completo,
                                file_name=f"obras_completo_sony_{ano_selecionado}_{mes_num_selecionado:02d}.xlsx",
                                mime=XLSX_MIME,
                                type="primary"
                            )
                        
                        else:
                            st.warning("⚠️ Coluna 'Writer' não encontrada na base de mapeamento.")

                    # --- SEÇÃO REPRTOIR (SONY) ---
                    st.markdown("---")
                    st.subheader("🔎 Buscar no Reprtoir")
                    if not REPRTOIR_DISPONIVEL:
                        st.info(REPRTOIR_MSG_DESATIVADO)
                    else:
                        st.caption("Consulta a API do Reprtoir para identificar músicas não mapeadas via título+autores.")
                        _rep_key_so = f"reprtoir_sony_{ano_selecionado}_{mes_num_selecionado:02d}"
                        if st.button("🔎 Buscar no Reprtoir"):
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
                            preview_dataframe(
                                _df_com_rep[_cols_rep_disp].sort_values("CONFIANÇA_REPRTOIR_%", ascending=False))
                            _xlsx_rep = df_to_xlsx_bytes(_df_com_rep[_cols_rep_disp])
                            st.download_button("⬇️ Baixar resultados Reprtoir (XLSX)", data=_xlsx_rep, file_name=f"reprtoir_sony_{ano_selecionado}_{mes_num_selecionado:02d}.xlsx", mime=XLSX_MIME)

                else:
                    st.success("✅ Todas as músicas foram mapeadas com sucesso!")

            else:
                st.warning("Coluna 'RoyAmt' não encontrada no relatório.")
                st.dataframe(df_out, use_container_width=True, height=520)

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
        _uploaded_base_vi = st.file_uploader("Upload da base de catálogo Irmãos Vitale (.xlsx)", type=["xlsx"])
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
            type=["xls"], accept_multiple_files=True)
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
            st.success("✅ Processamento concluído!")
            st.subheader("Resultado Agrupado por Catálogo")
            df_grouped = (
                df_all.groupby("CATÁLOGO", as_index=False)["VALOR"].sum()
                .sort_values("VALOR", ascending=False)
                .rename(columns={"VALOR": "Valor Repassado"})
            )
            st.dataframe(df_grouped, use_container_width=True, height=520)

            total_valor = df_grouped["Valor Repassado"].sum()
            st.markdown(f"**Total Repassado: R$ {total_valor:,.2f}**")

            xlsx_bytes = df_to_xlsx_bytes(df_grouped)
            st.download_button(
                "⬇️ Baixar resultado agrupado (XLSX)",
                data=xlsx_bytes,
                file_name=f"relatorio_agrupado_vitale_{ano_selecionado}_{tri_num_selecionado}T.xlsx",
                mime=XLSX_MIME,
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

            preview_dataframe(df_detalhado)
            xlsx_det = df_to_xlsx_bytes(df_detalhado)
            st.download_button(
                "⬇️ Baixar relatório DETALHADO (XLSX)",
                data=xlsx_det,
                file_name=f"relatorio_detalhado_vitale_{ano_selecionado}_{tri_num_selecionado}T.xlsx",
                mime=XLSX_MIME, type="primary",
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
                preview_dataframe(df_nm_grp)
                xlsx_nm = df_to_xlsx_bytes(df_nm_grp)
                st.download_button(
                    "⬇️ Baixar obras não mapeadas (XLSX)",
                    data=xlsx_nm,
                    file_name=f"obras_nao_mapeadas_vitale_{ano_selecionado}_{tri_num_selecionado}T.xlsx",
                    mime=XLSX_MIME, type="secondary",
                )
            else:
                st.success("✅ Todas as obras foram mapeadas com sucesso!")

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
        _uploaded_base_ig = st.file_uploader("Upload da base de mapeamento Ingrooves (.xlsx)", type=["xlsx"])
        if _uploaded_base_ig is None:
            st.info("Aguardando upload da base de mapeamento.")
            st.stop()
        base_source_ingrooves = _uploaded_base_ig
        st.success("✅ Base de mapeamento carregada via upload.")

    # --- Editar base de mapeamento completa ---
    with st.expander("✏️ Editar base de mapeamento completa"):
        gh_config_mapping = get_github_config()
        sha_mapping = None
        df_mapping_full = None

        if gh_config_mapping is not None:
            try:
                df_mapping_full, sha_mapping = github_fetch_mapping(gh_config_mapping)
            except Exception as e:
                st.error(f"❌ Erro ao buscar mapeamento no GitHub: {e}")
        elif isinstance(base_source_ingrooves, str) and os.path.exists(base_source_ingrooves):
            try:
                df_mapping_full = pd.read_excel(base_source_ingrooves, dtype=str)
                df_mapping_full.columns = [c.strip() for c in df_mapping_full.columns]
            except Exception as e:
                st.error(f"❌ Erro ao carregar base de mapeamento: {e}")
        else:
            st.caption("Edição indisponível: nem GitHub configurado, nem arquivo local encontrado (base veio de upload).")

        if df_mapping_full is not None:
            st.caption(
                f"{len(df_mapping_full)} registro(s). Use a lupa no canto superior da tabela para buscar "
                "por artista, música, ISRC etc. Também dá para adicionar ou apagar linhas."
            )
            df_mapping_editado = st.data_editor(
                df_mapping_full,
                use_container_width=True,
                height=400,
                num_rows="dynamic",
                key="editor_mapping_completo",
                hide_index=True,
            )

            if gh_config_mapping is not None:
                if st.button("💾 Salvar alterações na base de mapeamento", type="primary"):
                    try:
                        with st.spinner("Salvando no GitHub..."):
                            github_save_mapping(
                                gh_config_mapping,
                                df_mapping_editado,
                                sha_mapping,
                                commit_message="data: edita base de mapeamento Ingrooves via app",
                            )
                        st.success("✅ Base de mapeamento atualizada! O app vai reiniciar em instantes.")
                    except Exception as e:
                        st.error(f"❌ Erro ao salvar no GitHub: {e}")
            else:
                if st.button("💾 Salvar alterações na base de mapeamento (arquivo local)", type="primary"):
                    try:
                        df_mapping_editado.to_excel(base_source_ingrooves, index=False)
                        st.success("✅ Base de mapeamento salva localmente!")
                    except Exception as e:
                        st.error(f"❌ Erro ao salvar localmente: {e}")

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
        _uploaded_report_ig = st.file_uploader("Upload do relatório Ingrooves (Nas_Nuvens_Catalog_*_DSR.xlsx)", type=["xlsx"])
        if _uploaded_report_ig is None:
            st.info("Aguardando upload do relatório.")
            st.stop()
        st.success(f"✅ Arquivo `{_uploaded_report_ig.name}` carregado.")
        report_source_ingrooves = _uploaded_report_ig
        ano_selecionado = 0
        mes_num_selecionado = 0

    # Chave do período atual, usada para: (1) cachear o resultado no session_state
    # sobrevivendo a reruns causados pela edição do data_editor, e (2) nomear
    # arquivos/widgets de forma estável.
    if periods:
        period_suffix = f"{ano_selecionado}_{mes_num_selecionado:02d}"
    else:
        period_suffix = re.sub(r"[^A-Za-z0-9_-]", "_", getattr(report_source_ingrooves, "name", "upload"))

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

            # Guarda o resultado no session_state: a edição do data_editor abaixo
            # dispara reruns da página, e sem isso o app voltaria pra tela inicial
            # (o "if st.button" só é True no exato clique, não nos reruns seguintes).
            st.session_state["ingrooves_result"] = {
                "period_suffix": period_suffix,
                "df_out": df_out,
                "mask_nt": mask_nt,
                "original_total": original_total,
                "discounted_total": discounted_total,
                "total_withheld": total_withheld,
            }
        except Exception as e:
            st.error(f"❌ Erro ao processar: {e}")
            import traceback
            st.code(traceback.format_exc())

    # --- Renderização dos resultados (fora do botão, para sobreviver a reruns) ---
    resultado = st.session_state.get("ingrooves_result")
    if resultado and resultado["period_suffix"] == period_suffix:
        df_out = resultado["df_out"]
        mask_nt = resultado["mask_nt"]
        original_total = resultado["original_total"]
        discounted_total = resultado["discounted_total"]
        total_withheld = resultado["total_withheld"]

        st.success("✅ Processamento concluído!")
        st.write(f"O valor Original é **USD {original_total:,.2f}**")
        st.write(f"O total de withholding aplicado (30% EUA) é **USD {total_withheld:,.2f}**")
        st.write(f":red[O valor Net menos withholding é **USD {discounted_total:,.2f}**]")

        fx_rate_ingrooves = st.number_input(
            "Taxa cambial (USD → BRL)",
            value=0.0,
            min_value=0.0,
            format="%.4f",
            key=f"fx_rate_ingrooves_{period_suffix}",
        )
        if fx_rate_ingrooves > 0:
            st.write(f":green[O valor Net menos withholding convertido é **BRL {discounted_total * fx_rate_ingrooves:,.2f}**]")
        else:
            st.caption("Informe a taxa cambial acima para ver os valores das tabelas também em BRL.")

        gh_config = get_github_config()
        colunas_mapeamento = ["Artist", "Label", "Album Title", "Song", "ISRC", "Tag_Artista"]

        df_nao_mapeadas_raw = df_out[(df_out["CATÁLOGO"] == "") & (~mask_nt)].copy()
        # Linhas sem nome de artista não são "não mapeadas": não há o que mapear.
        # Separadas aqui porque groupby("Artist") descarta silenciosamente valores nulos.
        mask_sem_artist = df_nao_mapeadas_raw["Artist"].isna() | (df_nao_mapeadas_raw["Artist"].astype(str).str.strip() == "")
        df_sem_artist = df_nao_mapeadas_raw[mask_sem_artist]
        df_nao_mapeadas = df_nao_mapeadas_raw[~mask_sem_artist]

        tab_agrupado, tab_detalhado, tab_nao_mapeados = st.tabs([
            "📊 Agrupado por Catálogo", "📋 Detalhado", "🔍 Não Mapeados"
        ])

        with tab_agrupado:
            df_grouped = df_out.groupby("CATÁLOGO", as_index=False)["Net Dollars after Fees"].sum()
            df_grouped = df_grouped.sort_values("Net Dollars after Fees", ascending=False)
            df_grouped = df_grouped.rename(columns={"Net Dollars after Fees": "Net Dollars"})

            if fx_rate_ingrooves > 0:
                df_grouped["Net Dollars BRL"] = df_grouped["Net Dollars"] * fx_rate_ingrooves
                headers_agrupado = ["Catálogo", "Net Dollars (USD)", "Net Dollars (BRL)"]
                rows_agrupado = [
                    simple_row([
                        r["CATÁLOGO"] or "(sem catálogo)",
                        f"USD {r['Net Dollars']:,.2f}",
                        f"BRL {r['Net Dollars BRL']:,.2f}",
                    ])
                    for _, r in df_grouped.iterrows()
                ]
            else:
                headers_agrupado = ["Catálogo", "Net Dollars (USD)"]
                rows_agrupado = [
                    simple_row([r["CATÁLOGO"] or "(sem catálogo)", f"USD {r['Net Dollars']:,.2f}"])
                    for _, r in df_grouped.iterrows()
                ]

            render_html_table(
                headers_agrupado,
                rows_agrupado,
                max_height="480px",
                translucent=False,
            )

            total_net = df_grouped["Net Dollars"].sum()
            if fx_rate_ingrooves > 0:
                st.markdown(f"**Total Net Dollars: USD {total_net:,.2f} | BRL {total_net * fx_rate_ingrooves:,.2f}**")
            else:
                st.markdown(f"**Total Net Dollars: USD {total_net:,.2f}**")

            xlsx_bytes = df_to_xlsx_bytes(df_grouped)
            st.download_button(
                "⬇️ Baixar resultado agrupado (XLSX)",
                data=xlsx_bytes,
                file_name=f"relatorio_agrupado_ingrooves_{period_suffix}.xlsx",
                mime=XLSX_MIME,
            )

        with tab_detalhado:
            colunas_detalhadas = [
                "CATÁLOGO", "Artist", "Song", "Label", "Album Title", "ISRC",
                "Territory", "Sales Description", "Net Dollars after Fees"
            ]
            colunas_detalhadas_disp = [c for c in colunas_detalhadas if c in df_out.columns]
            df_detalhado_export = df_out[colunas_detalhadas_disp].copy()
            df_detalhado_export = df_detalhado_export.rename(columns={"Net Dollars after Fees": "Net Dollars after Fees (USD)"})
            if fx_rate_ingrooves > 0:
                df_detalhado_export["Net Dollars after Fees (BRL)"] = df_detalhado_export["Net Dollars after Fees (USD)"] * fx_rate_ingrooves
            df_detalhado_export = df_detalhado_export.sort_values(
                ["CATÁLOGO", "Net Dollars after Fees (USD)"], ascending=[True, False]
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

            preview_dataframe(df_detalhado_export)

            xlsx_detalhado = df_to_xlsx_bytes(df_detalhado_export)
            st.download_button(
                "⬇️ Baixar relatório DETALHADO com todas as faixas (XLSX)",
                data=xlsx_detalhado,
                file_name=f"relatorio_detalhado_ingrooves_{period_suffix}.xlsx",
                mime=XLSX_MIME,
                type="primary"
            )

        with tab_nao_mapeados:
            if len(df_sem_artist) > 0:
                total_sem_artist = df_sem_artist["Net Dollars after Fees"].sum()
                st.info(
                    f"ℹ️ **{len(df_sem_artist)} linha(s)** do relatório vieram sem nome de artista preenchido "
                    f"(não é possível mapear sem essa informação) | **Total: USD {total_sem_artist:,.2f}**"
                )

            if len(df_nao_mapeadas) > 0:
                df_nm_grp = df_nao_mapeadas.groupby("Artist", as_index=False)["Net Dollars after Fees"].sum()
                total_nao_mapeado = df_nm_grp["Net Dollars after Fees"].sum()
                st.warning(f"⚠️ **{len(df_nm_grp)} artistas únicos** não foram encontrados na base de mapeamento | **Total: USD {total_nao_mapeado:,.2f}**")
            elif len(df_sem_artist) == 0:
                st.success("✅ Todos os artistas foram mapeados com sucesso!")

            st.markdown("---")
            render_ultima_gravacao(
                gh_config, GITHUB_MAPPING_PATH,
                state_key=f"ingrooves_{period_suffix}", item_label="faixa(s)",
            )
            modo_resolucao = st.radio(
                "Como preencher o `Tag_Artista`?",
                ["✏️ Editar na tela", "📤 Importar arquivo preenchido"],
                horizontal=True,
                key=f"modo_resolucao_{period_suffix}",
            )

            if modo_resolucao == "✏️ Editar na tela":
                if len(df_nao_mapeadas) == 0:
                    st.caption("Nenhum artista pendente neste relatório.")
                else:
                    # Template no mesmo formato da planilha de mapeamento (Artist, Label, Album Title,
                    # Song, ISRC, Tag_Artista), editável e pronto para preencher/colar em mapping-artistas-ingrooves.xlsx
                    colunas_template = ["Artist", "Label", "Album Title", "Song", "ISRC"]
                    colunas_template_disp = [c for c in colunas_template if c in df_nao_mapeadas.columns]
                    df_template = df_nao_mapeadas[colunas_template_disp].drop_duplicates().sort_values("Artist").reset_index(drop=True)
                    df_template["Tag_Artista"] = ""

                    st.markdown(
                        "**Preencha `Tag_Artista`** — mesma estrutura da planilha de mapeamento, "
                        "pronta para salvar direto ou baixar e colar em `mapping-artistas-ingrooves.xlsx`:"
                    )

                    editor_key = f"editor_ingrooves_{period_suffix}"
                    df_editado = st.data_editor(
                        df_template,
                        use_container_width=True,
                        height=300,
                        key=editor_key,
                        disabled=colunas_template_disp,
                        hide_index=True,
                    )

                    preenchidos = df_editado[df_editado["Tag_Artista"].astype(str).str.strip() != ""]

                    artistas_status = df_editado.drop_duplicates(subset=["Artist"])
                    st.caption(f"**Status de preenchimento** — {len(preenchidos)} de {len(df_editado)} faixa(s) já com `Tag_Artista`:")
                    render_status_table(
                        ["Artista", "Tag_Artista"],
                        [
                            {
                                "preenchido": bool(str(row["Tag_Artista"]).strip()),
                                "Artist": row["Artist"],
                                "Tag_Artista": row["Tag_Artista"] or "—",
                            }
                            for _, row in artistas_status.iterrows()
                        ],
                        status_key="preenchido",
                        label_key="Artist",
                        max_height="200px",
                        translucent=False,
                    )

                    col_save1, col_save2 = st.columns(2)

                    with col_save1:
                        xlsx_template = df_to_xlsx_bytes(df_editado)
                        st.download_button(
                            "⬇️ Baixar template de mapeamento (XLSX)",
                            data=xlsx_template,
                            file_name=f"template_mapeamento_ingrooves_{period_suffix}.xlsx",
                            mime=XLSX_MIME,
                            type="secondary"
                        )

                    with col_save2:
                        if gh_config is None:
                            st.caption("💾 Salvar direto na base de mapeamento não está configurado neste ambiente.")
                        else:
                            if st.button(
                                f"💾 Salvar {len(preenchidos)} faixa(s) no mapeamento",
                                type="primary",
                                disabled=preenchidos.empty,
                                key=f"btn_save_{editor_key}",
                            ):
                                try:
                                    df_novas_linhas = preenchidos[colunas_mapeamento]
                                    save_linhas_no_mapeamento(
                                        gh_config,
                                        df_novas_linhas,
                                        commit_message=f"data: adiciona {df_novas_linhas['Artist'].nunique()} artista(s) ao mapeamento Ingrooves via app",
                                    )
                                except Exception as e:
                                    st.error(f"❌ Erro ao salvar no GitHub: {e}")

            else:
                st.caption(
                    "Envie o CSV/XLSX (baixado na aba de edição, ou de outro processamento), já com "
                    "`Tag_Artista` preenchido, para adicionar várias faixas de uma vez."
                )

                if gh_config is None:
                    st.caption("💾 Importar direto para o mapeamento não está configurado neste ambiente.")
                else:
                    arquivo_importado = st.file_uploader(
                        "Selecione o template preenchido (.csv ou .xlsx)",
                        type=["csv", "xlsx"],
                        key=f"upload_template_{period_suffix}",
                    )

                    if arquivo_importado is not None:
                        try:
                            if arquivo_importado.name.lower().endswith(".csv"):
                                # sep=None + engine="python" detecta o delimitador (";" ou ",", conforme o
                                # Excel/config regional de quem salvou o arquivo) em vez de assumir ";" fixo —
                                # com separador errado, o pandas lia a linha inteira como uma única coluna
                                # e a checagem de colunas abaixo falhava. encoding utf-8-sig remove o BOM
                                # que o Excel grava em CSVs "UTF-8", que também gruda no nome da 1ª coluna.
                                df_importado = pd.read_csv(arquivo_importado, sep=None, engine="python", dtype=str, encoding="utf-8-sig")
                            else:
                                df_importado = pd.read_excel(arquivo_importado, dtype=str)
                            df_importado.columns = [c.strip() for c in df_importado.columns]

                            colunas_faltando = [c for c in colunas_mapeamento if c not in df_importado.columns]
                            if colunas_faltando:
                                st.error(f"❌ Colunas faltando no arquivo importado: {colunas_faltando}")
                                st.caption(f"Colunas encontradas no arquivo: {list(df_importado.columns)}")
                            else:
                                df_importado_preenchido = df_importado[
                                    df_importado["Tag_Artista"].astype(str).str.strip() != ""
                                ]
                                st.info(f"📄 {len(df_importado_preenchido)} de {len(df_importado)} linha(s) têm `Tag_Artista` preenchido.")

                                artistas_status_import = df_importado.drop_duplicates(subset=["Artist"])
                                st.caption(
                                    f"**Status de preenchimento (arquivo importado)** — "
                                    f"{artistas_status_import['Tag_Artista'].astype(str).str.strip().ne('').sum()} de "
                                    f"{len(artistas_status_import)} artista(s) já com `Tag_Artista`:"
                                )
                                render_status_table(
                                    ["Artista", "Tag_Artista"],
                                    [
                                        {
                                            "preenchido": bool(str(row["Tag_Artista"]).strip()),
                                            "Artist": row["Artist"],
                                            "Tag_Artista": row["Tag_Artista"] or "—",
                                        }
                                        for _, row in artistas_status_import.iterrows()
                                    ],
                                    status_key="preenchido",
                                    label_key="Artist",
                                    max_height="200px",
                                    translucent=False,
                                )

                                if st.button(
                                    f"💾 Salvar {len(df_importado_preenchido)} faixa(s) importada(s) no mapeamento",
                                    type="primary",
                                    disabled=df_importado_preenchido.empty,
                                    key=f"btn_save_import_{period_suffix}",
                                ):
                                    try:
                                        df_novas_linhas = df_importado_preenchido[colunas_mapeamento].copy()
                                        save_linhas_no_mapeamento(
                                            gh_config,
                                            df_novas_linhas,
                                            commit_message=(
                                                f"data: importa {df_novas_linhas['Artist'].nunique()} artista(s) "
                                                f"ao mapeamento Ingrooves via app (upload em massa)"
                                            ),
                                        )
                                    except Exception as e:
                                        st.error(f"❌ Erro ao salvar no GitHub: {e}")
                        except Exception as e:
                            st.error(f"❌ Erro ao ler o arquivo importado: {e}")