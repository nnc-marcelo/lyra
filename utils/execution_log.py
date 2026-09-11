"""
Log de execuções dos processamentos de royalties, para rastreabilidade
posterior — sem isso, a única forma de saber se um período já foi processado
e se a validação bateu era perguntar a quem rodou (ou reprocessar do zero).

Cada chamada de `registrar` acrescenta uma linha JSON em
`data/logs/execucoes.jsonl` (um arquivo por append, uma execução por linha).
`historico`/`ultima`/`todas` releem o arquivo inteiro — é O(n), mas o arquivo
cresce uma linha por clique em "Processar", não por linha de dado, então não
pesa.

Quem lê o log: a `retomada` no topo de cada template (último período rodado
ali) e a tela Log de execuções (views/log_execucoes.py), que cruza páginas ×
meses. Os helpers de período no fim do arquivo existem para essas duas telas
lerem o campo `periodo` do mesmo jeito.
"""

from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

RAIZ = Path(__file__).resolve().parents[1]
LOG_PATH = RAIZ / "data" / "logs" / "execucoes.jsonl"

MESES_PT = ["jan", "fev", "mar", "abr", "mai", "jun",
            "jul", "ago", "set", "out", "nov", "dez"]


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


def todas() -> list[Execucao]:
    """Todas as execuções, de todas as páginas, na ordem em que foram
    gravadas. Linha corrompida (gravação interrompida no meio) é ignorada em
    vez de derrubar a leitura do resto do log."""
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
            try:
                resultado.append(Execucao(**dado))
            except TypeError:
                continue
    return resultado


def historico(pagina: str, periodo: str | None = None) -> list[Execucao]:
    """Execuções de uma página, na ordem em que foram gravadas."""
    return [
        ex for ex in todas()
        if ex.pagina == pagina and (periodo is None or ex.periodo == periodo)
    ]


def ultima(pagina: str, periodo: str | None = None) -> Execucao | None:
    """Última execução registrada para a página (e período, se informado).
    `None` quando nunca rodou."""
    execucoes = historico(pagina, periodo)
    return execucoes[-1] if execucoes else None


# ---------------------------------------------------------------------------
# Período: cada página grava no formato que tem à mão. Aqui se normaliza.
# ---------------------------------------------------------------------------

def meses_do_periodo(periodo: str) -> list[str]:
    """Meses AAAAMM contidos num `periodo`, sem repetição e em ordem. Aceita
    o que as páginas gravam hoje:
      - `202602` e `202601 · 202602` (Processamento de relatórios);
      - `2026M06` (Douglas Cezar EP);
      - códigos AAAAMMDD (fica só o mês).
    Lista vazia quando não há mês reconhecível — a Reconciliação de pagamentos
    grava o nome da planilha, e isso não é um período."""
    texto = str(periodo)
    achados = [f"{a}{m}" for a, m in re.findall(r"(\d{4})M(\d{2})", texto)]
    achados += [t[:6] for t in re.findall(r"\d{6,8}", texto)]
    meses = []
    for m in achados:
        if 1 <= int(m[4:6]) <= 12 and m not in meses:
            meses.append(m)
    return sorted(meses)


def periodo_humano(periodo: str) -> str:
    """`202602` -> `Fev/2026`; vários meses do mesmo ano -> `Jan–Fev/2026`;
    anos diferentes -> `Dez/2025 · Jan/2026`. O que não tem mês reconhecível
    sai como veio."""
    meses = meses_do_periodo(periodo)
    if not meses:
        return str(periodo)
    nome = lambda m: MESES_PT[int(m[4:6]) - 1].capitalize()  # noqa: E731
    if len(meses) == 1:
        return f"{nome(meses[0])}/{meses[0][:4]}"
    if len({m[:4] for m in meses}) == 1:
        return f"{nome(meses[0])}–{nome(meses[-1])}/{meses[0][:4]}"
    return " · ".join(f"{nome(m)}/{m[:4]}" for m in meses)
