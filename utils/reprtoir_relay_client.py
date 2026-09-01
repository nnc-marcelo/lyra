"""
Cliente HTTP para o relay local de reconciliação de payments (ver
`relay/server.py`).

Por quê existe: o Streamlit Community Cloud roda em IPs de datacenter
compartilhados que o WAF na frente do Reprtoir bloqueia (HTTP 403) — mesmo
para GET simples via `requests`, sem navegador. Do IP residencial/escritório
funciona normalmente. O relay roda na máquina do usuário (onde funciona) e
fica exposto via túnel (ngrok); esta página fala com o relay, nunca com o
Reprtoir diretamente.
"""

from __future__ import annotations

from dataclasses import asdict

import requests


class RelayError(RuntimeError):
    """Relay offline/token errado, ou erro repassado do Reprtoir pelo relay."""


class RelayClient:
    def __init__(self, base_url: str, token: str):
        if not base_url or not token:
            raise ValueError("RELAY_URL/RELAY_TOKEN não configurados.")
        self._base_url = base_url.rstrip("/")
        self._headers = {"Authorization": f"Bearer {token}"}

    def _chamar(self, metodo: str, path: str, timeout: int = 60, **kwargs) -> dict:
        try:
            resp = requests.request(
                metodo, f"{self._base_url}{path}", headers=self._headers, timeout=timeout, **kwargs
            )
        except requests.RequestException as e:
            raise RelayError(
                f"Não consegui alcançar o relay em {self._base_url} — confirme que ele está "
                f"rodando na sua máquina e que o túnel (ngrok) está ativo. ({e})"
            )
        if resp.status_code == 401:
            raise RelayError("Relay recusou o token — confira RELAY_TOKEN nos secrets.")
        if resp.status_code >= 400:
            detalhe = resp.text
            try:
                detalhe = resp.json().get("detail", detalhe)
            except ValueError:
                pass
            raise RelayError(f"Relay retornou erro: {detalhe}")
        return resp.json()

    def comparar(self, linhas: list) -> dict:
        return self._chamar("POST", "/comparar", json={"linhas": [asdict(l) for l in linhas]})

    def aplicar(self, marcar_pagos: list[dict], pendencias: list[dict]) -> dict:
        return self._chamar(
            "POST", "/aplicar", json={"marcar_pagos": marcar_pagos, "pendencias": pendencias}
        )

    def pendencias_em_aberto(self) -> list[dict]:
        return self._chamar("GET", "/pendencias")["pendencias"]

    def health(self) -> bool:
        """Timeout curto de propósito — é uma checagem de status, não deve
        travar a página por ~1 minuto se o relay estiver desligado."""
        try:
            return self._chamar("GET", "/health", timeout=4).get("status") == "ok"
        except RelayError:
            return False
