"""
Migra data/direct_incomes/regras.json do esquema antigo (chave 'historico'
de texto livre) para o novo (campos estruturados 'titular' + 'origem'),
acompanhando a troca de template do BI.

Motivo: no template antigo, a coluna 'Historico' juntava operação + titular
num texto só (ex.: "VENDA CATALOGO - CESSAO - ZEIDER FERNANDO PIRES"). No novo
template isso virou duas colunas: 'Origem/Detalhe' (VENDA CATALOGO / TRANSFERIDO)
e 'Titular / Conta' (ZEIDER, Z Produções, Helena, Polaroide...).

Cada (catalogo, fonte, historico) existente é mapeado para (titular, origem).
Regras sem historico recebem titular=None, origem=None. Rode uma vez:

    python froozen/_migrate_rules_to_titular_origem.py
"""

import json
from pathlib import Path

RULES_PATH = Path(__file__).resolve().parent.parent / "data" / "direct_incomes" / "regras.json"

# (catalogo, fonte, historico_antigo) -> (titular, origem)
MAPA = {
    # ACCIOLY/UBC: os dois historicos tinham incomes idênticos -> viram uma regra
    # genérica (titular/origem nulos). Revisar quando ACCIOLY aparecer no novo BI.
    ("ACCIOLY", "UBC", "REPASSE - Lalu"): (None, None),
    ("ACCIOLY", "UBC", "ADMINISTRACAO LALU EDICOES"): (None, None),

    # LAZAO: ATENÇÃO — direção invertida vs Zeider (TRANSFERIDO = aquisição).
    # Preservado como estava no notebook; confirmar com o time.
    ("LAZAO", "ABRAMUS", "TRANSFERIDO DE POP MUNDI PRODUCOES ARTISTICAS LTDA"): ("POP MUNDI", "TRANSFERIDO"),
    ("LAZAO", "ABRAMUS", "VENDA CATALOGO - CESSAO - POP MUNDI PRODUCOES ARTISTICAS LTDA"): ("POP MUNDI", "VENDA CATALOGO"),

    # CELSO FONSECA/UBC: discrimina por titular (sem origem)
    ("CELSO FONSECA", "UBC", "ADMINISTRACAO CELSO JOSE DA FONSECA"): ("CELSO FONSECA", None),
    ("CELSO FONSECA", "UBC", "REPASSE CELSO FONSECA"): ("POLAROIDE", None),

    # LUIZA POSSI/ABRAMUS: titular (LUIZA POSSI / HELENA) x origem (VENDA / TRANSFERIDO)
    ("LUIZA POSSI", "ABRAMUS", "VENDA CATALOGO - CESSAO - LUIZA POSSI GADELHA"): ("LUIZA POSSI", "VENDA CATALOGO"),
    ("LUIZA POSSI", "ABRAMUS", "VENDA CATALOGO - CESSAO - HELENA PRODUCOES ARTISTICAS LTDA ME"): ("HELENA", "VENDA CATALOGO"),
    ("LUIZA POSSI", "ABRAMUS", "TRANSFERIDO DE LUIZA POSSI GADELHA"): ("LUIZA POSSI", "TRANSFERIDO"),
    ("LUIZA POSSI", "ABRAMUS", "TRANSFERIDO DE HELENA"): ("HELENA", "TRANSFERIDO"),

    # ZEIDER/ABRAMUS: titular (ZEIDER / Z PRODUCOES) x origem (VENDA / TRANSFERIDO)
    ("ZEIDER", "ABRAMUS", "VENDA CATALOGO - CESSAO - ZEIDER FERNANDO PIRES"): ("ZEIDER", "VENDA CATALOGO"),
    ("ZEIDER", "ABRAMUS", "TRANSFERIDO DE ZEIDER FERNANDO PIRES"): ("ZEIDER", "TRANSFERIDO"),
    ("ZEIDER", "ABRAMUS", "VENDA CATALOGO - CESSAO - Z PRODUCOES ARTISTICAS LTDA - ME"): ("Z PRODUCOES", "VENDA CATALOGO"),
    ("ZEIDER", "ABRAMUS", "TRANSFERIDO DE Z PRODUCOES ARTISTICAS LTDA - ME"): ("Z PRODUCOES", "TRANSFERIDO"),
}


def main():
    data = json.loads(RULES_PATH.read_text(encoding="utf-8"))
    novas = []
    vistas = set()
    avisos = []

    for r in data["regras"]:
        cat, fonte, hist = r["catalogo"], r["fonte"], r.get("historico")

        if hist is None:
            titular, origem = None, None
        elif (cat, fonte, hist) in MAPA:
            titular, origem = MAPA[(cat, fonte, hist)]
        else:
            # fallback: deduz origem do texto; titular fica para revisão manual
            up = hist.upper()
            if up.startswith("VENDA CATALOGO"):
                origem = "VENDA CATALOGO"
            elif up.startswith("TRANSFERIDO"):
                origem = "TRANSFERIDO"
            else:
                origem = None
            titular = None
            avisos.append(f"sem mapa explicito: ({cat}, {fonte}, {hist!r}) -> titular=None, origem={origem!r}")

        nova = {
            "catalogo": cat,
            "fonte": fonte,
            "titular": titular,
            "origem": origem,
            "money_in": r.get("money_in"),
            "incomes": r["incomes"],
        }

        chave = (cat, fonte, titular, origem)
        if chave in vistas:
            avisos.append(f"regra duplicada descartada: {chave}")
            continue
        vistas.add(chave)
        novas.append(nova)

    out = {"periodo": data.get("periodo", ""), "regras": novas}
    RULES_PATH.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"OK: {len(data['regras'])} regras -> {len(novas)} apos migracao/dedupe")
    com_disc = sum(1 for r in novas if r["titular"] or r["origem"])
    print(f"     {com_disc} regras com titular/origem; {len(novas) - com_disc} genericas (cat+fonte)")
    for a in avisos:
        print("AVISO:", a)


if __name__ == "__main__":
    main()
