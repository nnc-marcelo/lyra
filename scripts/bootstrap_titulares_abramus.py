"""Semeia o de-para `titular do recibo -> catálogo` da RR.

Roda **fora do app** e uma vez só: o resultado é gravado em
`data/mapping/rr_titulares_abramus.json`, que é o que o Streamlit Cloud enxerga
(lá não existe o `Z:`). Rode de novo quando quiser reaprender do histórico.

Como aprende: para cada recibo (`_REC.pdf`) da pasta da ABRAMUS, soma o líquido
por titular e procura, no extrato da RR, a linha de mesmo valor dentro do
crédito bancário daquele recibo (o TOTAL do recibo bate com a soma das linhas
da RR daquela data). Os valores são praticamente únicos dentro de um mês, então
o casamento por valor é seguro — e ainda assim cada par vira um voto: o que
aparece em mais meses vence, e as divergências saem no relatório.

Aceita mais de um extrato: exportações parciais (um mês só) são comuns, e o
histórico completo costuma estar num arquivo antigo. Todos são concatenados.

Uso:
    python scripts/bootstrap_titulares_abramus.py "C:/caminho/rr.xlsx" [outro.xlsx ...]
"""

from __future__ import annotations

import glob
import json
import sys
from collections import Counter, defaultdict
from datetime import date
from pathlib import Path

import pandas as pd

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))

from utils.abramus_recibo import ler_recibo, normalizar, por_titular  # noqa: E402

CAMINHO_RECIBOS = r"Z:\ROYALTY\Royalties Statements_Historicals\Nas Nuvens Catalog\ABRAMUS\NAS NUVENS CATALOG S.A"
CAMINHO_CREDENCIAIS = RAIZ / "data" / "mapping" / "abramus_credentials_map.json"
CAMINHO_SAIDA = RAIZ / "data" / "mapping" / "rr_titulares_abramus.json"

# Folga para casar valor do recibo com valor da RR (frações abaixo de 1 centavo
# que o recibo não exibe no detalhe, mas soma no resumo).
TOLERANCIA = 0.05
# Folga para reconhecer o crédito bancário correspondente ao recibo.
TOLERANCIA_CREDITO = 50.00


def carregar_rr(*caminhos: str) -> pd.DataFrame:
    df = pd.concat([pd.read_excel(c) for c in caminhos], ignore_index=True)
    df = df.rename(columns={"Titular / Conta": "Titular", "Valor BRL": "Valor", "Período I": "Periodo"})
    df["Data"] = pd.to_datetime(df["Data"], errors="coerce")
    df["Valor"] = pd.to_numeric(df["Valor"], errors="coerce")
    df["Periodo"] = df.get("Periodo", "").astype(str).str.strip().str.upper()
    df = df[df["Data"].notna() & df["Valor"].notna() & df["Catalogo"].notna()]
    df = df[df["Fonte"].astype(str).str.upper() == "ABRAMUS"]
    # Extratos podem se sobrepor: a mesma linha em dois arquivos viraria voto em
    # dobro e, pior, consumiria duas candidatas no casamento por valor.
    return df.drop_duplicates(subset=["Data", "Catalogo", "Titular", "Valor"]).copy()


def credito_do_recibo(rr: pd.DataFrame, recibo) -> pd.DataFrame:
    """Linhas da RR correspondentes ao recibo.

    Primeiro procura o crédito bancário (linhas de uma mesma data) cuja soma
    chega mais perto do TOTAL do recibo — não é igualdade exata porque a RR
    arredonda as frações de outro jeito, então vale a menor diferença dentro de
    uma folga proporcional. Se nenhuma data servir (acontece quando o recibo foi
    lançado repartido em dois dias), cai para o mês inteiro do pagamento e, por
    último, para a competência anotada na coluna `Período I`."""
    melhor, menor_dif = pd.DataFrame(columns=rr.columns), None
    for _, grupo in rr.groupby(rr["Data"].dt.date):
        dif = abs(float(grupo["Valor"].sum()) - recibo.total)
        if menor_dif is None or dif < menor_dif:
            melhor, menor_dif = grupo, dif
    if menor_dif is not None and menor_dif <= max(TOLERANCIA_CREDITO, recibo.total * 0.001):
        return melhor

    if recibo.ano and recibo.mes:
        mesmo_mes = rr[(rr["Data"].dt.year == recibo.ano) & (rr["Data"].dt.month == recibo.mes)]
        if not mesmo_mes.empty:
            return mesmo_mes
    if recibo.competencia:
        return rr[rr["Periodo"] == recibo.competencia]
    return pd.DataFrame(columns=rr.columns)


def main() -> None:
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)

    rr = carregar_rr(*sys.argv[1:])
    print(f"RR: {len(rr)} linhas da fonte ABRAMUS, "
          f"{rr['Data'].dt.date.nunique()} créditos distintos.")

    recibos = sorted(glob.glob(str(Path(CAMINHO_RECIBOS) / "**" / "*_REC.pdf"), recursive=True))
    print(f"Recibos encontrados: {len(recibos)}\n")

    votos: dict[str, Counter] = defaultdict(Counter)
    nomes_originais: dict[str, str] = {}
    sem_credito: list[str] = []

    for caminho in recibos:
        recibo = ler_recibo(caminho)
        titulares = por_titular(recibo)
        titulares = titulares[(titulares["Titular"] != "") & (titulares["Valor"] > 0)]
        if titulares.empty:
            continue

        credito = credito_do_recibo(rr, recibo)
        if credito.empty:
            sem_credito.append(f"{recibo.competencia or Path(caminho).name} (total {recibo.total:,.2f})")
            continue

        usados: set = set()
        casados = 0
        for _, linha in titulares.iterrows():
            candidatas = credito[
                (credito["Valor"].sub(linha["Valor"]).abs() <= TOLERANCIA)
                & (~credito.index.isin(usados))
            ]
            if candidatas.empty:
                continue
            escolhida = candidatas.iloc[0]
            usados.add(candidatas.index[0])
            chave = normalizar(linha["Titular"])
            nomes_originais.setdefault(chave, linha["Titular"])
            votos[chave][str(escolhida["Catalogo"]).strip()] += 1
            casados += 1
        print(f"  {recibo.competencia:8s} {casados:3d}/{len(titulares):3d} titulares casados")

    credenciais = json.loads(CAMINHO_CREDENCIAIS.read_text(encoding="utf-8"))
    por_conta = {normalizar(c["account"]): c for c in credenciais}

    registros = []
    conflitos = []
    for chave, contagem in sorted(votos.items()):
        catalogo, n = contagem.most_common(1)[0]
        if len(contagem) > 1:
            conflitos.append((nomes_originais[chave], contagem.most_common()))
        registros.append({
            "titular_recibo": nomes_originais[chave],
            "chave": chave,
            "catalogo": catalogo,
            "origem": "historico",
            "ocorrencias": n,
        })

    # Completa com o mapa de credenciais quem nunca casou por valor: lá o campo
    # `account` é o mesmo nome que a ABRAMUS usa no recibo.
    conhecidos = {r["chave"] for r in registros}
    for chave, cred in sorted(por_conta.items()):
        if chave in conhecidos or not cred.get("artist"):
            continue
        registros.append({
            "titular_recibo": cred["account"],
            "chave": chave,
            # A RR grafa catálogo sem acento e em caixa alta.
            "catalogo": normalizar(cred["artist"]),
            "origem": "credenciais",
            "ocorrencias": 0,
        })

    saida = {
        "fonte": "ABRAMUS",
        "gerado_em": date.today().isoformat(),
        "titulares": sorted(registros, key=lambda r: r["chave"]),
    }
    CAMINHO_SAIDA.write_text(json.dumps(saida, ensure_ascii=False, indent=2), encoding="utf-8")

    do_historico = sum(1 for r in registros if r["origem"] == "historico")
    print(f"\n{len(registros)} titulares no de-para "
          f"({do_historico} aprendidos do histórico, {len(registros) - do_historico} das credenciais).")
    print(f"Gravado em {CAMINHO_SAIDA.relative_to(RAIZ)}")
    if sem_credito:
        print(f"\nRecibos sem crédito correspondente na RR ({len(sem_credito)}):")
        for item in sem_credito:
            print("  -", item)
    if conflitos:
        print(f"\nTitulares com mais de um destino no histórico ({len(conflitos)}) — venceu o mais frequente:")
        for nome, contagem in conflitos:
            print(f"  - {nome}: {contagem}")


if __name__ == "__main__":
    main()
