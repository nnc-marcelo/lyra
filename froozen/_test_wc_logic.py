"""Testa a logica _wc_fix_periods contra o arquivo real (sem Streamlit)."""

def _wc_fix_periods(raw):
    text = raw.decode("latin-1")
    lines = text.split("\n")
    out = [lines[0]]
    changes, issues = {}, 0
    for line in lines[1:]:
        if line.strip() == "":
            out.append(line)
            continue
        comma = line.find(",")
        period = line[:comma] if comma != -1 else ""
        if comma != -1 and period.isdigit() and len(period) >= 6:
            new = period[-6:]
            out.append(new + line[comma:])
            changes[(period, new)] = changes.get((period, new), 0) + 1
        else:
            out.append(line)
            issues += 1
    return "\n".join(out).encode("latin-1"), changes, issues


SRC = r"Z:\ROYALTY\Royalties Statements_Historicals\Nas Nuvens Catalog\WARNER CHAPPELL\2026\1T 26\Statement_2026-01-01_2026-03-31.csv"
raw = open(SRC, "rb").read()
processed, changes, issues = _wc_fix_periods(raw)

a = raw.decode("latin-1").split("\n")
b = processed.decode("latin-1").split("\n")
print("Linhas original:", len(a), "| processado:", len(b))
print("Header identico:", a[0] == b[0])
bad = 0
for i in range(1, len(a)):
    if a[i].strip() == "" and b[i].strip() == "":
        continue
    if a[i][6:] != b[i]:
        bad += 1
print("Linhas onde (original sem 6 primeiros chars) != processado:", bad)
print("Avisos:", issues)
print("Mapeamentos:")
for (o, n), c in sorted(changes.items()):
    print(f"   {o} -> {n}  ({c})")
