"""
Reconciliação de Payments — Reprtoir

Lê a planilha de conciliação financeiro × Reprtoir, compara contra o estado
ATUAL dos payments no Reprtoir (nunca um snapshot salvo — ver nota abaixo) e
aplica: marca como Paid + data de pagamento quem foi pago, e registra nota de
pendência em quem ficou pendente (ex.: pagamento que precisou ser refeito por
outro meio).

Por que comparar sempre contra o estado atual, e não um progresso salvo:
a página roda no Streamlit Cloud, cujo processo pode reiniciar e cuja sessão
de página é perdida a qualquer F5 do navegador — perder um "checkpoint" em
memória no meio de um lote seria fácil. Em vez de tentar não perder isso,
o desenho evita precisar dele: marcar como Paid algo que já está Paid é
inofensivo, então re-rodar esta página a qualquer momento (mesmo no meio de
um lote anterior) só reaplica o que ainda falta — o próprio Reprtoir já é o
"checkpoint".

Pelo mesmo motivo, as pendências (ex.: o caso de um pagamento que falhou e
será refeito por outro meio) não ficam num arquivo local do Lyra — friável a
qualquer redeploy do Streamlit Cloud — e sim como nota (`notes`) no próprio
payment no Reprtoir. Isso também as deixa visíveis para quem abre o Reprtoir
diretamente, sem precisar do Lyra.
"""

import os

import streamlit as st

from utils.page import setup_page
from utils.execution_log import registrar
from utils.reprtoir_payments import (
    ReprtoirLoginError,
    ReprtoirPaymentsClient,
    ReprtoirRequestError,
    carregar_planilha,
    cruzar,
    pendencias_em_aberto,
)

PAGINA = "reconciliacao_pagamentos"

setup_page(
    __file__,
    descricao=(
        "Compara a planilha de conciliação financeiro × Reprtoir contra o estado atual dos "
        "payments e aplica marcação de Paid, data de pagamento e notas de pendência."
    ),
)


def _credencial(nome: str) -> str:
    """Prioriza st.secrets (Streamlit Cloud); cai para variável de ambiente
    (.env local) se não estiver nos secrets — mesma convenção de
    utils/reprtoir_lookup.py, só que sem exigir um .env."""
    try:
        if nome in st.secrets:
            return st.secrets[nome]
    except Exception:
        pass
    return os.getenv(nome, "")


with st.expander("ℹ️ O que é esta página e como usar", expanded=False):
    st.markdown(
"""
**O que faz**

Lê a planilha de conciliação (financeiro × Reprtoir), cruza cada linha com o payment
correspondente no Reprtoir (por VAT + valor) e mostra o que precisa mudar **antes** de
aplicar qualquer coisa.

**O que ela aplica**

- Linhas **SIM** (pago) cujo payment no Reprtoir ainda está *Unpaid* → marca como **Paid** e
  seta a **data de pagamento**.
- Linhas **NÃO** (não pago) cujo payment ainda está *Unpaid* → grava uma **nota** explicando
  a pendência (editável antes de aplicar) — não muda o status.
- Linhas sem correspondência no Reprtoir, ou com status "Paid" mas a planilha dizendo
  **NÃO** (inconsistência), são só **mostradas**, nunca aplicadas automaticamente.

**Pendências entre competências**

A seção **Pendências em aberto** no fim da página não depende da planilha carregada — ela
pergunta ao Reprtoir "quem está Unpaid e tem nota registrada", sempre ao vivo. Assim, o caso
de um pagamento que falhou este mês e será refeito por outro meio continua visível mesmo
depois de fechar o Lyra, trocar de mês ou o app reiniciar — quando você reprocessar a
planilha do mês seguinte já com a linha como SIM, a nota é limpa automaticamente.

**Sobre a integração**

Não existe API pública do Reprtoir para payments — esta página usa os mesmos endpoints
internos que o próprio Reprtoir usa (login por sessão), não Playwright/navegador. Detalhes
em `utils/reprtoir_payments.py`.
""")

if "reconc_reprtoir_payments" not in st.session_state:
    st.session_state.reconc_reprtoir_payments = None
if "reconc_resultado" not in st.session_state:
    st.session_state.reconc_resultado = None

# ---------------------------------------------------------------------------
# 1. Upload da planilha
# ---------------------------------------------------------------------------

st.subheader("1. Planilha de conciliação")
arquivo = st.file_uploader(
    "Planilha do financeiro (xlsx) — mesma estrutura de sempre: Rights-Holder, VAT, Royalties, "
    "Financeiro, Check, Pago?",
    type=["xlsx"],
)

if not arquivo:
    st.stop()

try:
    linhas = carregar_planilha(arquivo)
except ValueError as e:
    st.error(str(e))
    st.stop()

pagos = [l for l in linhas if l.pago]
nao_pagos = [l for l in linhas if not l.pago]

c1, c2, c3 = st.columns(3)
c1.metric("Total de linhas", len(linhas))
c2.metric("Pagos (SIM)", len(pagos))
c3.metric("Não pagos (NÃO)", len(nao_pagos))

if nao_pagos:
    with st.expander(f"Linhas marcadas como NÃO pago ({len(nao_pagos)})", expanded=True):
        st.dataframe(
            [{"Rights-Holder": l.rightsholder, "VAT": l.vat, "Valor": l.amount, "Motivo": l.motivo or "—"}
             for l in nao_pagos],
            use_container_width=True,
            hide_index=True,
        )

st.divider()

# ---------------------------------------------------------------------------
# 2. Conectar e comparar contra o estado atual do Reprtoir
# ---------------------------------------------------------------------------

st.subheader("2. Comparar com o Reprtoir")
st.caption(
    "Sempre busca o estado atual — se você já rodou isso antes hoje (ou a sessão caiu no meio), "
    "rodar de novo é seguro: só aparece o que ainda falta."
)

if st.button("🔄 Conectar e comparar", type="primary"):
    email = _credencial("REPRTOIR_EMAIL")
    password = _credencial("REPRTOIR_PASSWORD")

    if not email or not password:
        st.error(
            "REPRTOIR_EMAIL / REPRTOIR_PASSWORD não configurados. Adicione em "
            "`.streamlit/secrets.toml` (local) ou nas Secrets do app no Streamlit Cloud."
        )
        st.stop()

    client = ReprtoirPaymentsClient(email, password)
    progress = st.progress(0.0, text="Conectando...")
    try:
        def _cb(pagina, total):
            progress.progress(pagina / total, text=f"Extraindo página {pagina}/{total}...")

        payments = client.fetch_all_payments(progress_cb=_cb)
    except ReprtoirLoginError as e:
        progress.empty()
        st.error(f"Login falhou: {e}")
        st.stop()
    except ReprtoirRequestError as e:
        progress.empty()
        st.error(f"Erro ao consultar o Reprtoir: {e}")
        st.stop()

    progress.empty()
    st.session_state.reconc_reprtoir_payments = payments
    st.session_state.reconc_resultado = cruzar(linhas, payments)
    st.success(f"{len(payments)} payments extraídos do Reprtoir.")

resultado = st.session_state.reconc_resultado
if resultado is None:
    st.stop()

st.divider()

# ---------------------------------------------------------------------------
# 3. Revisão
# ---------------------------------------------------------------------------

st.subheader("3. Revisão")

c1, c2, c3, c4, c5 = st.columns(5)
c1.metric("A marcar como Paid", len(resultado.a_pagar))
c2.metric("Pendências a registrar", len(resultado.pendentes))
c3.metric("Já OK (nada a fazer)", len(resultado.ja_ok))
c4.metric("Ambíguos", len(resultado.ambiguos))
c5.metric("Sem correspondência", len(resultado.sem_correspondencia))

data_padrao = None
if resultado.a_pagar:
    with st.expander(f"✅ Serão marcados como Paid ({len(resultado.a_pagar)})", expanded=True):
        st.dataframe(
            [{"Rights-Holder": m.linha.rightsholder, "VAT": m.linha.vat, "Valor": m.linha.amount,
              "Data de pagamento": m.linha.data_pagamento or "— (obrigatório informar abaixo)"}
             for m in resultado.a_pagar],
            use_container_width=True,
            hide_index=True,
        )
        sem_data = [m for m in resultado.a_pagar if not m.linha.data_pagamento]
        if sem_data:
            st.warning(
                f"{len(sem_data)} linha(s) sem data de pagamento na planilha — informe uma data "
                "padrão para aplicar a todas elas:"
            )
            data_padrao = st.date_input("Data de pagamento (para as linhas sem data na planilha)")

notas_editadas: dict[str, str] = {}
if resultado.pendentes:
    with st.expander(f"⏳ Pendências a registrar ({len(resultado.pendentes)})", expanded=True):
        st.caption("Edite o texto da nota se quiser — ela fica gravada no payment no Reprtoir.")
        for m in resultado.pendentes:
            padrao = m.linha.motivo or "Pendente — planilha marcou como NÃO pago neste ciclo."
            notas_editadas[m.payment["uuid"]] = st.text_input(
                f"{m.linha.rightsholder} — R$ {m.linha.amount:,.2f}",
                value=padrao,
                key=f"nota_{m.payment['uuid']}",
            )

if resultado.ambiguos:
    with st.expander(f"🔀 Ambíguos ({len(resultado.ambiguos)}) — não aplicado automaticamente", expanded=True):
        st.warning(
            "Mais de um payment do Reprtoir bate com o mesmo VAT + valor desta linha. "
            "Resolva manualmente no Reprtoir (ou ajuste a planilha) para evitar marcar o "
            "payment errado."
        )
        for amb in resultado.ambiguos:
            st.markdown(f"**{amb.linha.rightsholder}** — VAT {amb.linha.vat} — R$ {amb.linha.amount:,.2f}")
            st.dataframe(
                [{"Payment (nome)": p["name"], "Status": p["status"]["text"], "Criado em": p["created_at"],
                  "uuid": p["uuid"]}
                 for p in amb.candidatos],
                use_container_width=True,
                hide_index=True,
            )

if resultado.conflitos:
    with st.expander(f"⚠️ Inconsistências ({len(resultado.conflitos)}) — não aplicado automaticamente", expanded=True):
        st.warning("Planilha diz NÃO pago, mas o Reprtoir já mostra Paid. Confira manualmente.")
        st.dataframe(
            [{"Rights-Holder": m.linha.rightsholder, "VAT": m.linha.vat, "Valor": m.linha.amount,
              "Status no Reprtoir": m.payment["status"]["text"]}
             for m in resultado.conflitos],
            use_container_width=True,
            hide_index=True,
        )

if resultado.sem_correspondencia:
    with st.expander(f"❓ Sem correspondência no Reprtoir ({len(resultado.sem_correspondencia)})", expanded=True):
        st.dataframe(
            [{"Rights-Holder": l.rightsholder, "VAT": l.vat, "Valor": l.amount}
             for l in resultado.sem_correspondencia],
            use_container_width=True,
            hide_index=True,
        )

if not resultado.a_pagar and not resultado.pendentes:
    st.info("Nada a aplicar — planilha e Reprtoir já estão alinhados.")
    st.stop()

st.divider()

# ---------------------------------------------------------------------------
# 4. Aplicar
# ---------------------------------------------------------------------------

st.subheader("4. Aplicar no Reprtoir")
st.caption("Ação real, em produção. Confira a revisão acima antes de confirmar.")

confirmar = st.checkbox("Revisei a lista acima e quero aplicar estas mudanças.")
if st.button("Aplicar", disabled=not confirmar, type="primary"):
    email = _credencial("REPRTOIR_EMAIL")
    password = _credencial("REPRTOIR_PASSWORD")
    client = ReprtoirPaymentsClient(email, password)

    resumo = {"marcados_paid": 0, "pendencias_registradas": 0, "erros": []}

    try:
        # --- marcar como Paid, agrupando por data (mesma data -> 1 chamada) ---
        por_data: dict[str, list] = {}
        for m in resultado.a_pagar:
            data = m.linha.data_pagamento or (str(data_padrao) if data_padrao else None)
            por_data.setdefault(data, []).append(m)

        for data, matches in por_data.items():
            if not data:
                resumo["erros"].append(
                    f"{len(matches)} payment(s) sem data de pagamento — pulados."
                )
                continue
            uuids = [m.payment["uuid"] for m in matches]
            nomes = {m.payment["uuid"]: m.payment["name"] for m in matches}
            client.update_payments(uuids, name_by_uuid=nomes, status="paid", payment_date=data)
            resumo["marcados_paid"] += len(uuids)

        # --- registrar pendências (uma chamada por nota distinta) ---
        if resultado.pendentes:
            por_nota: dict[str, list] = {}
            for m in resultado.pendentes:
                nota = notas_editadas.get(m.payment["uuid"], "")
                por_nota.setdefault(nota, []).append(m)
            for nota, matches in por_nota.items():
                uuids = [m.payment["uuid"] for m in matches]
                nomes = {m.payment["uuid"]: m.payment["name"] for m in matches}
                client.update_payments(
                    uuids, name_by_uuid=nomes,
                    status=matches[0].payment["status"]["value"],
                    notes=nota,
                )
                resumo["pendencias_registradas"] += len(uuids)

    except (ReprtoirLoginError, ReprtoirRequestError) as e:
        st.error(f"Parou no meio da aplicação: {e}")
        st.info(
            "Pode rodar a página de novo com segurança — quem já foi marcado não será "
            "reprocessado, só o que ainda falta."
        )
    else:
        st.success(
            f"Concluído: {resumo['marcados_paid']} marcado(s) como Paid, "
            f"{resumo['pendencias_registradas']} pendência(s) registrada(s)."
        )
        if resumo["erros"]:
            for erro in resumo["erros"]:
                st.warning(erro)

        registrar(PAGINA, periodo=arquivo.name, resumo=resumo)
        st.session_state.reconc_reprtoir_payments = None
        st.session_state.reconc_resultado = None

st.divider()

# ---------------------------------------------------------------------------
# 5. Pendências em aberto (estado vivo do Reprtoir, não depende da planilha)
# ---------------------------------------------------------------------------

st.subheader("5. Pendências em aberto (todas, não só desta planilha)")
payments_atuais = st.session_state.reconc_reprtoir_payments
if payments_atuais:
    abertas = pendencias_em_aberto(payments_atuais)
    if abertas:
        st.dataframe(
            [{"Rights-Holder": p["rightholder"]["name"], "VAT": p["rightholder"]["vat_number"],
              "Valor": float(p["amount"]), "Nota": p.get("notes", "")}
             for p in abertas],
            use_container_width=True,
            hide_index=True,
        )
    else:
        st.success("Nenhuma pendência em aberto no Reprtoir. 🎉")
else:
    st.caption("Conecte e compare (passo 2) para ver as pendências em aberto.")
