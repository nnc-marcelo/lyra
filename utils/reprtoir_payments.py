"""
Reconciliação de payments do Reprtoir (marcar como Paid, setar data de
pagamento, registrar pendências).

O Reprtoir não expõe isso na API pública (ver `reprtoir_lookup.py`, que só
cobre works/tracks/albums via /api). Este módulo usa os mesmos endpoints
internos que a própria SPA React do Reprtoir chama — descobertos por
engenharia reversa das chamadas de rede, autenticando por login de formulário
(cookies de sessão) via `requests`, sem navegador. Não são documentados
oficialmente: se o Reprtoir mudar o front-end, isto pode quebrar.

Endpoints usados:
  POST /users/sign_in        — login (form Devise: user[email]/user[password])
  GET  /payments.json        — lista paginada de payments (até 500/página)
  PUT  /mass.json             — edição em massa (status, payment_date, notes)
                                 `status` é campo obrigatório em toda chamada;
                                 os demais (payment_date, notes) são opcionais
                                 e não afetados quando omitidos.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field
from typing import Callable

import pandas as pd
import requests
from bs4 import BeautifulSoup

REPRTOIR_URL = "https://nas-nuvens-catalog.reprtoir.io"
# UA de navegador real: um UA customizado ("Lyra/...") tem mais chance de ser
# barrado por proteção anti-bot (Cloudflare etc.) na frente do Reprtoir,
# especialmente vindo do IP de datacenter compartilhado do Streamlit Cloud em
# vez de um IP residencial/escritório.
_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "pt-BR,pt;q=0.9,en-US;q=0.8,en;q=0.7",
}
_PER_PAGE = 500
_COLUMN_KEYS = ["name", "status", "rightholder", "rightholder.vat_number", "amount", "payment_date", "notes"]


class ReprtoirLoginError(RuntimeError):
    """Login falhou (credenciais erradas ou o formulário do Reprtoir mudou)."""


class ReprtoirRequestError(RuntimeError):
    """Uma chamada autenticada falhou depois do login."""


# ---------------------------------------------------------------------------
# Cliente HTTP
# ---------------------------------------------------------------------------

class ReprtoirPaymentsClient:
    def __init__(self, email: str, password: str):
        if not email or not password:
            raise ValueError("Email/senha do Reprtoir não configurados.")
        self._email = email
        self._password = password
        self._session = requests.Session()
        self._session.headers.update(_HEADERS)
        self._logged_in = False

    def login(self) -> None:
        r = self._session.get(f"{REPRTOIR_URL}/users/sign_in", timeout=15)
        soup = BeautifulSoup(r.text, "html.parser")
        token_input = soup.select_one('input[name="authenticity_token"]')
        if not token_input:
            raise ReprtoirLoginError(
                "Não encontrei o formulário de login (o Reprtoir pode ter mudado). "
                + self._diagnosticar(r)
            )

        r2 = self._session.post(
            f"{REPRTOIR_URL}/users/sign_in",
            data={
                "authenticity_token": token_input.get("value"),
                "user[email]": self._email,
                "user[password]": self._password,
            },
            timeout=15,
        )
        soup2 = BeautifulSoup(r2.text, "html.parser")
        csrf = soup2.select_one('meta[name="csrf-token"]')
        ainda_na_tela_login = soup2.select_one('input[type="password"]') is not None
        if not csrf or ainda_na_tela_login:
            raise ReprtoirLoginError(
                "Login recusado — confira REPRTOIR_EMAIL/REPRTOIR_PASSWORD nos secrets. "
                + self._diagnosticar(r2)
            )

        self._session.headers.update({
            "X-CSRF-Token": csrf.get("content"),
            "X-Requested-With": "XMLHttpRequest",
            "Accept": "application/json",
            "Content-Type": "application/json",
        })
        self._logged_in = True

    @staticmethod
    def _diagnosticar(r: requests.Response) -> str:
        """Detalhe extra para o erro — sem isso, um bloqueio anti-bot (comum
        vindo do IP compartilhado do Streamlit Cloud) e uma mudança real no
        Reprtoir dão o mesmo erro genérico, e não dá pra saber qual é sem
        acesso ao ambiente onde rodou."""
        indicios_cloudflare = (
            "cf-ray" in r.headers
            or "cloudflare" in r.headers.get("server", "").lower()
            or "just a moment" in r.text.lower()
            or "checking your browser" in r.text.lower()
        )
        if indicios_cloudflare:
            return (
                f"(HTTP {r.status_code}, indícios de bloqueio anti-bot/Cloudflare — "
                "provavelmente o IP do Streamlit Cloud está sendo desafiado.)"
            )
        amostra = re.sub(r"\s+", " ", r.text).strip()[:200]
        return f"(HTTP {r.status_code}, início da resposta: {amostra!r})"

    def _ensure_login(self) -> None:
        if not self._logged_in:
            self.login()

    def fetch_all_payments(
        self, progress_cb: Callable[[int, int], None] | None = None
    ) -> list[dict]:
        """Extrai todos os payments. `progress_cb(pagina_atual, total_paginas)`
        é chamado a cada página, se informado."""
        self._ensure_login()
        all_payments: list[dict] = []
        page = 1
        while True:
            resp = self._session.get(
                f"{REPRTOIR_URL}/payments.json",
                params={
                    "is_saved_search": "false",
                    "page": page,
                    "per_page": _PER_PAGE,
                    "sort[field]": "created_at",
                    "sort[order]": "desc",
                    "query": "",
                    "column_keys[]": _COLUMN_KEYS,
                },
                timeout=30,
            )
            if resp.status_code != 200:
                raise ReprtoirRequestError(
                    f"Falha ao listar payments (HTTP {resp.status_code})."
                )
            data = resp.json()
            all_payments.extend(data["results"])
            pagination = data.get("pagination", {})
            total_pages = pagination.get("total_pages", 1) or 1
            if progress_cb:
                progress_cb(page, total_pages)
            if page >= total_pages:
                break
            page += 1
        return all_payments

    def update_payments(
        self,
        uuids: list[str],
        *,
        name_by_uuid: dict[str, str],
        status: str,
        payment_date: str | None = None,
        notes: str | None = None,
    ) -> None:
        """Atualiza um lote de payments que compartilham o mesmo `status` (e,
        se informado, o mesmo `payment_date`/`notes`) numa única chamada.
        `status` é obrigatório em toda chamada ao /mass.json (confirmado por
        teste manual — omiti-lo derruba a chamada com 500); `payment_date` e
        `notes` são opcionais e preservados quando omitidos.

        `name_by_uuid` é necessário porque o endpoint exige `name` no corpo,
        e a API não deixa "não mudar o nome" implícito — reenviamos o nome
        atual de cada payment. Como o endpoint aplica um único `fields` a
        todos os uuids do lote, e o nome varia por payment, isto despacha uma
        chamada por payment quando os nomes diferem (o normal), ou uma única
        chamada quando compartilham o mesmo nome.
        """
        self._ensure_login()
        if not uuids:
            return

        por_nome: dict[str, list[str]] = {}
        for u in uuids:
            nome = name_by_uuid.get(u, "")
            por_nome.setdefault(nome, []).append(u)

        for nome, grupo_uuids in por_nome.items():
            fields: dict = {"name": nome, "status": status}
            dirty = ["status"]
            if payment_date is not None:
                fields["payment_date"] = payment_date
                dirty.append("payment_date")
            if notes is not None:
                fields["notes"] = notes
                dirty.append("notes")

            payload = {
                "model": "Payment",
                "uuids": grupo_uuids,
                "fields": fields,
                "dirty_field_attributes": dirty,
                "pane_type": "payment",
                "pane_uuid": grupo_uuids[0],
            }
            resp = self._session.put(f"{REPRTOIR_URL}/mass.json", json=payload, timeout=60)
            if resp.status_code != 200:
                raise ReprtoirRequestError(
                    f"Falha ao atualizar {len(grupo_uuids)} payment(s) (HTTP {resp.status_code})."
                )
            body = resp.json().get("mass", {})
            if not body.get("success"):
                raise ReprtoirRequestError(
                    f"Reprtoir recusou a atualização: {body.get('message') or body.get('errors')}"
                )


# ---------------------------------------------------------------------------
# Leitura da planilha do financeiro
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class LinhaPlanilha:
    rightsholder: str
    vat: str
    amount: float
    pago: bool
    data_pagamento: str | None  # YYYY-MM-DD, se a planilha trouxer
    motivo: str | None  # texto livre da coluna "Descrição do caso", se houver


def _normalizar_vat(vat: str) -> str:
    return "".join(c for c in str(vat) if c.isdigit())


def _achar_linha_cabecalho(df_bruto: pd.DataFrame) -> int:
    """Procura a linha que contém o cabeçalho real ("Payment | Rights-Holder" /
    "Payment | E.U. VAT Number") em vez de assumir uma posição fixa — o número
    de linhas de título no topo da planilha varia entre competências."""
    for i in range(min(10, len(df_bruto))):
        linha_texto = " ".join(str(v) for v in df_bruto.iloc[i].tolist() if pd.notna(v))
        if "Rights-Holder" in linha_texto and "VAT" in linha_texto:
            return i
    raise ValueError(
        "Não encontrei a linha de cabeçalho (\"Payment | Rights-Holder\" / "
        "\"Payment | E.U. VAT Number\") nas primeiras 10 linhas da planilha."
    )


def carregar_planilha(arquivo) -> list[LinhaPlanilha]:
    """Lê a planilha de conciliação financeiro × Reprtoir. `arquivo` é o que
    `st.file_uploader` devolve (aceita path também). Colunas esperadas, por
    posição, a partir da linha de cabeçalho: Rights-Holder, VAT, Royalties
    (valor), Financeiro, Check, Pago?, [Data de pagamento], [Descrição do
    caso] — as duas últimas são opcionais."""
    bruto = pd.read_excel(arquivo, sheet_name=0, header=None, dtype=str)
    idx_cabecalho = _achar_linha_cabecalho(bruto)
    df = bruto.iloc[idx_cabecalho + 1:].reset_index(drop=True)

    n_cols = df.shape[1]
    nomes = ["_", "rightsholder", "vat", "amount", "financeiro", "check", "pago",
             "data_pagamento", "motivo"][:n_cols]
    nomes += [f"extra_{i}" for i in range(len(nomes), n_cols)]
    df.columns = nomes

    df = df[df["vat"].notna() & df["pago"].notna()]
    df["vat"] = df["vat"].str.strip()
    df["pago"] = df["pago"].str.strip().str.upper()

    linhas: list[LinhaPlanilha] = []
    for _, row in df.iterrows():
        pago = row["pago"]
        if pago not in ("SIM", "NÃO", "NAO"):
            continue
        try:
            valor = round(float(str(row["amount"]).strip()), 2)
        except (TypeError, ValueError):
            continue

        data_pagamento = None
        if "data_pagamento" in df.columns and pd.notna(row.get("data_pagamento")):
            try:
                data_pagamento = pd.to_datetime(row["data_pagamento"]).strftime("%Y-%m-%d")
            except (TypeError, ValueError):
                data_pagamento = None

        motivo = None
        if "motivo" in df.columns and pd.notna(row.get("motivo")):
            motivo = str(row["motivo"]).strip() or None

        linhas.append(LinhaPlanilha(
            rightsholder=str(row["rightsholder"]).strip(),
            vat=row["vat"],
            amount=valor,
            pago=(pago == "SIM"),
            data_pagamento=data_pagamento,
            motivo=motivo,
        ))
    return linhas


# ---------------------------------------------------------------------------
# Matching
# ---------------------------------------------------------------------------

@dataclass
class Match:
    linha: LinhaPlanilha
    payment: dict  # registro cru vindo do Reprtoir


@dataclass
class Ambiguidade:
    linha: LinhaPlanilha
    candidatos: list[dict]  # 2+ payments do Reprtoir que batem igualmente


@dataclass
class ResultadoMatching:
    a_pagar: list[Match] = field(default_factory=list)       # SIM, hoje Unpaid no Reprtoir
    pendentes: list[Match] = field(default_factory=list)     # NÃO, hoje Unpaid no Reprtoir
    ja_ok: list[Match] = field(default_factory=list)         # já bate (nada a fazer)
    conflitos: list[Match] = field(default_factory=list)     # NÃO na planilha, mas já Paid no Reprtoir
    ambiguos: list[Ambiguidade] = field(default_factory=list)  # 2+ candidatos — não aplicado
    sem_correspondencia: list[LinhaPlanilha] = field(default_factory=list)


# Meio centavo: só absorve erro de ponto flutuante — os dois lados já chegam
# arredondados para 2 casas antes daqui, então valores realmente diferentes
# (mesmo por 1 centavo) não devem ser tratados como o mesmo pagamento.
_TOLERANCIA_VALOR = 0.005


def cruzar(linhas: list[LinhaPlanilha], payments: list[dict]) -> ResultadoMatching:
    """VAT + valor identifica o rights-holder com segurança (VAT é
    praticamente único), mas um mesmo rights-holder pode ter mais de um
    payment com valor igual (coincidência, ou dois períodos com o mesmo
    valor). Por isso, quando mais de um payment do Reprtoir bate igualmente
    com uma linha, a linha vai para `ambiguos` em vez de aplicar no primeiro
    candidato encontrado — evita marcar como pago o payment errado entre
    dois igualmente prováveis. Mesma lógica do lado do Reprtoir: um payment
    já usado por uma linha não é reoferecido a outra (pega duplicata de
    linha na planilha, que senão aplicaria a mesma ação duas vezes calada)."""
    resultado = ResultadoMatching()
    usados: set[str] = set()

    for linha in linhas:
        vat_key = _normalizar_vat(linha.vat)
        candidatos = [
            p for p in payments
            if p["uuid"] not in usados
            and _normalizar_vat(p["rightholder"]["vat_number"]) == vat_key
            and abs(float(p["amount"]) - linha.amount) < _TOLERANCIA_VALOR
        ]

        if not candidatos:
            resultado.sem_correspondencia.append(linha)
            continue
        if len(candidatos) > 1:
            resultado.ambiguos.append(Ambiguidade(linha=linha, candidatos=candidatos))
            continue

        payment = candidatos[0]
        usados.add(payment["uuid"])
        status_atual = payment["status"]["value"]
        m = Match(linha=linha, payment=payment)
        if linha.pago:
            (resultado.ja_ok if status_atual == "paid" else resultado.a_pagar).append(m)
        else:
            # Planilha diz NÃO pago: se o Reprtoir já mostra Paid é uma
            # inconsistência a checar manualmente, não uma pendência normal.
            (resultado.conflitos if status_atual == "paid" else resultado.pendentes).append(m)
    return resultado


def pendencias_em_aberto(payments: list[dict]) -> list[dict]:
    """Payments atualmente Unpaid E com uma nota registrada — não depende da
    planilha carregada nesta sessão: é sempre o estado vivo do Reprtoir, então
    sobrevive a reload de página, redeploy, mês seguinte, etc."""
    return [
        p for p in payments
        if p["status"]["value"] != "paid" and (p.get("notes") or "").strip()
    ]
