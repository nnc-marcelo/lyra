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


def registrar(pagina: str, periodo: str, resumo: dict[str, Any], quando: str | None = None) -> None:
    """Acrescenta uma linha ao log. `resumo` é de livre escolha da página
    (cada uma sabe o que vale registrar), mas precisa ser serializável em
    JSON puro — valores numpy/pandas devem virar float/int antes de chegar
    aqui, senão o `json.dumps` quebra.

    `quando` normalmente é omitido (vira "agora"); existe só para os scripts
    de importação de histórico (ex.: scripts/importar_log_processamentos.py),
    que reconstroem execuções passadas a partir de arquivos já arquivados e
    usam a data de modificação do arquivo como proxy de quando rodou."""
    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    execucao = Execucao(
        pagina=pagina,
        periodo=periodo,
        quando=quando or datetime.now().isoformat(timespec="seconds"),
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


def mes_seguinte(aaaamm: str) -> str:
    ano, mes = int(aaaamm[:4]), int(aaaamm[4:6]) + 1
    return f"{ano + 1}01" if mes == 13 else f"{ano}{mes:02d}"


def mes_anterior(aaaamm: str) -> str:
    ano, mes = int(aaaamm[:4]), int(aaaamm[4:6]) - 1
    return f"{ano - 1}12" if mes == 0 else f"{ano}{mes:02d}"


def periodo_codigo(periodo: str) -> str:
    """`202602` -> `2026M02` (o formato que o Douglas Cezar EP já grava);
    meses seguidos -> `2025M10–2026M03`; meses soltos -> `2026M01, 2026M03`.
    Ordena como texto na ordem certa. O que não tem mês reconhecível sai
    como veio."""
    meses = meses_do_periodo(periodo)
    if not meses:
        return str(periodo)
    sequencias = [[meses[0]]]
    for m in meses[1:]:
        if m == mes_seguinte(sequencias[-1][-1]):
            sequencias[-1].append(m)
        else:
            sequencias.append([m])
    codigo = lambda m: f"{m[:4]}M{m[4:6]}"  # noqa: E731
    return ", ".join(
        codigo(s[0]) if len(s) == 1 else f"{codigo(s[0])}–{codigo(s[-1])}"
        for s in sequencias
    )
