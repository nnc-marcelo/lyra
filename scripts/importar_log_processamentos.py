"""
Importa para o log de execuções (utils.execution_log) os relatórios já
processados manualmente e arquivados em
Z:\\ROYALTY\\_PROCESSAMENTOS_\\Arquivos processamento — reconstrói o histórico
que existia antes do log existir.

Só entra o que tem PROVA de ter passado pelo Processamento de relatórios: o
nome do arquivo bate exatamente com o que aquele template exporta
("..._Database.xlsx", "..._Detailed Consumption.xlsx",
"the_orchard_<catálogo>_consolidado_withholding...") — não com o nome do
arquivo baixado da distribuidora. A pasta de arquivamento mistura os dois:
tem catálogo do Orchard (Midas, MZA — que nem estão em ORCHARD_CATALOGOS
ainda) e trimestre da Luiza Possi (2026T02, em Jul/26) com só o download
bruto ao lado, sem o consolidado_withholding — não foi processado ainda, e
por isso fica de fora.

Uso:
    python scripts/importar_log_processamentos.py "Z:\\ROYALTY\\_PROCESSAMENTOS_\\Arquivos processamento\\2026\\07. Jul 26"

`quando` de cada entrada usa a data de modificação do arquivo (melhor proxy
disponível pra "quando foi processado" — o log não existia na época, não tem
o horário real). Não duplica: se já existe uma execução com esse `arquivo`
pra aquela página, pula — pode rodar de novo sem medo.
"""

from __future__ import annotations

import io
import re
import sys
from datetime import datetime
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from utils import execution_log  # noqa: E402
from views.processamento_relatorios import _periodo_da_coluna  # noqa: E402

PAGINA_BASE = "processamento_relatorios"


def _quando_do_arquivo(path: Path) -> str:
    return datetime.fromtimestamp(path.stat().st_mtime).isoformat(timespec="seconds")


def _ja_registrado(pagina: str, arquivo: str) -> bool:
    return any(ex.resumo.get("arquivo") == arquivo for ex in execution_log.historico(pagina))


def _registrar(slug: str, arquivo: str, periodo: str, resumo: dict, quando: str) -> None:
    pagina = f"{PAGINA_BASE}:{slug}"
    if _ja_registrado(pagina, arquivo):
        print(f"  já registrado, pulando: {arquivo}")
        return
    execution_log.registrar(pagina, str(periodo), resumo, quando=quando)
    print(f"  [{slug}] {execution_log.periodo_humano(periodo)} · {arquivo}")


def _aba_unica(path: Path, slug: str, aba: str) -> None:
    """iMusica e Claro Música: o arquivo já É a aba única exportada pelo
    template (`{original}_{aba}.xlsx`). Reconstrói o nome original tirando o
    sufixo, pra ficar igual ao que `render_aba_unica` teria gravado."""
    raw = path.read_bytes()
    df = pd.read_excel(io.BytesIO(raw), sheet_name=aba)
    periodo = _periodo_da_coluna(df, ("Period",)) or "?"
    arquivo_original = path.name[: -len(f"_{aba}.xlsx")] + ".xlsx"
    fv = pd.to_numeric(
        df.get("FinalValue", pd.Series(dtype=str)).astype(str).str.replace(",", ".", regex=False),
        errors="coerce",
    ).fillna(0).sum()
    resumo = {
        "arquivo": arquivo_original,
        "aba": aba,
        "linhas": int(len(df)),
        "colunas": int(len(df.columns)),
        "final_value_total": round(float(fv), 2),
        "origem": "importado do arquivo (Z:)",
    }
    _registrar(slug, arquivo_original, periodo, resumo, _quando_do_arquivo(path))


def _orchard(path: Path) -> None:
    """The Orchard: o arquivo já é o consolidado com withholding aplicado —
    não dá pra reconstruir bruto/débito (isso exigiria o(s) arquivo(s) de
    entrada, que não sobrevivem à consolidação), só o total líquido."""
    m = re.match(r"the_orchard_(.+?)_consolidado_withholding", path.name)
    if not m:
        return
    slug = m.group(1)
    raw = path.read_bytes()
    is_csv = path.suffix.lower() == ".csv"
    try:
        if is_csv:
            df = pd.read_csv(io.BytesIO(raw), low_memory=False, encoding="utf-8-sig")
            net_col = "NET SHARE ACCOUNT CURRENCY"
            per_cols = ("ORIGINAL STATEMENT PERIOD", "STATEMENT PERIOD")
        else:
            df = pd.read_excel(io.BytesIO(raw), engine="openpyxl")
            net_col = "Label Share Net Receipts"
            per_cols = ("Period",)
    except Exception as e:
        print(f"  [orchard:{slug}] erro ao ler {path.name}: {e}")
        return

    if net_col not in df.columns:
        print(f"  [orchard:{slug}] coluna '{net_col}' não encontrada em {path.name}, pulando")
        return

    total_liquido = float(
        pd.to_numeric(
            df[net_col].astype(str)
            .str.replace(",", "", regex=False)
            .str.replace("$", "", regex=False)
            .str.replace("(", "-", regex=False)
            .str.replace(")", "", regex=False),
            errors="coerce",
        ).fillna(0).sum()
    )
    periodo = _periodo_da_coluna(df, per_cols) or "?"
    resumo = {
        "arquivo": path.name,
        "linhas": int(len(df)),
        "total_liquido": round(total_liquido, 2),
        "origem": "importado do arquivo (Z:) — já consolidado, sem bruto/débito",
    }
    _registrar(f"orchard:{slug}", path.name, periodo, resumo, _quando_do_arquivo(path))


def importar(pasta: str) -> None:
    raiz = Path(pasta)
    print(f"Varrendo {raiz} ...")
    encontrados = 0
    for path in sorted(raiz.rglob("*")):
        if not path.is_file():
            continue
        nome = path.name
        if nome.endswith("_Database.xlsx"):
            encontrados += 1
            _aba_unica(path, "imusica", "Database")
        elif nome.endswith("_Detailed Consumption.xlsx"):
            encontrados += 1
            _aba_unica(path, "claro", "Detailed Consumption")
        elif nome.startswith("the_orchard_") and "_consolidado_withholding" in nome:
            encontrados += 1
            _orchard(path)
    print(f"\n{encontrados} arquivo(s) reconhecido(s) como já processado(s).")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("uso: python scripts/importar_log_processamentos.py <pasta>")
        sys.exit(1)
    importar(sys.argv[1])
