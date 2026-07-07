"""
Organizador de Comprovantes — ABRAMUS

Recebe o .zip de comprovantes baixado do portal da ABRAMUS, identifica de
qual conta/artista é cada arquivo (pelo código ECAD no nome) e devolve um
.zip já organizado na estrutura de pastas usada na base
(Artista\\ABRAMUS\\Conta\\Ano\\Mês\\arquivo), pronto pra extrair e colar.

Não escreve em lugar nenhum da base, não mexe em credencial nenhuma, e não
guarda nada do que for enviado — tudo é processado em memória e descartado
ao fim da sessão.

O mapeamento (data/mapping/abramus_credentials_map.json) só tem código
ECAD/ABRAMUS, nome de artista/conta e caminho relativo — sem login nem senha.
Precisa ser regerado sempre que uma credencial nova for cadastrada no
rpa-royalties (fora do escopo desta página).
"""

import html
import io
import json
import re
import zipfile
from collections import defaultdict
from datetime import datetime
from pathlib import Path

import pdfplumber
import streamlit as st

st.set_page_config(page_title="Organizador de Comprovantes — ABRAMUS", page_icon="🗂️", layout="wide")

MAPPING_PATH = Path(__file__).resolve().parents[1] / "data" / "mapping" / "abramus_credentials_map.json"

PT_MONTHS_SHORT = {
    1: "Jan", 2: "Fev", 3: "Mar", 4: "Abr",
    5: "Mai", 6: "Jun", 7: "Jul", 8: "Ago",
    9: "Set", 10: "Out", 11: "Nov", 12: "Dez",
}

_CODE_RE = re.compile(r"_201_0*(\d+)")
_YM_RE = re.compile(r"^(?P<y>20\d{2})_(?P<m>\d{1,2})[_\-]")

_ABRAMUS_CODE_RE = re.compile(r"ABRAMUS\s*(\d+)", re.IGNORECASE)
_ECAD_CODE_RE = re.compile(r"ECAD\s*(\d+)", re.IGNORECASE)
_LEFT_COLUMN_FRACTION = 0.68


@st.cache_data
def load_mapping_rows() -> list:
    if not MAPPING_PATH.exists():
        return []
    return json.loads(MAPPING_PATH.read_text(encoding="utf-8"))


def build_ecad_index(rows: list) -> dict:
    """Só as ativas (com ecad_code) entram no índice usado pra reconhecer arquivo."""
    return {row["ecad_code"]: row for row in rows if row.get("ecad_code")}


def month_folder_name(year: int, month: int) -> str:
    mm = PT_MONTHS_SHORT.get(month, f"{month:02d}")
    return f"{month:02d}. {mm} {str(year)[-2:]}"


def extract_code(name: str):
    m = _CODE_RE.search(name)
    return m.group(1) if m else None


def extract_year_month(name: str):
    m = _YM_RE.match(name)
    if m:
        return int(m.group("y")), int(m.group("m"))
    return None, None


def extract_identity_from_pdf(pdf_bytes: bytes) -> dict:
    """Melhor esforço: lê a coluna esquerda da 1ª página e usa a linha
    'ABRAMUS<código>' como âncora pra achar titular/artista. Se não achar,
    devolve vazio — a pessoa vê só o código mesmo."""
    info = {"holder_name": None, "artist_name": None, "abramus_code": None}
    try:
        with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
            page = pdf.pages[0]
            left = page.crop((0, 0, page.width * _LEFT_COLUMN_FRACTION, page.height))
            text = left.extract_text() or ""
    except Exception:
        return info

    lines = [l.strip() for l in text.splitlines() if l.strip()]
    idx = next((i for i, l in enumerate(lines) if _ABRAMUS_CODE_RE.search(l)), None)
    if idx is None:
        return info

    m = _ABRAMUS_CODE_RE.search(lines[idx])
    if m:
        info["abramus_code"] = m.group(1)
    if idx - 1 >= 0:
        info["artist_name"] = lines[idx - 1]
    if idx - 2 >= 0:
        info["holder_name"] = lines[idx - 2]
    return info


def collect_zip_files(uploaded_zip: zipfile.ZipFile) -> list[tuple[str, bytes]]:
    """Extrai recursivamente: arquivos soltos e o conteúdo de zips aninhados
    (ex.: _REC.zip, _VCV.zip), sempre que reconhecer o padrão de código."""
    collected = []
    for item in uploaded_zip.namelist():
        if item.endswith("/"):
            continue
        name = item.rsplit("/", 1)[-1]
        if name.lower().endswith(".zip"):
            try:
                inner_bytes = uploaded_zip.read(item)
                with zipfile.ZipFile(io.BytesIO(inner_bytes)) as inner_zip:
                    for inner_item in inner_zip.namelist():
                        if inner_item.endswith("/"):
                            continue
                        inner_name = inner_item.rsplit("/", 1)[-1]
                        if extract_code(inner_name) is None:
                            continue
                        collected.append((inner_name, inner_zip.read(inner_item)))
            except zipfile.BadZipFile:
                continue
        elif extract_code(name) is not None:
            collected.append((name, uploaded_zip.read(item)))

    # dedup: mesmo nome de arquivo pode vir tanto solto quanto de dois zips
    # aninhados diferentes (ex.: zip individual + zip "mestre" da conta master)
    dedup = {}
    for name, content in collected:
        dedup[name] = content
    return list(dedup.items())


def render_html_table(headers: list[str], body_rows_html: list[str], max_height: str = "420px"):
    """Tabela HTML padrão do app: cabeçalho cinza translúcido + blur (tema-agnóstico,
    ao contrário de cor fixa ou variável CSS do Streamlit que não existe de verdade)."""
    thead_cells = "".join(f'<th style="text-align:left;padding:6px 10px;">{html.escape(h)}</th>' for h in headers)
    table_html = (
        f'<div style="max-height:{max_height}; overflow-y:auto; border:1px solid rgba(128,128,128,0.3); border-radius:6px;">'
        '<table style="width:100%; border-collapse:collapse; font-size:13px;">'
        '<thead style="position:sticky; top:0; background:rgba(128,128,128,0.15); backdrop-filter:blur(4px);">'
        f"<tr>{thead_cells}</tr></thead><tbody>" + "".join(body_rows_html) + "</tbody></table></div>"
    )
    st.markdown(table_html, unsafe_allow_html=True)


def simple_row(cells: list, style: str = "") -> str:
    tds = "".join(f'<td style="padding:6px 10px;">{html.escape(str(c))}</td>' for c in cells)
    return f'<tr style="{style}">{tds}</tr>'


def render_credentials_table(rows: list, query: str = ""):
    """Tabela com credenciais ativas 'acesas' e suspensas 'apagadas'."""
    q = query.strip().lower()
    filtered = [
        r for r in rows
        if not q or q in (r.get("artist") or "").lower() or q in (r.get("account") or "").lower()
    ]
    filtered = sorted(filtered, key=lambda r: (not r.get("active"), (r.get("artist") or "").lower()))

    rows_html = []
    for r in filtered:
        active = bool(r.get("active"))
        artist = html.escape(r.get("artist") or "")
        account = html.escape(r.get("account") or "")
        ecad = html.escape(r.get("ecad_code") or "—")
        if active:
            dot_color = "var(--text-success, #1D9E75)"
            text_style = "opacity: 1;"
            label = "ativa"
        else:
            dot_color = "var(--text-muted, #888780)"
            text_style = "opacity: 0.4;"
            label = "suspensa"
        rows_html.append(
            f'<tr style="{text_style}" title="{label}">'
            f'<td style="padding:6px 10px;">'
            f'<span style="display:inline-block;width:8px;height:8px;border-radius:50%;'
            f'background:{dot_color};margin-right:8px;"></span>{artist}</td>'
            f'<td style="padding:6px 10px;">{account}</td>'
            f'<td style="padding:6px 10px;font-family:monospace;">{ecad}</td>'
            f"</tr>"
        )

    render_html_table(["Artista", "Conta", "ECAD"], rows_html)
    st.caption(f"{len(filtered)} de {len(rows)} — 🟢 acesa = reconhece automático · apagada = ainda suspensa/sem código")


def build_coverage(rows: list, account_counter: dict) -> list:
    """Cruza as credenciais ativas com o que realmente apareceu nesse upload."""
    coverage = []
    for r in rows:
        if not r.get("active"):
            continue
        key = (r["artist"], r["account"])
        count = account_counter.get(key)
        coverage.append({
            "status": "✅ organizada" if count else "⚠️ não apareceu",
            "Artista": r["artist"],
            "Conta": r["account"],
            "Tipo": r.get("access_type") or "—",
            "Arquivos": count or 0,
        })
    # faltantes primeiro, pra chamar atenção
    coverage.sort(key=lambda c: (c["status"] != "⚠️ não apareceu", c["Artista"].lower()))
    return coverage


def organize(files: list[tuple[str, bytes]], mapping: dict):
    """Retorna (zip_bytes, resumo_por_conta, orfaos) onde orfaos é uma lista
    de dicts com código, arquivo de exemplo e melhor palpite de identidade."""
    out_buffer = io.BytesIO()
    account_counter = defaultdict(int)
    orphan_codes = defaultdict(list)  # code -> [(name, bytes), ...]

    with zipfile.ZipFile(out_buffer, "w", zipfile.ZIP_DEFLATED) as out_zip:
        for name, content in files:
            code = extract_code(name)
            year, month = extract_year_month(name)
            if not code or not year or not month:
                continue

            cred = mapping.get(code)
            if cred:
                base = cred["relative_path"]
                account_counter[(cred["artist"], cred["account"])] += 1
            else:
                base = f"_ORPHANS\\CODE_{code}"
                orphan_codes[code].append((name, content))

            dest = f"{base}\\{year}\\{month_folder_name(year, month)}\\{name}".replace("\\", "/")
            out_zip.writestr(dest, content)

    orphan_summary = []
    for code, entries in orphan_codes.items():
        pdf_entry = next((c for n, c in entries if n.lower().endswith(".pdf")), None)
        identity = extract_identity_from_pdf(pdf_entry) if pdf_entry else {}
        orphan_summary.append({
            "code": code,
            "arquivos": len(entries),
            "titular": identity.get("holder_name") or "?",
            "artista": identity.get("artist_name") or "?",
        })

    return out_buffer.getvalue(), account_counter, orphan_summary


def main():
    st.title("🗂️ Organizador de Comprovantes — ABRAMUS")
    st.caption(
        "Anexe o .zip de comprovantes baixado do portal da ABRAMUS. "
        "A página organiza tudo na estrutura de pastas da base e devolve "
        "um .zip pronto pra você extrair e colar direto no lugar certo."
    )

    rows = load_mapping_rows()
    if not rows:
        st.error(
            "Mapeamento de credenciais não encontrado ou vazio "
            f"(`{MAPPING_PATH}`). Fale com o Marcelo antes de usar esta página."
        )
        return
    mapping = build_ecad_index(rows)

    with st.expander(f"Ver credenciais cadastradas ({len(rows)})"):
        query = st.text_input("Buscar por artista ou conta", key="cred_search")
        render_credentials_table(rows, query)

    uploaded = st.file_uploader("Anexe o .zip de comprovantes", type="zip")
    if uploaded is None:
        return

    with st.spinner("Lendo e organizando os arquivos..."):
        try:
            with zipfile.ZipFile(uploaded) as z:
                files = collect_zip_files(z)
        except zipfile.BadZipFile:
            st.error("Não consegui abrir esse arquivo como .zip. Confira se o upload não corrompeu.")
            return

        if not files:
            st.warning("Nenhum arquivo reconhecido dentro do .zip (padrão esperado: `..._201_XXXXXXXX...`).")
            return

        out_bytes, account_counter, orphans = organize(files, mapping)

    st.success(f"{len(files)} arquivo(s) processado(s).")

    col1, col2 = st.columns(2)
    with col1:
        st.metric("Contas reconhecidas", len(account_counter))
    with col2:
        st.metric("Códigos não reconhecidos", len(orphans))

    if account_counter:
        st.subheader("Resumo por conta")
        render_html_table(
            ["Artista", "Conta", "Arquivos"],
            [simple_row([a, c, n]) for (a, c), n in sorted(account_counter.items())],
        )

    if orphans:
        st.subheader("⚠️ Códigos não reconhecidos")
        st.caption(
            "Foram incluídos no .zip dentro de `_ORPHANS`, pra nada se perder. "
            "Avise o Marcelo com o código e o titular/artista (quando identificado) "
            "pra ele cadastrar na base."
        )
        render_html_table(
            ["Código ECAD", "Arquivos", "Titular (palpite)", "Artista (palpite)"],
            [simple_row([o["code"], o["arquivos"], o["titular"], o["artista"]]) for o in orphans],
        )

    st.divider()
    st.subheader("Conferência — o que foi organizado neste envio")
    coverage = build_coverage(rows, account_counter)
    faltantes = [c for c in coverage if c["status"] == "⚠️ não apareceu"]
    if faltantes:
        st.warning(
            f"{len(faltantes)} conta(s) ativa(s) não apareceram neste .zip — "
            "confira manualmente se era esperado (ex.: conta sem movimento no mês)."
        )
    else:
        st.success("Todas as contas ativas apareceram neste envio.")
    render_html_table(
        ["Status", "Artista", "Conta", "Tipo", "Arquivos"],
        [simple_row([c["status"], c["Artista"], c["Conta"], c["Tipo"], c["Arquivos"]],
                    style="" if c["status"] == "✅ organizada" else "background: rgba(230,150,20,0.08);")
         for c in coverage],
    )

    st.divider()
    hoje = datetime.now().strftime("%Y-%m-%d")
    st.download_button(
        "⬇️ Baixar .zip organizado",
        data=out_bytes,
        file_name=f"comprovantes_organizados_{hoje}.zip",
        mime="application/zip",
        use_container_width=True,
    )
    st.caption(
        "Depois de baixar: extraia e cole o conteúdo direto em "
        "`Z:\\ROYALTY\\Royalties Statements_Historicals\\` — as pastas já vêm com o caminho certo."
    )


if __name__ == "__main__":
    main()
