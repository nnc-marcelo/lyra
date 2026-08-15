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


@dataclass(frozen=True)
class Pendencia:
    """Algo que está esperando ação. `pagina` é o caminho registrado em
    utils/nav.py da página onde se resolve — o link existe por causa da
    pendência, e não como atalho de navegação (para isso já existe o menu)."""

    titulo: str
    detalhe: str
    pagina: str
    atencao: bool = True


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


@st.cache_data(show_spinner=False)
def _resumo_varredura(_caminho: str, mtime: float) -> dict[str, int]:
    """Contagens do relatório da varredura.

    Lê só as 4 colunas usadas: o CSV passa de 100 mil linhas e é carregado no
    Home, que abre a cada sessão.

    As categorias são do próprio relatório, não invenção daqui:
    `Portal == "anomalias"` são pastas fora da estrutura esperada em Z:, e
    `Access Type == "não cadastrada"` são contas com pasta na base mas sem
    credencial registrada.
    """
    df = pd.read_csv(
        _caminho,
        sep=";",
        encoding="utf-8-sig",
        low_memory=False,
        usecols=["Portal", "Path", "Conta", "Access Type"],
    )
    return {
        "pastas_anomalas": int(df.loc[df["Portal"] == "anomalias", "Path"].nunique()),
        "contas_sem_credencial": int(
            df.loc[df["Access Type"] == "não cadastrada", "Conta"].nunique()
        ),
        "contas_total": int(df["Conta"].nunique()),
    }


def pendencias() -> list[Pendencia]:
    """Tudo que está esperando ação, na ordem em que deve ser lido. Lista vazia
    significa que não há nada pendente — e o Home diz isso explicitamente, em
    vez de mostrar um painel vazio."""
    itens: list[Pendencia] = []

    varredura = ultima_varredura()
    if varredura is not None and varredura.alerta:
        itens.append(
            Pendencia(
                "Varredura de lacunas desatualizada",
                varredura.ajuda or "",
                "views/varredura_lacunas.py",
            )
        )

    caminho_csv = VARREDURA_DIR / "relatorio_royalties.csv"
    mtime = _mtime(caminho_csv)
    if mtime is not None:
        try:
            resumo = _resumo_varredura(str(caminho_csv), mtime)
        except Exception:
            resumo = {}
        if resumo.get("pastas_anomalas"):
            itens.append(
                Pendencia(
                    f"{resumo['pastas_anomalas']} pastas fora da estrutura esperada",
                    "A varredura achou pastas em Z: que não seguem o padrão "
                    "Artista/Entidade/Conta e por isso ficam de fora do mapa de períodos.",
                    "views/varredura_lacunas.py",
                )
            )
        if resumo.get("contas_sem_credencial"):
            itens.append(
                Pendencia(
                    f"{resumo['contas_sem_credencial']} de {resumo['contas_total']} contas sem credencial cadastrada",
                    "Têm pasta na base histórica, mas nenhuma credencial registrada — "
                    "não entram na varredura automática.",
                    "views/varredura_lacunas.py",
                    atencao=False,
                )
            )

    suspensas = _credenciais_suspensas()
    if suspensas:
        itens.append(
            Pendencia(
                f"{suspensas} credenciais suspensas",
                "Estão sem código ECAD, então os comprovantes delas não são "
                "reconhecidos automaticamente na hora de organizar o .zip.",
                "views/organizador_comprovantes.py",
            )
        )

    return itens


def _credenciais_suspensas() -> int:
    total = 0
    for nome in ("abramus_credentials_map.json", "ubc_credentials_map.json"):
        caminho = MAPPING_DIR / nome
        try:
            registros = json.loads(caminho.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        total += sum(1 for r in registros if not r.get("active"))
    return total


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
