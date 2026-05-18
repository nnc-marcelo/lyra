"""
Integração com a API do Reprtoir para busca de obras não identificadas.
Usa ISWC como identificador primário; cai para título+autores como fallback.
"""

import os
import unicodedata
import difflib
import requests
from dotenv import load_dotenv

load_dotenv()


class ReprtorirClient:
    BASE_URL = "https://reprtoir.io/api"

    def __init__(self, api_key: str | None = None):
        self.api_key = api_key or os.getenv("REPRTOIR_API_KEY")
        if not self.api_key:
            raise ValueError(
                "REPRTOIR_API_KEY não configurada. Adicione ao arquivo .env do projeto."
            )
        self._session = requests.Session()
        self._session.headers.update({
            "X-API-Key": self.api_key,
            "X-API-Version": os.getenv("REPRTOIR_API_VERSION", "2024-04-11"),
            "Accept": "application/json",
            "Content-Type": "application/json",
        })

    def search_works(
        self,
        query: str | None = None,
        iswc: str | None = None,
        author_writers: list[str] | None = None,
        composer_writers: list[str] | None = None,
        per_page: int = 5,
    ) -> dict:
        url = f"{self.BASE_URL}/works/search"
        params = {"sort_field": "_score", "sort_order": "desc", "per_page": per_page}
        if query:
            params["query"] = query
        body = {}
        if iswc:
            body["iswc"] = iswc
        if author_writers:
            body["author_writers"] = author_writers
        if composer_writers:
            body["composer_writers"] = composer_writers
        resp = self._session.post(url, params=params, json=body)
        resp.raise_for_status()
        return resp.json()


def _normalizar(text: str) -> str:
    text = unicodedata.normalize("NFD", text.upper().strip())
    return "".join(c for c in text if unicodedata.category(c) != "Mn")


def lookup_obra(
    client: ReprtorirClient,
    iswc: str,
    titulo: str,
    autores_list: list[str],
) -> dict | None:
    """
    Busca uma obra no Reprtoir.
    Tenta ISWC primeiro (alta precisão), depois título+autores como fallback.
    Retorna o dicionário da obra com campo extra '_fonte', ou None.
    """
    iswc_clean = (iswc or "").strip()
    titulo_clean = (titulo or "").strip()
    autores_clean = [a.strip() for a in (autores_list or []) if len(a.strip()) > 2]

    # Tentativa 1: ISWC exato
    if iswc_clean and iswc_clean.upper() not in ("", "NAN", "NONE"):
        try:
            result = client.search_works(iswc=iswc_clean, per_page=1)
            items = result.get("results", [])
            if items:
                return {**items[0], "_fonte": "ISWC"}
        except Exception:
            pass

    # Tentativa 2: título + autores
    if titulo_clean and titulo_clean.upper() not in ("", "NAN", "NONE"):
        try:
            result = client.search_works(
                query=titulo_clean,
                author_writers=autores_clean or None,
                per_page=5,
            )
            items = result.get("results", [])
            if items:
                melhor = _melhor_match_titulo(titulo_clean, items)
                if melhor:
                    return {**melhor, "_fonte": "Título+Autor"}
        except Exception:
            pass

    return None


def _melhor_match_titulo(titulo: str, items: list[dict]) -> dict | None:
    titulo_norm = _normalizar(titulo)
    melhor_score = 0.0
    melhor_item = None
    for item in items:
        score = difflib.SequenceMatcher(
            None, titulo_norm, _normalizar(item.get("title", "") or "")
        ).ratio()
        if score > melhor_score:
            melhor_score = score
            melhor_item = item
    # Aceita resultado se similaridade >= 60%
    if melhor_score >= 0.6:
        return melhor_item
    return items[0] if items else None


def match_catalogo_interno(
    cat_reprtoir: str, catalogs_internos: list[str]
) -> tuple[str, float]:
    """
    Fuzzy match entre o nome de catálogo do Reprtoir e os nomes internos.
    Retorna (nome_interno_mais_próximo, score 0–100).
    """
    if not cat_reprtoir or not catalogs_internos:
        return cat_reprtoir or "", 0.0

    cat_norm = _normalizar(cat_reprtoir)
    cats_norm = {_normalizar(c): c for c in catalogs_internos}

    matches = difflib.get_close_matches(cat_norm, cats_norm.keys(), n=1, cutoff=0.5)
    if matches:
        score = difflib.SequenceMatcher(None, cat_norm, matches[0]).ratio() * 100
        return cats_norm[matches[0]], round(score, 1)

    return cat_reprtoir, 0.0
