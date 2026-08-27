"""Leitura do recibo (DEMONSTRATIVO DE PAGAMENTO) da ABRAMUS em PDF.

É o documento que fecha com o crédito que cai no banco: o `TOTAL` do cabeçalho
é exatamente o valor da transferência. O detalhe vem em duas naturezas, e a
distinção é o que sustenta a conciliação:

* **relacionamento** — linhas `VENDA CATALOGO - <MODALIDADE> - <TITULAR>` (e
  `CESSÃO PARA PJ`): catálogos adquiridos, **já quebrados por titular**. É daqui
  que sai, direto, o valor de cada catálogo.
* **próprio** — linhas prefixadas pelo número do demonstrativo da própria
  titular (ex.: `22710786 SHOW`) e `DIR AUTORAL EXTERIOR`: repertório
  registrado na própria conta, detalhado por rubrica e **sem qualquer quebra
  por catálogo**. Ratear esse bolo exige o analítico por obra (`_XLS.csv`), que
  é o que a página de cruzamento com catálogo faz.

O módulo é puro (sem `streamlit`) para ser testável e reusável — mesma razão de
`utils/bi_extract.py` e `utils/bases.py` existirem separados das páginas.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field

import pandas as pd
import pdfplumber

# Um valor monetário do recibo: "1.234,56", "0,00", "-12,30".
_NUM = r"(-?[\d.]+,\d{2})"

# Linha de detalhe: descrição + referência (MM.AAAA) + débito + crédito.
# A referência é o que separa detalhe de cabeçalho/rodapé repetidos a cada
# página — nenhuma outra linha do documento tem esse formato.
_RE_LINHA = re.compile(r"^(.*?)\s+(\d{2}\.\d{4})\s+" + _NUM + r"\s+" + _NUM + r"$")
_RE_TOTAL_CATEGORIA = re.compile(r"^Total da categoria\s+(.+?)\s+" + _NUM + r"\s+" + _NUM + r"$")
# Em 2022 o mês vinha na linha seguinte ao título; daí a busca no texto inteiro
# (com `\s+` cobrindo a quebra de linha) em vez de linha a linha.
_RE_COMPETENCIA = re.compile(r"DEMONSTRATIVO DE PAGAMENTO\s+([A-ZÇÃÊÁÍÓÚ]+)\s*/\s*(\d{4})", re.IGNORECASE)
# O TOTAL do topo vem grudado na razão social ("NAS NUVENS CATALOG S.A. TOTAL 563.408,09");
# o `(?<!SUB)` evita casar com o SUBTOTAL do resumo.
_RE_TOTAL = re.compile(r"(?<!SUB)TOTAL\s*=?\s*" + _NUM)
_RE_RECIBO = re.compile(r"RECIBO\s+(\d+)")
_RE_ECAD = re.compile(r"ECAD\s*(\d{6,})")

# Linha de repertório próprio: começa com o número do demonstrativo da titular.
_RE_PROPRIO = re.compile(r"^(\d{5,})\s+(.*)$")

# `VENDA CATALOGO - CESSAO - FULANO`, `VENDA DE CATÁLOGO - CESSÃO` (formato de
# 2022/2023, sem quebra por titular) e `CESSÃO PARA PJ - 100,00% - FULANA LTDA`.
_RE_VENDA = re.compile(r"^VENDA\s+(?:DE\s+)?CAT[ÁA]LOGO\s*-\s*(.+)$", re.IGNORECASE)
_RE_CESSAO_PJ = re.compile(r"^(CESS[ÃA]O PARA PJ)\s*-\s*([\d,]+%)\s*-\s*(.+)$")

_MESES = {
    "JANEIRO": 1, "FEVEREIRO": 2, "MARCO": 3, "ABRIL": 4, "MAIO": 5, "JUNHO": 6,
    "JULHO": 7, "AGOSTO": 8, "SETEMBRO": 9, "OUTUBRO": 10, "NOVEMBRO": 11, "DEZEMBRO": 12,
}

# Rótulos do bloco MENSAGEM RESUMO, no fim do documento.
_RESUMO_CAMPOS = {
    "credito": "Crédito",
    "antecipacao": "Antecipação",
    "credito_relacionamento": "Crédito de Relacionamento",
    "amortizacao_antecipacao": "Amortização de Antecipação",
    "amortizacao_adiantamento": "Amortização de Adiantamento",
    "aviso_debito": "Aviso de Débito",
    "debito_relacionamento": "Débito de Relacionamento",
    "outros_debitos": "Outros Débitos",
    "irrf": "IRRF",
    "subtotal": "SUBTOTAL",
    "despesas_bancarias": "Despesas bancárias",
}

TIPO_PROPRIO = "PRÓPRIO"
TIPO_RELACIONAMENTO = "RELACIONAMENTO"

# Rubrica do direito autoral recebido das sociedades estrangeiras. Ela entra no
# bloco próprio mas NÃO está no analítico do ECAD (`_XLS.csv`) — o detalhe por
# obra vem no demonstrativo internacional (`_INT.pdf`). Por isso é somada à
# parte: são dois rateios diferentes.
RUBRICA_EXTERIOR = "DIR AUTORAL EXTERIOR"

COLUNAS = ["Categoria", "Tipo", "Modalidade", "Titular", "Rubrica", "Referência", "Débito", "Crédito", "Valor"]


@dataclass
class Recibo:
    """Recibo lido. `linhas` é o detalhe; `total` é o que caiu no banco."""

    competencia: str = ""          # "2026M06"
    competencia_extenso: str = ""  # "JUNHO/2026"
    ano: int | None = None
    mes: int | None = None
    numero: str = ""               # nº do recibo (22548)
    ecad: str = ""
    titular: str = ""              # razão social no topo
    demonstrativo: str = ""        # código que prefixa as linhas de repertório próprio
    total: float = 0.0
    linhas: pd.DataFrame = field(default_factory=lambda: pd.DataFrame(columns=COLUNAS))
    resumo: dict = field(default_factory=dict)
    avisos: list[str] = field(default_factory=list)

    @property
    def valor_relacionamento(self) -> float:
        return float(self.linhas.loc[self.linhas["Tipo"] == TIPO_RELACIONAMENTO, "Valor"].sum())

    @property
    def valor_proprio(self) -> float:
        return float(self.linhas.loc[self.linhas["Tipo"] == TIPO_PROPRIO, "Valor"].sum())

    @property
    def valor_exterior(self) -> float:
        """Parte do repertório próprio que veio do exterior — rateada pelo
        `_INT.pdf`, não pelo analítico do ECAD."""
        proprio = self.linhas["Tipo"] == TIPO_PROPRIO
        exterior = self.linhas["Rubrica"].str.startswith(RUBRICA_EXTERIOR, na=False)
        return float(self.linhas.loc[proprio & exterior, "Valor"].sum())

    @property
    def valor_ecad(self) -> float:
        """Repertório próprio de execução pública no Brasil — é o que o
        `_XLS.csv` (e portanto o cruzamento) detalha por obra."""
        return round(self.valor_proprio - self.valor_exterior, 2)


def valor_br(texto: str) -> float:
    """1.234,56 -> 1234.56."""
    return float(str(texto).replace(".", "").replace(",", "."))


def normalizar(texto) -> str:
    """Maiúsculas, sem acento, sem pontuação, espaços colapsados — chave de
    comparação de nomes de titular entre o recibo e a RR."""
    s = unicodedata.normalize("NFKD", str(texto if texto is not None else ""))
    s = s.encode("ascii", "ignore").decode().upper()
    return " ".join(re.sub(r"[^A-Z0-9 ]", " ", s).split())


def _extrair_texto(pdf_file) -> list[str]:
    if hasattr(pdf_file, "seek"):
        pdf_file.seek(0)
    linhas: list[str] = []
    with pdfplumber.open(pdf_file) as pdf:
        for pagina in pdf.pages:
            linhas.extend((pagina.extract_text() or "").split("\n"))
    return [ln.strip() for ln in linhas]


def _classificar(descricao: str) -> tuple[str, str, str, str]:
    """(tipo, modalidade, titular, rubrica) a partir da descrição da linha."""
    m = _RE_PROPRIO.match(descricao)
    if m:
        return TIPO_PROPRIO, "", "", m.group(2).strip()
    if descricao.upper().startswith("DIR AUTORAL EXTERIOR"):
        return TIPO_PROPRIO, "", "", descricao.strip()
    m = _RE_CESSAO_PJ.match(descricao)
    if m:
        return TIPO_RELACIONAMENTO, f"{m.group(1)} {m.group(2)}", m.group(3).strip(), ""
    m = _RE_VENDA.match(descricao)
    if m:
        # Só a PRIMEIRA " - " separa modalidade de titular: razão social costuma
        # trazer mais hífens ("SETE MARES PRODUCOES ARTISTICAS LTDA - ME").
        partes = m.group(1).strip().split(" - ", 1)
        if len(partes) == 2:
            return TIPO_RELACIONAMENTO, partes[0].strip(), partes[1].strip(), ""
        # Recibo antigo (até 2023): uma linha só por modalidade, sem titular.
        return TIPO_RELACIONAMENTO, partes[0].strip(), "", ""
    # Formato desconhecido: entra como relacionamento sem modalidade, para
    # aparecer na tela em vez de sumir da conciliação.
    return TIPO_RELACIONAMENTO, "", descricao.strip(), ""


def _ler_resumo(texto: str) -> dict:
    """Bloco MENSAGEM RESUMO (fim do documento). Os rótulos vêm no fim de linhas
    que também carregam o texto do aviso, então procura-se o rótulo seguido de
    sinal e valor em qualquer posição — mas só depois do marcador do bloco, para
    não capturar o cabeçalho das colunas ("... Débito Crédito")."""
    resumo: dict = {}
    corte = texto.find("MENSAGEM RESUMO")
    trecho = texto[corte:] if corte >= 0 else texto
    for chave, rotulo in _RESUMO_CAMPOS.items():
        m = re.search(re.escape(rotulo) + r"\s*[+\-=]\s*" + _NUM, trecho)
        if m:
            resumo[chave] = valor_br(m.group(1))
    m = _RE_TOTAL.search(trecho)
    if m:
        resumo["total"] = valor_br(m.group(1))
    return resumo


def _ler_cabecalho(texto: str, linhas_texto: list[str]) -> Recibo:
    """Competência, nº do recibo, ECAD e TOTAL. O layout mudou ao longo
    dos anos (em 2022 o mês ficava numa linha só dele), então a leitura é feita
    no texto inteiro, não posicionalmente."""
    recibo = Recibo()

    m = _RE_COMPETENCIA.search(texto)
    if not m:
        # O extrator às vezes espaça o título ("DEM ON STRATIVO DE PAGAM EN TO");
        # nesses casos a competência é uma linha só dela.
        m = re.search(r"^\s*([A-ZÇÃÊÁÍÓÚ]{4,})\s*/\s*(\d{4})\s*$", texto, re.MULTILINE)
    if m:
        mes = _MESES.get(normalizar(m.group(1)))
        if mes:
            recibo.ano, recibo.mes = int(m.group(2)), mes
            recibo.competencia = f"{recibo.ano}M{mes:02d}"
            recibo.competencia_extenso = f"{normalizar(m.group(1))}/{recibo.ano}"

    m = _RE_TOTAL.search(texto)
    if m:
        recibo.total = valor_br(m.group(1))
    m = _RE_RECIBO.search(texto)
    if m:
        recibo.numero = m.group(1)
    m = _RE_ECAD.search(texto)
    if m:
        recibo.ecad = m.group(1)
    # Razão social: primeira linha que não seja o título nem o TOTAL (que em
    # alguns anos vem numa linha própria e em outros grudado na razão social,
    # junto de "PAGAMENTO Doc").
    for linha in linhas_texto:
        if not linha or linha.upper().startswith(("DEMONSTRATIVO", "TOTAL", "DEM ")):
            continue
        if re.match(r"^[A-ZÇÃÊÁÍÓÚ]{4,}\s*/\s*\d{4}$", linha):   # competência solta (2022)
            continue
        recibo.titular = re.split(r"\s+(?:TOTAL|PAGAMENTO)\s", linha)[0].strip()
        break
    return recibo


def ler_recibo(pdf_file) -> Recibo:
    """Lê o `_REC.pdf` da ABRAMUS. Não levanta exceção por divergência de
    centavos: o que não fecha vira aviso em `Recibo.avisos`."""
    linhas_texto = _extrair_texto(pdf_file)
    texto = "\n".join(linhas_texto)
    recibo = _ler_cabecalho(texto, linhas_texto)

    registros: list[dict] = []
    pendentes: list[int] = []   # índices ainda sem categoria (ela só aparece no total)
    totais_categoria: list[tuple[str, float, float]] = []

    for linha in linhas_texto:
        if not linha:
            continue

        m = _RE_TOTAL_CATEGORIA.match(linha)
        if m:
            categoria = m.group(1).strip()
            for i in pendentes:
                registros[i]["Categoria"] = categoria
            pendentes = []
            totais_categoria.append((categoria, valor_br(m.group(2)), valor_br(m.group(3))))
            continue

        m = _RE_LINHA.match(linha)
        if not m:
            continue

        descricao, referencia = m.group(1).strip(), m.group(2)
        debito, credito = valor_br(m.group(3)), valor_br(m.group(4))
        tipo, modalidade, titular, rubrica = _classificar(descricao)
        if tipo == TIPO_PROPRIO and not recibo.demonstrativo:
            mp = _RE_PROPRIO.match(descricao)
            if mp:
                recibo.demonstrativo = mp.group(1)
        registros.append({
            "Categoria": "", "Tipo": tipo, "Modalidade": modalidade, "Titular": titular,
            "Rubrica": rubrica, "Referência": referencia,
            "Débito": debito, "Crédito": credito, "Valor": round(credito - debito, 2),
        })
        pendentes.append(len(registros) - 1)

    recibo.linhas = pd.DataFrame(registros, columns=COLUNAS)
    recibo.resumo = _ler_resumo(texto)
    if not recibo.total:
        recibo.total = recibo.resumo.get("total", 0.0)

    if recibo.linhas.empty:
        recibo.avisos.append("Nenhuma linha de detalhe reconhecida — o PDF é mesmo o recibo (_REC.pdf) da ABRAMUS?")
        return recibo

    if pendentes:
        recibo.avisos.append(
            f"{len(pendentes)} linha(s) ficaram fora de qualquer categoria (sem 'Total da categoria' depois delas)."
        )

    # Confere cada categoria contra o total que o próprio documento declara.
    # A tolerância de 10 centavos é a folga das frações abaixo de um centavo que
    # o recibo soma no resumo mas não mostra no detalhe.
    for categoria, debito, credito in totais_categoria:
        bloco = recibo.linhas[recibo.linhas["Categoria"] == categoria]
        dif = round(float(bloco["Valor"].sum()) - (credito - debito), 2)
        if abs(dif) > 0.10:
            recibo.avisos.append(
                f"Categoria {categoria}: soma das linhas difere do total declarado em R$ {dif:,.2f}."
            )

    sem_titular = recibo.linhas[
        (recibo.linhas["Tipo"] == TIPO_RELACIONAMENTO) & (recibo.linhas["Titular"] == "")
    ]
    if not sem_titular.empty:
        recibo.avisos.append(
            f"{len(sem_titular)} linha(s) de venda de catálogo não trazem o titular — é o layout "
            "antigo do recibo (até 2023), que não detalhava por titular."
        )

    return recibo


def conferencia(recibo: Recibo) -> dict:
    """Fecha a conta do documento: soma do detalhe menos as deduções do resumo
    contra o TOTAL declarado. A diferença residual são as frações abaixo de um
    centavo que o próprio recibo avisa não exibir no detalhe."""
    soma = round(float(recibo.linhas["Valor"].sum()), 2)
    despesas = recibo.resumo.get("despesas_bancarias", 0.0)
    irrf = recibo.resumo.get("irrf", 0.0)
    return {
        "soma_detalhe": soma,
        "despesas_bancarias": despesas,
        "irrf": irrf,
        "total": recibo.total,
        "diferenca": round(soma - despesas - irrf - recibo.total, 2),
    }


def por_titular(recibo: Recibo) -> pd.DataFrame:
    """Uma linha por titular de relacionamento, somando as categorias — é a
    granularidade que a RR usa. Ordenado por valor decrescente."""
    rel = recibo.linhas[recibo.linhas["Tipo"] == TIPO_RELACIONAMENTO]
    if rel.empty:
        return pd.DataFrame(columns=["Titular", "Modalidades", "Categorias", "Valor"])
    agrupado = (
        rel.groupby("Titular", as_index=False)
        .agg(
            Modalidades=("Modalidade", lambda s: ", ".join(sorted({v for v in s if v}))),
            Categorias=("Categoria", lambda s: ", ".join(sorted({v for v in s if v}))),
            Valor=("Valor", "sum"),
        )
    )
    agrupado["Valor"] = agrupado["Valor"].round(2)
    return agrupado.sort_values("Valor", ascending=False, ignore_index=True)
