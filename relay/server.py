"""
Relay local para a Reconciliação de Payments do Lyra.

Por quê: o Streamlit Community Cloud roda em IPs de datacenter compartilhados
que o WAF na frente do Reprtoir bloqueia (HTTP 403) — mesmo para chamadas GET
simples via `requests`, sem navegador. Do IP residencial/escritório funciona
normalmente. Este relay roda NA SUA MÁQUINA, fala com o Reprtoir daqui, e
fica exposto pra internet via túnel (ngrok) — a página no Lyra Cloud chama
este relay em vez do Reprtoir direto (ver utils/reprtoir_relay_client.py).

Uso (rodar da raiz do repo, não de dentro de relay/):
  1. Copie relay/.env.example para relay/.env e preencha.
  2. python -m uvicorn relay.server:app --port 8000
  3. Em outro terminal: ngrok http --domain=<seu-dominio-fixo> 8000
  4. Nos secrets do Lyra Cloud: RELAY_URL = URL do ngrok, RELAY_TOKEN = mesmo
     valor do relay/.env.

Autenticação: um token compartilhado (header Authorization: Bearer <token>).
Sem isso, qualquer um que descobrisse a URL pública do túnel poderia marcar
payments como pagos na sua conta do Reprtoir.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

from dataclasses import asdict
from dotenv import load_dotenv
from fastapi import FastAPI, Header, HTTPException
from pydantic import BaseModel

load_dotenv(Path(__file__).parent / ".env")

# utils/ vive na raiz do repo, um nível acima de relay/.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from utils.reprtoir_payments import (  # noqa: E402
    LinhaPlanilha,
    ReprtoirLoginError,
    ReprtoirPaymentsClient,
    ReprtoirRequestError,
    cruzar,
    pendencias_em_aberto,
)

RELAY_TOKEN = os.getenv("RELAY_TOKEN", "")
REPRTOIR_EMAIL = os.getenv("REPRTOIR_EMAIL", "")
REPRTOIR_PASSWORD = os.getenv("REPRTOIR_PASSWORD", "")

if not RELAY_TOKEN:
    raise RuntimeError(
        "RELAY_TOKEN não configurado em relay/.env — gere um valor aleatório "
        "(ex.: python -c \"import secrets; print(secrets.token_urlsafe(32))\")."
    )
if not REPRTOIR_EMAIL or not REPRTOIR_PASSWORD:
    raise RuntimeError("REPRTOIR_EMAIL/REPRTOIR_PASSWORD não configurados em relay/.env.")

app = FastAPI(title="Lyra — Relay do Reprtoir")


def _checar_token(authorization: str | None) -> None:
    if authorization != f"Bearer {RELAY_TOKEN}":
        raise HTTPException(status_code=401, detail="Token inválido.")


def _cliente() -> ReprtoirPaymentsClient:
    return ReprtoirPaymentsClient(REPRTOIR_EMAIL, REPRTOIR_PASSWORD)


def _erro_reprtoir(e: Exception) -> HTTPException:
    return HTTPException(status_code=502, detail=str(e))


@app.get("/health")
def health():
    return {"status": "ok"}


class ComparaRequest(BaseModel):
    linhas: list[dict]


@app.post("/comparar")
def comparar(body: ComparaRequest, authorization: str | None = Header(None)):
    _checar_token(authorization)
    try:
        linhas = [LinhaPlanilha(**l) for l in body.linhas]
        payments = _cliente().fetch_all_payments()
        resultado = cruzar(linhas, payments)
    except (ReprtoirLoginError, ReprtoirRequestError) as e:
        raise _erro_reprtoir(e)

    return {
        "a_pagar": [asdict(m) for m in resultado.a_pagar],
        "pendentes": [asdict(m) for m in resultado.pendentes],
        "ja_ok": [asdict(m) for m in resultado.ja_ok],
        "conflitos": [asdict(m) for m in resultado.conflitos],
        "ambiguos": [asdict(a) for a in resultado.ambiguos],
        "sem_correspondencia": [asdict(l) for l in resultado.sem_correspondencia],
        "total_payments_reprtoir": len(payments),
    }


class ItemPago(BaseModel):
    uuid: str
    name: str
    payment_date: str


class ItemPendencia(BaseModel):
    uuid: str
    name: str
    status: str
    notes: str


class AplicarRequest(BaseModel):
    marcar_pagos: list[ItemPago] = []
    pendencias: list[ItemPendencia] = []


@app.post("/aplicar")
def aplicar(body: AplicarRequest, authorization: str | None = Header(None)):
    _checar_token(authorization)
    client = _cliente()
    resumo = {"marcados_paid": 0, "pendencias_registradas": 0}

    try:
        por_data: dict[str, list[ItemPago]] = {}
        for item in body.marcar_pagos:
            por_data.setdefault(item.payment_date, []).append(item)
        for data, itens in por_data.items():
            uuids = [i.uuid for i in itens]
            nomes = {i.uuid: i.name for i in itens}
            client.update_payments(uuids, name_by_uuid=nomes, status="paid", payment_date=data)
            resumo["marcados_paid"] += len(uuids)

        por_nota: dict[tuple[str, str], list[ItemPendencia]] = {}
        for item in body.pendencias:
            por_nota.setdefault((item.status, item.notes), []).append(item)
        for (status, notes), itens in por_nota.items():
            uuids = [i.uuid for i in itens]
            nomes = {i.uuid: i.name for i in itens}
            client.update_payments(uuids, name_by_uuid=nomes, status=status, notes=notes)
            resumo["pendencias_registradas"] += len(uuids)
    except (ReprtoirLoginError, ReprtoirRequestError) as e:
        # Parcialmente aplicado é esperado e seguro aqui: /comparar sempre
        # busca o estado atual, então rodar de novo só reprocessa o que
        # ainda falta (ver docstring de views/reconciliacao_pagamentos.py).
        raise HTTPException(
            status_code=502,
            detail=f"Parou no meio ({resumo['marcados_paid']} pago(s), "
                   f"{resumo['pendencias_registradas']} pendência(s) aplicadas antes do erro): {e}",
        )

    return resumo


@app.get("/pendencias")
def pendencias(authorization: str | None = Header(None)):
    _checar_token(authorization)
    try:
        payments = _cliente().fetch_all_payments()
    except (ReprtoirLoginError, ReprtoirRequestError) as e:
        raise _erro_reprtoir(e)
    return {"pendencias": pendencias_em_aberto(payments)}
