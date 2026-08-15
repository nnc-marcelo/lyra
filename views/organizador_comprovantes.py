"""
Organizador de Comprovantes — ABRAMUS / UBC

Recebe o .zip de comprovantes baixado do portal (ABRAMUS ou UBC), identifica de
qual conta/artista é cada arquivo (pelo código ECAD no nome) e devolve um .zip
já organizado na estrutura de pastas usada na base
(Artista\\<ENTIDADE>\\Conta\\Ano\\Mês\\arquivo), pronto pra extrair e colar.

A entidade é escolhida num seletor na barra lateral — o fluxo é idêntico pras
duas; só muda o padrão de código no nome do arquivo e o mapeamento de
credenciais usado.

Não escreve em lugar nenhum da base, não mexe em credencial nenhuma, e não
guarda nada do que for enviado — tudo é processado em memória e descartado ao
fim da sessão.

Os mapeamentos (data/mapping/{abramus,ubc}_credentials_map.json) só têm código
ECAD, nome de artista/conta e caminho relativo — sem login nem senha. Cada um
precisa ser regerado (pelos exporters export_{abramus,ubc}_mapping_to_lyra.py em
rpa-royalties) sempre que uma credencial nova for cadastrada na base.
"""

import html
import importlib.util
import io
import json
import re
import shutil
import sys
import zipfile
from collections import defaultdict
from datetime import datetime
from pathlib import Path

import pdfplumber
import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from utils.ui_components import render_html_table, simple_row, status_dot_html
from utils.page import setup_page

MAPPING_DIR = Path(__file__).resolve().parents[1] / "data" / "mapping"

PT_MONTHS_SHORT = {
    1: "Jan", 2: "Fev", 3: "Mar", 4: "Abr",
    5: "Mai", 6: "Jun", 7: "Jul", 8: "Ago",
    9: "Set", 10: "Out", 11: "Nov", 12: "Dez",
}

# ---------------------------------------------------------------------------
# Extração de código ECAD do nome do arquivo — específico por entidade
# ---------------------------------------------------------------------------

# ABRAMUS: código sempre no token _201_XXXXXXXX (demonstrativos e recibos).
_ABRAMUS_FILE_RE = re.compile(r"_201_0*(\d+)")
# UBC: demonstrativo nacional no token _093_XXXXXXXX. Os demais (INT, REC) não
# têm token de tipo — o código ECAD é o 4º campo separado por "_".
_UBC_FILE_RE = re.compile(r"_093_(\d+)")


def extract_code_abramus(name: str):
    m = _ABRAMUS_FILE_RE.search(name)
    return m.group(1) if m else None


def _extract_ubc_positional(name: str):
    """Pega o código ECAD do 4º campo do nome (…_<masterOrZeros>_<ECAD>_…).
    Vale tanto pra recibo (_REC) quanto pro demonstrativo internacional (_INT)."""
    parts = name.split("_")
    if len(parts) >= 4:
        candidate = parts[3].split(".")[0]
        try:
            return str(int(candidate))
        except ValueError:
            pass
    return None


def extract_code_ubc(name: str):
    m = _UBC_FILE_RE.search(name)
    if m:
        return str(int(m.group(1)))
    return _extract_ubc_positional(name)


# ---------------------------------------------------------------------------
# Palpite de identidade a partir do PDF — específico da ABRAMUS
# ---------------------------------------------------------------------------

_ABRAMUS_ANCHOR_RE = re.compile(r"ABRAMUS\s*(\d+)", re.IGNORECASE)
_LEFT_COLUMN_FRACTION = 0.68


def extract_identity_abramus(pdf_bytes: bytes, code=None) -> dict:
    """Melhor esforço: lê a coluna esquerda da 1ª página e usa a linha
    'ABRAMUS<código>' como âncora pra achar titular/artista. Se não achar,
    devolve vazio — a pessoa vê só o código mesmo. (`code` é ignorado aqui; existe
    só pra manter a assinatura igual à da UBC, que ancora pelo código ECAD.)"""
    info = {"holder_name": None, "artist_name": None, "abramus_code": None}
    try:
        with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
            page = pdf.pages[0]
            left = page.crop((0, 0, page.width * _LEFT_COLUMN_FRACTION, page.height))
            text = left.extract_text() or ""
    except Exception:
        return info

    lines = [l.strip() for l in text.splitlines() if l.strip()]
    idx = next((i for i, l in enumerate(lines) if _ABRAMUS_ANCHOR_RE.search(l)), None)
    if idx is None:
        return info

    m = _ABRAMUS_ANCHOR_RE.search(lines[idx])
    if m:
        info["abramus_code"] = m.group(1)
    if idx - 1 >= 0:
        info["artist_name"] = lines[idx - 1]
    if idx - 2 >= 0:
        info["holder_name"] = lines[idx - 2]
    return info


# ---------------------------------------------------------------------------
# Palpite de identidade a partir do PDF — específico da UBC
# ---------------------------------------------------------------------------
#
# A UBC entrega dois layouts de PDF, e o titular aparece de forma previsível em
# ambos — ancorado no código ECAD:
#
#   Demonstrativo do titular (..._093_...):
#       <TITULAR> CNPJ/CPF: ...            → titular (nome antes do rótulo)
#       <NOME ARTÍSTICO> COD ECAD: <cod>   → artista (trecho antes de "COD ECAD")
#
#   Recibo eletrônico (..._REC...):
#       <NOME>                             → titular (linha logo acima)
#       UBC:xxxx · ECAD:<cod> · CNPJ/CPF:  → âncora
#
# O recibo não traz nome artístico, então nesses casos artista fica vazio (vira
# "?"). Ancorar no código evita pegar por engano algum dos vários nomes de obra
# /executante que também aparecem na 1ª página do demonstrativo.

_UBC_DEM_ECAD_RE = re.compile(r"COD\s*ECAD:\s*0*(\d+)", re.IGNORECASE)
_UBC_REC_ECAD_RE = re.compile(r"ECAD:\s*0*(\d+)", re.IGNORECASE)


def extract_identity_ubc(pdf_bytes: bytes, code=None) -> dict:
    """Melhor esforço: acha titular (e artista, quando houver) na 1ª página,
    ancorando no código ECAD. Cobre demonstrativo e recibo. Se não achar,
    devolve vazio — a pessoa vê só o código mesmo."""
    info = {"holder_name": None, "artist_name": None, "ubc_code": None}
    try:
        with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
            text = pdf.pages[0].extract_text() or ""
    except Exception:
        return info

    lines = [l.strip() for l in text.splitlines() if l.strip()]
    want = str(int(code)) if code is not None else None

    # Layout 1: demonstrativo do titular — linha "<artista> COD ECAD: <cod>".
    for i, l in enumerate(lines):
        m = _UBC_DEM_ECAD_RE.search(l)
        if m and (want is None or str(int(m.group(1))) == want):
            info["ubc_code"] = str(int(m.group(1)))
            info["artist_name"] = l[:m.start()].strip() or None
            for j in range(i - 1, -1, -1):
                if "CNPJ/CPF" in lines[j].upper() or "CNPJ" in lines[j].upper():
                    holder = re.split(r"CNPJ", lines[j], maxsplit=1, flags=re.IGNORECASE)[0]
                    info["holder_name"] = holder.strip() or None
                    break
            return info

    # Layout 2: recibo eletrônico — nome na linha acima de "UBC:.. ECAD:<cod> .."
    for i, l in enumerate(lines):
        up = l.upper()
        if "ECAD:" in up and "UBC:" in up:
            m = _UBC_REC_ECAD_RE.search(l)
            if m and (want is None or str(int(m.group(1))) == want):
                info["ubc_code"] = str(int(m.group(1)))
                if i - 1 >= 0:
                    info["holder_name"] = lines[i - 1].strip() or None
                return info

    return info


# ---------------------------------------------------------------------------
# Configuração por entidade
# ---------------------------------------------------------------------------

ENTITIES = {
    "ABRAMUS": {
        "mapping_file": "abramus_credentials_map.json",
        "extract_code": extract_code_abramus,
        "folder": "ABRAMUS",
        "filename_hint": "..._201_XXXXXXXX...",
        "pdf_identity": extract_identity_abramus,
        "portal_id": None,  # schema do portal ABRAMUS difere; cadastro não automatizado aqui
    },
    "UBC": {
        "mapping_file": "ubc_credentials_map.json",
        "extract_code": extract_code_ubc,
        "folder": "UBC",
        "filename_hint": "..._093_XXXXXXXX... (nacional) ou ..._<ECAD>_INT/REC... (internacional)",
        "pdf_identity": extract_identity_ubc,
        "portal_id": "ubc_portal",  # cadastro direto habilitado (ver bloco "Cadastro de credencial")
    },
}


# ---------------------------------------------------------------------------
# Mapeamento de credenciais
# ---------------------------------------------------------------------------

@st.cache_data
def load_mapping_rows(mapping_path: str) -> list:
    p = Path(mapping_path)
    if not p.exists():
        return []
    return json.loads(p.read_text(encoding="utf-8"))


def build_ecad_index(rows: list) -> dict:
    """Só as ativas (com ecad_code) entram no índice usado pra reconhecer arquivo."""
    return {row["ecad_code"]: row for row in rows if row.get("ecad_code")}


def month_folder_name(year: int, month: int) -> str:
    mm = PT_MONTHS_SHORT.get(month, f"{month:02d}")
    return f"{month:02d}. {mm} {str(year)[-2:]}"


def extract_year_month(name: str):
    """Ano/mês no início do nome; fallback em qualquer posição, pra nomes
    prefixados (ex.: 'DEM. INTERNACIONAL(2026_05_...)')."""
    m = re.match(r"^(?P<y>20\d{2})_(?P<m>\d{1,2})[_\-]", name)
    if not m:
        m = re.search(r"(?P<y>20\d{2})_(?P<m>\d{1,2})[_\-]", name)
    if m:
        return int(m.group("y")), int(m.group("m"))
    return None, None


def collect_zip_files(uploaded_zip: zipfile.ZipFile, extract_code) -> list[tuple[str, bytes]]:
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
        text_style = "opacity: 1;" if active else "opacity: 0.4;"
        label = "ativa" if active else "suspensa"
        rows_html.append(
            f'<tr style="{text_style}" title="{label}">'
            f'<td style="padding:6px 10px;">{status_dot_html(active)}{artist}</td>'
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


def organize(files: list[tuple[str, bytes]], mapping: dict, extract_code, folder: str, pdf_identity):
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
                base = f"_ORPHANS\\{folder}\\CODE_{code}"
                orphan_codes[code].append((name, content))

            dest = f"{base}\\{year}\\{month_folder_name(year, month)}\\{name}".replace("\\", "/")
            out_zip.writestr(dest, content)

    orphan_summary = []
    for code, entries in orphan_codes.items():
        identity = {}
        if pdf_identity is not None:
            # tenta cada PDF do código; o demonstrativo traz titular+artista e o
            # recibo só titular. Guarda o 1º não-vazio como fallback, mas segue
            # procurando um completo (pros códigos que só têm recibo, ou cujo 1º
            # PDF é um ajuste/recibo sem nome artístico).
            for n, c in entries:
                if not n.lower().endswith(".pdf"):
                    continue
                cand = pdf_identity(c, code) or {}
                if not (cand.get("holder_name") or cand.get("artist_name")):
                    continue
                if cand.get("holder_name") and cand.get("artist_name"):
                    identity = cand
                    break
                if not identity:
                    identity = cand
        orphan_summary.append({
            "code": code,
            "arquivos": len(entries),
            "titular": identity.get("holder_name") or "?",
            "artista": identity.get("artist_name") or "?",
        })

    return out_buffer.getvalue(), account_counter, orphan_summary


# ---------------------------------------------------------------------------
# Cadastro de credencial — grava direto na fonte (rpa-royalties, repo irmão)
# ---------------------------------------------------------------------------
#
# A fonte de verdade das credenciais NÃO é o lyra: é
# rpa-royalties/config/portals/ubc_portal.json (repo privado, com login/senha).
# O lyra só lê um espelho sanitizado (data/mapping/ubc_credentials_map.json),
# gerado pelo exporter export_ubc_mapping_to_lyra.py.
#
# O cadastro daqui só faz sentido rodando LOCAL, com o rpa-royalties ao lado
# (é o uso real do app). Ele:
#   1) faz backup do ubc_portal.json,
#   2) adiciona a credencial nova (login master/unificado, SEM senha),
#   3) roda o exporter pra atualizar o mapa do lyra na hora.
# Nunca manuseia senha — contas UBC comuns usam o login master.

_RPA_ROOT = Path(__file__).resolve().parents[2] / "rpa-royalties"
UBC_PORTAL_FILE = _RPA_ROOT / "config" / "portals" / "ubc_portal.json"
UBC_EXPORTER = _RPA_ROOT / "tools" / "organizers" / "export_ubc_mapping_to_lyra.py"
ROYALTIES_PREFIX = "Z:\\ROYALTY\\Royalties Statements_Historicals\\"


def _rpa_ubc_available() -> bool:
    """Cadastro só é possível local, com o repo irmão e o exporter presentes."""
    return UBC_PORTAL_FILE.exists() and UBC_EXPORTER.exists()


def _load_ubc_portal():
    try:
        return json.loads(UBC_PORTAL_FILE.read_text(encoding="utf-8"))
    except Exception:
        return None


def _existing_ubc_ids() -> set:
    portal = _load_ubc_portal()
    if not portal:
        return set()
    return {c.get("id") for c in portal.get("credentials", []) if c.get("id")}


def _slugify_id(name: str, existing: set) -> str:
    base = re.sub(r"[^a-z0-9]", "", (name or "").lower()) or "ubc"
    i, cand = 1, f"{base}1"
    while cand in existing:
        i += 1
        cand = f"{base}{i}"
    return cand


def _suggest_ubc_path(artist: str, account: str) -> str:
    a = (artist or "").strip() or (account or "").strip() or "ARTISTA"
    acc = (account or "").strip() or a
    return f"{ROYALTIES_PREFIX}{a}\\UBC\\{acc}"


@st.cache_data(show_spinner=False)
def _base_folder_names() -> list:
    """Nomes das pastas de 1º nível da base (cacheado — Z:\\ pode ser de rede)."""
    base = Path(ROYALTIES_PREFIX)
    if not base.exists():
        return []
    try:
        return [f.name for f in base.iterdir() if f.is_dir()]
    except Exception:
        return []


def _find_artist_folders(artist: str) -> list:
    """Pastas na base cujo nome contém a 1ª palavra do artista — só dica visual."""
    term = (artist or "").strip().lower().split()
    if not term:
        return []
    first = term[0]
    return [n for n in _base_folder_names() if first in n.lower()][:6]


def _run_ubc_exporter() -> int:
    """Roda export_ubc_mapping_to_lyra.export_mapping() sem subprocess. O exporter
    calcula SRC/DST pelo próprio __file__, então funciona de qualquer cwd."""
    spec = importlib.util.spec_from_file_location("_export_ubc_map", str(UBC_EXPORTER))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod.export_mapping()


def _build_ubc_cred(id_val: str, artist_val: str, account_val: str, path_val: str, code: str) -> dict:
    account = account_val.strip() or artist_val.strip()
    hoje = datetime.now().strftime("%Y-%m-%d")
    return {
        "id": id_val.strip(),
        "artist": artist_val.strip() or account,
        "account": account,
        "holder_name": account,
        "path": path_val.strip(),
        "username": "",
        "password": "",
        "status": "active",
        "notas": f"Cadastrado via Organizador de Comprovantes (lyra) em {hoje}. Login master/unificado.",
        "access_type": "unified",
        "ecad_code": str(code),
    }


def register_ubc_credential(cred: dict) -> tuple[bool, str]:
    """Faz backup, adiciona a credencial no ubc_portal.json e roda o exporter.
    Recusa duplicatas (mesmo id, ou mesmo ECAD+pasta)."""
    portal = _load_ubc_portal()
    if portal is None:
        return False, "Não consegui ler o ubc_portal.json."

    creds = portal.get("credentials", [])
    code = str(cred["ecad_code"]).strip()

    if cred["id"] in {c.get("id") for c in creds}:
        return False, f"Já existe credencial com id '{cred['id']}'. Troque o ID."
    for c in creds:
        ec = str(c.get("ecad_code") or "").strip()
        try:
            same_code = bool(ec) and str(int(ec)) == str(int(code))
        except ValueError:
            same_code = ec == code
        if same_code and (c.get("path") or "") == cred["path"]:
            return False, f"Já existe credencial com ECAD {code} nessa mesma pasta (id '{c.get('id')}')."

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup = UBC_PORTAL_FILE.parent / f"ubc_portal.json.bak_{ts}"
    try:
        shutil.copy2(UBC_PORTAL_FILE, backup)
        creds.append(cred)
        portal["credentials"] = creds
        UBC_PORTAL_FILE.write_text(
            json.dumps(portal, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        n = _run_ubc_exporter()
    except Exception as e:
        return False, f"Falhou ao gravar/exportar: {e}"
    return True, (
        f"'{cred['id']}' cadastrado (ECAD {code}) e exportado — {n} credenciais no "
        f"mapa. Backup: {backup.name}"
    )


def render_orphans(orphans: list, cfg: dict, entity_name: str):
    """Seção 'Códigos não reconhecidos'. Pra UBC rodando local, mostra um form de
    cadastro por código; senão, cai na tabela informativa de sempre."""
    st.subheader("⚠️ Códigos não reconhecidos")
    portal_id = cfg.get("portal_id")

    def _static_table(extra_caption: str = ""):
        st.caption(
            f"Foram incluídos no .zip dentro de `_ORPHANS\\{cfg['folder']}`, pra nada "
            "se perder. Avise o Marcelo com o código e o titular/artista (quando "
            "identificado) pra ele cadastrar na base." + extra_caption
        )
        render_html_table(
            ["Código ECAD", "Arquivos", "Titular (palpite)", "Artista (palpite)"],
            [simple_row([o["code"], o["arquivos"], o["titular"], o["artista"]]) for o in orphans],
        )

    # ABRAMUS (ou entidade sem portal_id): sem cadastro automatizado por ora.
    if not portal_id:
        _static_table()
        return

    # UBC mas rodando fora do ambiente local (ex.: Streamlit Cloud): sem fonte pra gravar.
    if not _rpa_ubc_available():
        _static_table(
            " · O cadastro direto só aparece rodando o app **local**, com o repo "
            "`rpa-royalties` ao lado."
        )
        return

    # Feedback persistente do último cadastro (sobrevive ao st.rerun).
    msg = st.session_state.pop("_ubc_reg_msg", None)
    if msg:
        st.success(msg)

    st.caption(
        "Preencha e clique **Cadastrar e ativar**: grava direto no `ubc_portal.json` "
        "(com backup), roda o exporter e o código passa a ser reconhecido na hora. "
        "Usa login **master/unificado** — sem senha."
    )

    existing_ids = _existing_ubc_ids()
    for o in orphans:
        titular = o["titular"] if o["titular"] != "?" else ""
        artista = o["artista"] if o["artista"] != "?" else ""
        default_artist = artista or titular
        header_name = titular or artista or "sem palpite"
        with st.expander(f"🔢 {o['code']} — {header_name}  ·  {o['arquivos']} arq."):
            default_slug = _slugify_id(default_artist or f"ubc{o['code']}", existing_ids)
            with st.form(f"reg_{entity_name}_{o['code']}"):
                c1, c2 = st.columns(2)
                with c1:
                    artist_val = st.text_input("Artista", value=default_artist, key=f"a_{o['code']}")
                    account_val = st.text_input(
                        "Conta / Titular", value=titular or default_artist, key=f"ac_{o['code']}"
                    )
                with c2:
                    id_val = st.text_input("ID da credencial", value=default_slug, key=f"id_{o['code']}")
                    st.text_input("Código ECAD", value=o["code"], disabled=True, key=f"e_{o['code']}")
                path_val = st.text_input(
                    "Pasta na base (Z:\\...)",
                    value=_suggest_ubc_path(default_artist, titular or default_artist),
                    key=f"p_{o['code']}",
                    help="A credencial só entra no mapa se tiver pasta. Confirme o caminho real na base.",
                )
                matches = _find_artist_folders(default_artist)
                if matches:
                    st.caption("Pastas parecidas em Z:\\: " + "  ·  ".join(matches))
                st.caption("access_type = **unified** · status = **active** · sem login (usa master)")
                submitted = st.form_submit_button("✅ Cadastrar e ativar", use_container_width=True)

            if submitted:
                if not id_val.strip() or not path_val.strip() or not (artist_val.strip() or account_val.strip()):
                    st.error("Preencha ao menos ID, Artista/Conta e Pasta.")
                else:
                    cred = _build_ubc_cred(id_val, artist_val, account_val, path_val, o["code"])
                    ok, result_msg = register_ubc_credential(cred)
                    if ok:
                        st.session_state["_ubc_reg_msg"] = result_msg
                        load_mapping_rows.clear()
                        st.rerun()
                    else:
                        st.error(result_msg)


# ---------------------------------------------------------------------------
# YouTube — organizador por período (sem código ECAD / credenciais)
# ---------------------------------------------------------------------------
#
# O YouTube não entrega comprovante por artista/conta: são relatórios em massa
# da conta de Content Owner. Aqui não há código ECAD nem mapeamento de
# credencial — cada arquivo é encaixado em
# `Nas Nuvens Catalog\YOUTUBE\Ano\Mês\<Tipo de receita>` seguindo o padrão que
# já existe na base. O período sai da data AAAAMMDD do nome; o tipo de receita
# sai de marcadores no nome (ADJ / red / adjustment). Os arquivos são mantidos
# exatamente como o YouTube entregou (inclusive os .gz / .csv.zip) — só mudam de
# pasta.

YT_BASE_PREFIX = "Nas Nuvens Catalog\\YOUTUBE"

# Pastas de tipo de receita — nomes canônicos (acentuados, versão 2026 da base).
YT_TYPE_ADS = "Receita de anúncios"
YT_TYPE_SUBS = "Receita das assinaturas"
YT_TYPE_ADJ_ADS = "Receita de ajustes de anúncios"
YT_TYPE_ADJ_SUBS = "Receita de ajustes de assinaturas"
YT_TYPE_OTHER = "Outro"

_YT_DATE_RE = re.compile(r"(20\d{2})(\d{2})(\d{2})")


def extract_youtube_period(name: str):
    """Ano/mês a partir do último AAAAMMDD no nome do arquivo. Os relatórios
    trazem a data do período no nome (ex.: `..._M_20260501_...`); os que trazem
    faixa (`..._20260401_20260430_...`) caem no mês da data."""
    for y, m, _d in reversed(_YT_DATE_RE.findall(name)):
        month = int(m)
        if 1 <= month <= 12:
            return int(y), month
    return None, None


def classify_youtube_revenue(name: str) -> str:
    """Pasta de tipo de receita a partir de marcadores no nome do arquivo.
    Funciona tanto pros nomes entregues pelo Content Manager
    (`..._M_..._ADJ_...`, `..._red_label_...`, `..._adjustment_red_...`) quanto
    pros nomes do Reporting API (`ads_partner_revenue_*`, `adjustment_*`,
    `red_*_subscription_*`)."""
    n = name.lower()
    if "custom" in n or "lifetime" in n or "payment_summary" in n:
        return YT_TYPE_OTHER
    is_adjustment = "adjustment" in n or "_adj_" in n
    is_subscription = "red" in n or "subscription" in n
    if is_adjustment and is_subscription:
        return YT_TYPE_ADJ_SUBS
    if is_adjustment:
        return YT_TYPE_ADJ_ADS
    if is_subscription:
        return YT_TYPE_SUBS
    return YT_TYPE_ADS


def collect_youtube_files(uploaded_zip: zipfile.ZipFile) -> list[tuple[str, bytes]]:
    """Todos os relatórios do zip (.csv, .gz, .csv.zip), mantidos como estão —
    o YouTube entrega os brutos já compactados em .gz (e às vezes .zip)."""
    collected = []
    for item in uploaded_zip.namelist():
        if item.endswith("/"):
            continue
        name = item.rsplit("/", 1)[-1]
        low = name.lower()
        if low.endswith((".csv", ".gz", ".zip")):
            collected.append((name, uploaded_zip.read(item)))

    dedup = {}
    for name, content in collected:
        dedup[name] = content
    return list(dedup.items())


def organize_youtube(files: list[tuple[str, bytes]]):
    """Retorna (zip_bytes, contagem_por_(ano,mês,tipo), sem_data). Cada arquivo
    vai para `YOUTUBE\\Ano\\Mês\\<Tipo>` pela data e pelos marcadores do nome; os
    sem data ficam de fora."""
    out_buffer = io.BytesIO()
    counter = defaultdict(int)
    skipped = []

    with zipfile.ZipFile(out_buffer, "w", zipfile.ZIP_DEFLATED) as out_zip:
        for name, content in files:
            year, month = extract_youtube_period(name)
            if not year or not month:
                skipped.append(name)
                continue
            tipo = classify_youtube_revenue(name)
            dest = (
                f"{YT_BASE_PREFIX}\\{year}\\{month_folder_name(year, month)}\\{tipo}\\{name}"
            ).replace("\\", "/")
            out_zip.writestr(dest, content)
            counter[(year, month, tipo)] += 1

    return out_buffer.getvalue(), counter, skipped


def render_youtube_organizer():
    st.caption(
        "Anexe o .zip de relatórios baixado do YouTube. A página encaixa cada "
        "arquivo em `YOUTUBE\\Ano\\Mês\\<Tipo de receita>` (o padrão da base) pela "
        "data e pelos marcadores do nome, e devolve um .zip pronto pra extrair e "
        "colar direto no lugar certo. Os arquivos são mantidos como o YouTube "
        "entregou (inclusive os `.gz`)."
    )

    uploaded = st.file_uploader(
        "Anexe o .zip de relatórios do YouTube", type="zip", key="uploader_youtube"
    )
    if uploaded is None:
        return

    with st.spinner("Lendo e organizando os arquivos..."):
        try:
            with zipfile.ZipFile(uploaded) as z:
                files = collect_youtube_files(z)
        except zipfile.BadZipFile:
            st.error("Não consegui abrir esse arquivo como .zip. Confira se o upload não corrompeu.")
            return

        if not files:
            st.warning("Nenhum arquivo `.csv`/`.gz`/`.zip` encontrado dentro do .zip.")
            return

        out_bytes, counter, skipped = organize_youtube(files)

    st.success(f"{len(files)} arquivo(s) processado(s).")

    periodos = {(y, m) for (y, m, _t) in counter}
    col1, col2 = st.columns(2)
    with col1:
        st.metric("Períodos (Ano/Mês)", len(periodos))
    with col2:
        st.metric("Arquivos sem data", len(skipped))

    if counter:
        st.subheader("Resumo por período e tipo de receita")
        render_html_table(
            ["Ano", "Mês", "Tipo de receita", "Arquivos"],
            [simple_row([y, month_folder_name(y, m), t, n])
             for (y, m, t), n in sorted(counter.items())],
        )

    if skipped:
        st.subheader("⚠️ Arquivos sem data reconhecida")
        st.caption(
            "Não tinham um `AAAAMMDD` no nome e ficaram de fora do .zip. "
            "Confira manualmente."
        )
        render_html_table(["Arquivo"], [simple_row([n]) for n in skipped])

    st.divider()
    hoje = datetime.now().strftime("%Y-%m-%d")
    st.download_button(
        "⬇️ Baixar .zip organizado",
        data=out_bytes,
        file_name=f"relatorios_organizados_youtube_{hoje}.zip",
        mime="application/zip",
        use_container_width=True,
    )
    st.caption(
        "Depois de baixar: extraia e cole o conteúdo direto em "
        "`Z:\\ROYALTY\\Royalties Statements_Historicals\\` — as pastas já vêm com o "
        "caminho completo (`Nas Nuvens Catalog\\YOUTUBE\\...`)."
    )


def main():
    setup_page(__file__)

    st.sidebar.header("⚙️ Configurações")
    entity_name = st.sidebar.selectbox("Entidade", list(ENTITIES.keys()) + ["YouTube"], index=0)
    st.sidebar.markdown("---")

    if entity_name == "YouTube":
        render_youtube_organizer()
        return

    cfg = ENTITIES[entity_name]

    st.caption(
        f"Anexe o .zip de comprovantes baixado do portal da **{entity_name}**. "
        "A página organiza tudo na estrutura de pastas da base e devolve "
        "um .zip pronto pra você extrair e colar direto no lugar certo."
    )

    mapping_path = MAPPING_DIR / cfg["mapping_file"]
    rows = load_mapping_rows(str(mapping_path))
    if not rows:
        st.error(
            f"Mapeamento de credenciais da {entity_name} não encontrado ou vazio "
            f"(`{mapping_path}`). Rode o exporter em rpa-royalties pra gerar, "
            "ou fale com o Marcelo antes de usar esta página."
        )
        return
    mapping = build_ecad_index(rows)

    with st.expander(f"Ver credenciais {entity_name} cadastradas ({len(rows)})"):
        query = st.text_input("Buscar por artista ou conta", key=f"cred_search_{entity_name}")
        render_credentials_table(rows, query)

    uploaded = st.file_uploader(
        "Anexe o .zip de comprovantes", type="zip", key=f"uploader_{entity_name}"
    )
    if uploaded is None:
        return

    with st.spinner("Lendo e organizando os arquivos..."):
        try:
            with zipfile.ZipFile(uploaded) as z:
                files = collect_zip_files(z, cfg["extract_code"])
        except zipfile.BadZipFile:
            st.error("Não consegui abrir esse arquivo como .zip. Confira se o upload não corrompeu.")
            return

        if not files:
            st.warning(f"Nenhum arquivo reconhecido dentro do .zip (padrão esperado: `{cfg['filename_hint']}`).")
            return

        out_bytes, account_counter, orphans = organize(
            files, mapping, cfg["extract_code"], cfg["folder"], cfg["pdf_identity"]
        )

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
        render_orphans(orphans, cfg, entity_name)

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
        file_name=f"comprovantes_organizados_{cfg['folder'].lower()}_{hoje}.zip",
        mime="application/zip",
        use_container_width=True,
    )
    st.caption(
        "Depois de baixar: extraia e cole o conteúdo direto em "
        "`Z:\\ROYALTY\\Royalties Statements_Historicals\\` — as pastas já vêm com o caminho certo."
    )


if __name__ == "__main__":
    main()
