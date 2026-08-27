"""Do recibo de uma fonte para as linhas da RR (Revenue Reconciliation).

A RR registra, para cada crédito que cai no banco, uma linha por
**catálogo × titular**. O recibo da ABRAMUS já traz essa quebra na parte de
venda de catálogo; o que falta é traduzir o nome do titular (nome civil ou razão
social, como a ABRAMUS grafa) para o catálogo, e é isso que o de-para em
`data/mapping/rr_titulares_abramus.json` faz. O **titular sai exatamente como
está no recibo** — o de-para guarda só o catálogo.

O repertório próprio é a parte que o recibo não quebra, e são dois rateios
distintos, cada um com sua fonte de detalhe:

* **execução pública no Brasil** — detalhada obra a obra no `_XLS.csv`; quem
  agrupa por catálogo é a página de Cruzamento com catálogo, e é o xlsx dela que
  entra aqui;
* **direito autoral do exterior** (rubrica `DIR AUTORAL EXTERIOR`) — não está no
  `_XLS.csv`; o detalhe vem no `_INT.pdf`, que este módulo cruza com a base de
  obras da ABRAMUS por ISWC (e, quando falta, por título).

Sem `streamlit` de propósito: a página (`views/rr_conciliacao.py`) cuida só da
tela, e esta lógica pode ser exercitada sem subir o app — mesma razão de
`utils/bi_extract.py` e `utils/bases.py` existirem separados.
"""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from utils.abramus_pdf import ler_internacional as _ler_internacional_pdf
from utils.abramus_recibo import Recibo, normalizar, por_titular

RAIZ = Path(__file__).resolve().parents[1]
CAMINHO_DEPARA = RAIZ / "data" / "mapping" / "rr_titulares_abramus.json"
# Mesma base de obras que a página de cruzamento usa para a ABRAMUS.
CAMINHO_BASE_OBRAS = RAIZ / "data" / "mapping" / "Robo_Abramus_Base.xlsx"

FONTE_ABRAMUS = "ABRAMUS"
# Titular que a RR usa para o que é do repertório da própria Nas Nuvens.
TITULAR_PROPRIO = "NAS NUVENS CATALOG"

ORIGEM_VENDA = "Venda de catálogo"
ORIGEM_DEBITO = "Débito"
ORIGEM_PROPRIO = "Repertório próprio"
ORIGEM_EXTERIOR = "Direito autoral do exterior"
ORIGEM_DESPESA = "Despesas bancárias"
SUFIXO_RESIDUO = " (resíduo)"

MAPEAMENTO_PENDENTE = "pendente"
MAPEAMENTO_DEBITO = "débito"
MAPEAMENTO_MANUAL = "manual"
MAPEAMENTO_A_RATEAR = "a ratear pelo cruzamento"
MAPEAMENTO_A_RATEAR_INT = "a ratear pelo _INT.pdf"
MAPEAMENTO_CRUZAMENTO = "cruzamento"
MAPEAMENTO_INT = "_INT.pdf"

COLUNAS_SAIDA = ["Período", "Catálogo", "Titular", "Valor"]
COLUNAS = COLUNAS_SAIDA + ["Origem", "Titular no recibo", "Mapeamento"]


# ---------------------------------------------------------------------------
# De-para de titulares
# ---------------------------------------------------------------------------
def carregar_depara(caminho: Path = CAMINHO_DEPARA) -> dict:
    """De-para indexado pela chave normalizada do titular do recibo."""
    if not Path(caminho).exists():
        return {}
    dados = json.loads(Path(caminho).read_text(encoding="utf-8"))
    return {t["chave"]: t for t in dados.get("titulares", [])}


def gravar_depara(mapa: dict, caminho: Path = CAMINHO_DEPARA, fonte: str = FONTE_ABRAMUS) -> None:
    Path(caminho).parent.mkdir(parents=True, exist_ok=True)
    conteudo = {
        "fonte": fonte,
        "gerado_em": pd.Timestamp.today().date().isoformat(),
        "titulares": sorted(mapa.values(), key=lambda t: t["chave"]),
    }
    Path(caminho).write_text(json.dumps(conteudo, ensure_ascii=False, indent=2), encoding="utf-8")


def entrada_depara(titular_recibo: str, catalogo: str) -> dict:
    chave = normalizar(titular_recibo)
    return {
        "titular_recibo": titular_recibo,
        "chave": chave,
        "catalogo": str(catalogo).strip(),
        "origem": MAPEAMENTO_MANUAL,
        "ocorrencias": 0,
    }


def novos_mapeamentos(linhas: pd.DataFrame) -> pd.DataFrame:
    """Linhas editadas na tela que valem virar entrada no de-para: são de um
    titular do recibo (não do repertório próprio nem de despesa), ainda não
    resolvidas pelo de-para, e ganharam um catálogo à mão."""
    return linhas[
        linhas["Origem"].isin([ORIGEM_VENDA, ORIGEM_DEBITO])
        & (linhas["Catálogo"].astype(str).str.strip() != "")
        & linhas["Mapeamento"].isin([MAPEAMENTO_PENDENTE, MAPEAMENTO_DEBITO])
    ]


def aplicar_mapeamentos(mapa: dict, linhas: pd.DataFrame) -> dict:
    """Novo de-para com as linhas informadas incorporadas. Não muta o original —
    o chamador decide quando trocar o que está em sessão."""
    atualizado = dict(mapa)
    for _, linha in linhas.iterrows():
        entrada = entrada_depara(linha["Titular no recibo"], linha["Catálogo"])
        atualizado[entrada["chave"]] = entrada
    return atualizado


# ---------------------------------------------------------------------------
# Detalhe do repertório próprio
# ---------------------------------------------------------------------------
def ler_agrupado(arquivo) -> pd.DataFrame:
    """Relatório agrupado do cruzamento com catálogo: uma linha por catálogo,
    valor na coluna RATEIO. É ele que quebra a execução pública, que o recibo
    entrega como um bolo só. Levanta `ValueError` se não for esse arquivo."""
    df = pd.read_excel(arquivo)
    colunas = {str(c).strip().upper(): c for c in df.columns}
    col_cat = colunas.get("CATÁLOGO") or colunas.get("CATALOGO")
    col_val = colunas.get("RATEIO") or colunas.get("VALOR")
    if not col_cat or not col_val:
        raise ValueError("O relatório agrupado precisa ter as colunas CATÁLOGO e RATEIO.")
    catalogo = df[col_cat].astype(str).str.strip()
    # Obra sem catálogo no cruzamento vira linha em branco explícita, em vez de
    # sumir dentro do resíduo.
    catalogo = catalogo.where(~catalogo.str.lower().isin(["nan", "none", "(sem catálogo)"]), "")
    return pd.DataFrame({
        "Catálogo": catalogo,
        "Valor": pd.to_numeric(df[col_val], errors="coerce").fillna(0.0),
    })


def _lookup_obras(caminho: Path = CAMINHO_BASE_OBRAS) -> tuple[dict, dict]:
    """(por ISWC, por título normalizado) -> catálogo, a partir da base de obras
    da ABRAMUS. Quando a mesma obra aparece com mais de um catálogo, vence o
    mais frequente."""
    if not Path(caminho).exists():
        return {}, {}
    base = pd.read_excel(caminho)
    base = base.dropna(subset=["CATÁLOGO"])
    base["_iswc"] = base["ISWC"].astype(str).str.replace(r"[^A-Za-z0-9]", "", regex=True).str.upper()
    base["_titulo"] = base["TÍTULO DA MUSICA"].map(normalizar)
    def moda(coluna):
        valido = base[base[coluna] != ""]
        return valido.groupby(coluna)["CATÁLOGO"].agg(lambda s: s.mode()[0]).to_dict()
    return moda("_iswc"), moda("_titulo")


def ler_internacional(arquivo, caminho_base: Path = CAMINHO_BASE_OBRAS) -> pd.DataFrame:
    """Demonstrativo internacional (`_INT.pdf`) agrupado por catálogo.

    O PDF traz obra, ISWC e rendimento, mas nenhum catálogo — ele vem da base de
    obras da ABRAMUS, cruzando por ISWC e, quando o ISWC não está na base, por
    título. O que não casar sai com catálogo em branco, para aparecer na tela em
    vez de se perder no resíduo.
    """
    detalhe = _ler_internacional_pdf(arquivo)
    if detalhe.empty:
        return pd.DataFrame(columns=["Catálogo", "Valor", "Obras"])

    por_iswc, por_titulo = _lookup_obras(caminho_base)

    def resolver(linha):
        iswc = str(linha["ISRC/ISWC"]).replace("-", "").upper()
        if por_iswc.get(iswc):
            return por_iswc[iswc], False
        # Sem ISWC na base, cai no título — menos seguro: há obras homônimas de
        # autores diferentes, e o valor casado assim é reportado à parte.
        return por_titulo.get(normalizar(linha["Título"]), ""), True

    detalhe = detalhe.copy()
    resolvido = detalhe.apply(resolver, axis=1, result_type="expand")
    detalhe["Catálogo"], detalhe["_por_titulo"] = resolvido[0], resolvido[1]
    detalhe["_valor_titulo"] = detalhe["Rendimento"].where(
        detalhe["_por_titulo"] & (detalhe["Catálogo"] != ""), 0.0
    )
    agrupado = detalhe.groupby("Catálogo", as_index=False).agg(
        Valor=("Rendimento", "sum"),
        Obras=("Título", "nunique"),
        **{"Casado só por título": ("_valor_titulo", "sum")},
    )
    agrupado["Valor"] = agrupado["Valor"].round(2)
    agrupado["Casado só por título"] = agrupado["Casado só por título"].round(2)
    return agrupado.sort_values("Valor", ascending=False, ignore_index=True)


# ---------------------------------------------------------------------------
# Linhas da RR
# ---------------------------------------------------------------------------
def _linha(periodo, catalogo, titular, valor, origem, titular_recibo, mapeamento) -> dict:
    return {
        "Período": periodo,
        "Catálogo": catalogo,
        "Titular": titular,
        "Valor": round(float(valor), 2),
        "Origem": origem,
        "Titular no recibo": titular_recibo,
        "Mapeamento": mapeamento,
    }


def linhas_do_recibo(
    recibo: Recibo,
    mapa: dict,
    agrupado: pd.DataFrame | None = None,
    internacional: pd.DataFrame | None = None,
) -> pd.DataFrame:
    """Linhas da RR correspondentes a um recibo.

    A soma das linhas fecha com o crédito bancário: despesas e retenções entram
    como linha negativa própria, em vez de sumirem no arredondamento.
    """
    registros: list[dict] = []
    periodo = recibo.competencia

    for _, linha in por_titular(recibo).iterrows():
        titular_recibo = linha["Titular"]
        entrada = mapa.get(normalizar(titular_recibo)) if titular_recibo else None
        negativo = linha["Valor"] < 0

        if entrada:
            catalogo, mapeamento = entrada.get("catalogo", ""), entrada.get("origem", "de-para")
        elif negativo:
            # Débito de editora: fica sem catálogo, identificado só pelo titular —
            # a alocação correta é decisão à parte, fora do que o recibo informa.
            catalogo, mapeamento = "", MAPEAMENTO_DEBITO
        else:
            catalogo, mapeamento = "", MAPEAMENTO_PENDENTE

        registros.append(_linha(
            periodo, catalogo, titular_recibo, linha["Valor"],
            ORIGEM_DEBITO if negativo else ORIGEM_VENDA,
            titular_recibo or "(sem titular no recibo)", mapeamento,
        ))

    registros.extend(_bloco_rateado(
        recibo, recibo.valor_ecad, agrupado,
        ORIGEM_PROPRIO, "(repertório próprio)", MAPEAMENTO_CRUZAMENTO, MAPEAMENTO_A_RATEAR,
    ))
    registros.extend(_bloco_rateado(
        recibo, recibo.valor_exterior, internacional,
        ORIGEM_EXTERIOR, "(direito autoral do exterior)", MAPEAMENTO_INT, MAPEAMENTO_A_RATEAR_INT,
    ))

    for chave, rotulo in (("despesas_bancarias", "DESPESAS BANCÁRIAS"), ("irrf", "IRRF")):
        valor = recibo.resumo.get(chave, 0.0)
        if abs(valor) >= 0.01:
            registros.append(_linha(
                periodo, "", rotulo, -valor, ORIGEM_DESPESA,
                f"({rotulo.lower()})", MAPEAMENTO_DEBITO,
            ))

    return pd.DataFrame(registros, columns=COLUNAS)


def _bloco_rateado(
    recibo: Recibo,
    total: float,
    detalhe: pd.DataFrame | None,
    origem: str,
    rotulo: str,
    mapeamento: str,
    mapeamento_sem_detalhe: str,
) -> list[dict]:
    """Um bloco do repertório próprio, rateado pelo detalhe correspondente.

    Sem o arquivo de detalhe, sai numa linha só, marcada com o que falta subir.
    Com ele, sai uma linha por catálogo — e a sobra vira uma linha de resíduo,
    em vez de ser diluída nos catálogos: em geral são as frações abaixo de um
    centavo, mas pode ser obra que o detalhe não soube atribuir.
    """
    total = round(total, 2)
    if abs(total) < 0.01:
        return []
    periodo = recibo.competencia

    if detalhe is None or detalhe.empty:
        return [_linha(periodo, "", TITULAR_PROPRIO, total, origem, rotulo, mapeamento_sem_detalhe)]

    registros = [
        _linha(
            periodo, linha["Catálogo"], TITULAR_PROPRIO, linha["Valor"], origem, rotulo,
            mapeamento if str(linha["Catálogo"]).strip() else MAPEAMENTO_PENDENTE,
        )
        for _, linha in detalhe.iterrows()
        if abs(float(linha["Valor"])) >= 0.005
    ]
    residuo = round(total - float(detalhe["Valor"].sum()), 2)
    if abs(residuo) >= 0.01:
        registros.append(_linha(
            periodo, "", TITULAR_PROPRIO, residuo, origem + SUFIXO_RESIDUO,
            rotulo, MAPEAMENTO_PENDENTE,
        ))
    return registros
