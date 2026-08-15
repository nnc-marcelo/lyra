"""
Métricas do estado das bases, exibidas no topo do Home.

Cada função lê um arquivo de `data/` e devolve `None` quando ele não existe ou
não pôde ser lido — o Home mostra "—" no lugar. Isso não é defensivo à toa: as
bases entram no repo por commit (o app grava mapeamento via commit no GitHub) e
o relatório da varredura é gerado por uma máquina externa, então um clone novo
ou um deploy pode legitimamente não ter todos os arquivos ainda.

O cache é invalidado pelo mtime do arquivo, passado como argumento para o
`st.cache_data` enxergar a mudança — sem isso, um `git pull` trazendo base nova
continuaria mostrando o número velho até reiniciar o app.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import pandas as pd
import streamlit as st

RAIZ = Path(__file__).resolve().parents[1]
MAPPING_DIR = RAIZ / "data" / "mapping"
VARREDURA_DIR = RAIZ / "data" / "varredura_lacunas"

# Mesma cadência esperada em views/varredura_lacunas.py: acima disto o
# relatório é considerado defasado.
STALE_AFTER_DAYS = 2


@dataclass(frozen=True)
class Metrica:
    valor: str
    ajuda: str | None = None
    alerta: bool = False


def _mtime(caminho: Path) -> float | None:
    try:
        return caminho.stat().st_mtime
    except OSError:
        return None


@st.cache_data(show_spinner=False)
def _contar_faixas_ingrooves(_caminho: str, mtime: float) -> tuple[int, int]:
    """(faixas, tags de artista) no mapeamento Ingrooves.

    A contagem é por ISRC, não por artista: a coluna `Artist` traz o crédito
    como veio do relatório, então "Fulano" e "Fulano feat. Beltrano" contam
    como dois. Quem agrupa de fato é `Tag_Artista` — é por ela que o Ingrooves
    Breaker separa os arquivos — e são poucas dezenas de tags, cada uma
    cobrindo várias faixas.
    """
    df = pd.read_excel(_caminho)
    faixas = int(df["ISRC"].dropna().nunique())
    tags = int(df["Tag_Artista"].dropna().nunique()) if "Tag_Artista" in df.columns else 0
    return faixas, tags


@st.cache_data(show_spinner=False)
def _contar_obras(_caminho: str, mtime: float) -> int:
    return int(len(pd.read_excel(_caminho)))


@st.cache_data(show_spinner=False)
def _contar_credenciais(_caminhos: tuple[str, ...], mtimes: tuple[float, ...]) -> tuple[int, int]:
    """(ativas, total) somando ABRAMUS e UBC."""
    ativas = total = 0
    for caminho in _caminhos:
        registros = json.loads(Path(caminho).read_text(encoding="utf-8"))
        total += len(registros)
        ativas += sum(1 for r in registros if r.get("active"))
    return ativas, total


def faixas_mapeadas() -> Metrica | None:
    caminho = MAPPING_DIR / "mapping-artistas-ingrooves.xlsx"
    mtime = _mtime(caminho)
    if mtime is None:
        return None
    try:
        faixas, tags = _contar_faixas_ingrooves(str(caminho), mtime)
    except Exception:
        return None
    return Metrica(
        f"{faixas:,}".replace(",", "."),
        f"ISRCs no mapeamento Ingrooves, agrupados em {tags} tags de artista.",
    )


def obras_catalogo() -> Metrica | None:
    caminho = MAPPING_DIR / "Lista_Obras_Catalogo_Irmaos_Vitale.xlsx"
    mtime = _mtime(caminho)
    if mtime is None:
        return None
    try:
        n = _contar_obras(str(caminho), mtime)
    except Exception:
        return None
    return Metrica(f"{n:,}".replace(",", "."), "Obras na lista do catálogo Irmãos Vitale.")


def credenciais() -> Metrica | None:
    caminhos = [MAPPING_DIR / "abramus_credentials_map.json", MAPPING_DIR / "ubc_credentials_map.json"]
    existentes = [c for c in caminhos if c.exists()]
    if not existentes:
        return None
    try:
        ativas, total = _contar_credenciais(
            tuple(str(c) for c in existentes),
            tuple(_mtime(c) or 0.0 for c in existentes),
        )
    except Exception:
        return None
    return Metrica(f"{ativas} de {total}", "Credenciais ABRAMUS + UBC marcadas como ativas.")


def ultima_varredura() -> Metrica | None:
    caminho = VARREDURA_DIR / "last_updated.txt"
    try:
        bruto = caminho.read_text(encoding="utf-8").strip()
        quando = datetime.fromisoformat(bruto)
    except (OSError, ValueError):
        return None
    dias = (datetime.now() - quando).days
    defasado = dias > STALE_AFTER_DAYS
    ajuda = f"Varredura de lacunas gerada em {quando:%d/%m/%Y %H:%M}."
    if defasado:
        ajuda += f" Defasada: esperada diária, e já são {dias} dias."
    return Metrica(f"{quando:%d/%m}", ajuda, alerta=defasado)
