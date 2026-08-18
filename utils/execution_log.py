"""
Log de execuções dos processamentos de royalties, para rastreabilidade
posterior — sem isso, a única forma de saber se um período já foi processado
e se a validação bateu era perguntar a quem rodou (ou reprocessar do zero).

Cada chamada de `registrar` acrescenta uma linha JSON em
`data/logs/execucoes.jsonl` (um arquivo por append, uma execução por linha).
`historico`/`ultima` releem o arquivo inteiro — é O(n), mas o arquivo cresce
uma linha por clique em "Processar", não por linha de dado, então não pesa.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

RAIZ = Path(__file__).resolve().parents[1]
LOG_PATH = RAIZ / "data" / "logs" / "execucoes.jsonl"


@dataclass(frozen=True)
class Execucao:
    pagina: str
    periodo: str
    quando: str
    resumo: dict[str, Any]


def registrar(pagina: str, periodo: str, resumo: dict[str, Any]) -> None:
    """Acrescenta uma linha ao log. `resumo` é de livre escolha da página
    (cada uma sabe o que vale registrar), mas precisa ser serializável em
    JSON puro — valores numpy/pandas devem virar float/int antes de chegar
    aqui, senão o `json.dumps` quebra."""
    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    execucao = Execucao(
        pagina=pagina,
        periodo=periodo,
        quando=datetime.now().isoformat(timespec="seconds"),
        resumo=resumo,
    )
    with LOG_PATH.open("a", encoding="utf-8") as f:
        f.write(json.dumps(asdict(execucao), ensure_ascii=False) + "\n")


def historico(pagina: str, periodo: str | None = None) -> list[Execucao]:
    """Execuções de uma página, na ordem em que foram gravadas. Linha
    corrompida (gravação interrompida no meio) é ignorada em vez de derrubar
    a leitura do resto do log."""
    if not LOG_PATH.exists():
        return []
    resultado = []
    with LOG_PATH.open("r", encoding="utf-8") as f:
        for linha in f:
            linha = linha.strip()
            if not linha:
                continue
            try:
                dado = json.loads(linha)
            except ValueError:
                continue
            if dado.get("pagina") != pagina:
                continue
            if periodo is not None and dado.get("periodo") != periodo:
                continue
            resultado.append(Execucao(**dado))
    return resultado


def ultima(pagina: str, periodo: str | None = None) -> Execucao | None:
    """Última execução registrada para a página (e período, se informado).
    `None` quando nunca rodou."""
    execucoes = historico(pagina, periodo)
    return execucoes[-1] if execucoes else None
