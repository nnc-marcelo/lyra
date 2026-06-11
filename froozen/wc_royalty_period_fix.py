"""
Warner Chappell - ajuste de formato da coluna royalty_period.

Mantem apenas os ultimos 6 digitos (ultimo mes do trimestre):
    202601202603 -> 202603
    202510202512 -> 202512

Processa o arquivo como texto cru (latin-1, round-trip lossless) e altera
SOMENTE o primeiro campo de cada linha de dados. Todos os demais bytes
(decimais de alta precisao, aspas, acentos, quebras de linha) sao preservados
exatamente como no original.
"""
import sys

SRC = r"Z:\ROYALTY\Royalties Statements_Historicals\Nas Nuvens Catalog\WARNER CHAPPELL\2026\1T 26\Statement_2026-01-01_2026-03-31.csv"
DST = r"Z:\ROYALTY\Royalties Statements_Historicals\Nas Nuvens Catalog\WARNER CHAPPELL\2026\1T 26\Statement_2026-01-01_2026-03-31_processado.csv"


def fix_period(field: str) -> str:
    return field[-6:]


def main() -> None:
    with open(SRC, "r", encoding="latin-1", newline="") as fh:
        lines = fh.readlines()  # mantem o '\n' de cada linha

    out = []
    out.append(lines[0])  # header inalterado

    changes = {}
    issues = []
    for i, line in enumerate(lines[1:], start=2):
        if line.strip() == "":
            out.append(line)  # preserva eventuais linhas em branco
            continue
        comma = line.find(",")
        if comma == -1:
            issues.append((i, "sem virgula"))
            out.append(line)
            continue
        period = line[:comma]
        if not (period.isdigit() and len(period) == 12):
            issues.append((i, f"campo inesperado: {period!r}"))
            out.append(line)
            continue
        new_period = fix_period(period)
        out.append(new_period + line[comma:])
        changes[(period, new_period)] = changes.get((period, new_period), 0) + 1

    with open(DST, "w", encoding="latin-1", newline="") as fh:
        fh.writelines(out)

    print(f"Linhas lidas : {len(lines)} (1 header + {len(lines)-1} dados)")
    print(f"Linhas escritas: {len(out)}")
    print("Transformacoes aplicadas:")
    for (old, new), n in sorted(changes.items()):
        print(f"   {old} -> {new}   ({n} linhas)")
    if issues:
        print(f"AVISOS ({len(issues)} linhas nao transformadas):")
        for ln, msg in issues[:20]:
            print(f"   linha {ln}: {msg}")
    else:
        print("Nenhum aviso: todas as linhas de dados foram transformadas.")
    print(f"\nArquivo gerado:\n{DST}")


if __name__ == "__main__":
    sys.exit(main())
