"""
Reconciliação de Payments — Reprtoir

Lê a planilha de conciliação financeiro × Reprtoir, compara contra o estado
ATUAL dos payments no Reprtoir (nunca um snapshot salvo — ver nota abaixo) e
aplica: marca como Paid + data de pagamento quem foi pago, e registra nota de
pendência em quem ficou pendente (ex.: pagamento que precisou ser refeito por
outro meio).

Por que via relay, e não falando com o Reprtoir direto: o Streamlit Community
Cloud roda em IPs de datacenter compartilhados que o WAF na frente do
Reprtoir bloqueia (HTTP 403) — mesmo pra chamadas GET simples via `requests`,
sem navegador. Do IP residencial/escritório funciona normalmente. Por isso
esta página fala com um relay rodando na sua máquina (ver `relay/`), que por
sua vez fala com o Reprtoir — ver `utils/reprtoir_relay_client.py`.

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
from utils.reprtoir_payments import carregar_planilha
from utils.reprtoir_relay_client import RelayClient, RelayError

PAGINA = "reconciliacao_pagamentos"

setup_page(
    __file__,
    descricao=(
        "Compara a planilha de conciliação financeiro × Reprtoir contra o estado atual dos "
        "payments e aplica marcação de Paid, data de pagamento e notas de pendência."
    ),
)


def _config(nome: str) -> str:
    """Prioriza st.secrets (Streamlit Cloud); cai para variável de ambiente
    (.env local) se não estiver nos secrets."""
    try:
        if nome in st.secrets:
            return st.secrets[nome]
    except Exception:
        pass
    return os.getenv(nome, "")


def _relay() -> RelayClient:
    return RelayClient(_config("RELAY_URL"), _config("RELAY_TOKEN"))


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
- Linhas sem correspondência, com mais de um payment candidato (ambíguo), ou com status
  "Paid" mas a planilha dizendo **NÃO** (inconsistência), são só **mostradas**, nunca
  aplicadas automaticamente.

**Pendências entre competências**

A seção **Pendências em aberto** no fim da página não depende da planilha carregada — ela
pergunta ao Reprtoir "quem está Unpaid e tem nota registrada", sempre ao vivo. Assim, o caso
de um pagamento que falhou este mês e será refeito por outro meio continua visível mesmo
depois de fechar o Lyra, trocar de mês ou o app reiniciar — quando você reprocessar a
planilha do mês seguinte já com a linha como SIM, a nota é limpa automaticamente.

**Sobre a integração**

Esta página não fala com o Reprtoir diretamente — o Streamlit Cloud é bloqueado pelo WAF do
Reprtoir. Ela fala com um **relay rodando na sua máquina** (veja `relay/README.md` no repo
para configurar). Sem o relay ligado, o botão "Conectar e comparar" abaixo vai dar erro de
conexão.

**Como rodar na próxima vez:**

1. Abra um terminal dentro da pasta `relay/` do projeto e rode:
   ```
   python -m uvicorn server:app --port 8000
   ```

2. Abra outro terminal (mantenha o primeiro aberto) e rode ngrok:
   ```
   ngrok http 8000
   ```

3. Copie a URL que ngrok gera (tipo `https://abc123.ngrok-free.dev`) e atualize nas **Secrets do
   app no Streamlit Cloud** (⋮ → Settings → Secrets — é lá que o app publicado lê, não no
   `.streamlit/secrets.toml` local):
   ```
   RELAY_URL = "https://abc123.ngrok-free.dev"
   ```

4. Volte aqui e clique "🔄 Verificar" — deve aparecer "🟢 Relay online".
""")

if "reconc_resultado" not in st.session_state:
    st.session_state.reconc_resultado = None
if "reconc_relay_online" not in st.session_state:
    st.session_state.reconc_relay_online = None  # None = ainda não checado


def _checar_relay() -> None:
    try:
        st.session_state.reconc_relay_online = _relay().health()
    except ValueError:
        st.session_state.reconc_relay_online = None  # secrets não configurados


if st.session_state.reconc_relay_online is None:
    _checar_relay()

status_text = "🟢 Relay online" if st.session_state.reconc_relay_online else "🔴 Relay offline"
bg_color = "#d1e7dd" if st.session_state.reconc_relay_online else "#f8d7da"
border_color = "#b6d4cc" if st.session_state.reconc_relay_online else "#f1b0b7"
text_color = "#0d3622" if st.session_state.reconc_relay_online else "#842029"

# CSS mira na classe estável que st.container(key=...) gera (st-key-<key>) para
# pintar o próprio container do Streamlit — texto e botão ficam de verdade
# dentro dele, sem gambiarra de posicionamento.
st.markdown(f"""
    <style>
        .st-key-relay_status_box {{
            background-color: {bg_color};
            border: 1px solid {border_color};
            border-radius: 0.375rem;
            padding: 0.5rem 1rem;
        }}
        .st-key-relay_status_box [data-testid="stMarkdownContainer"] p {{
            color: {text_color};
            font-weight: 500;
            margin: 0;
        }}
        /* Streamlit aplica margin-bottom negativo no container do markdown
           (para colar elementos), o que faz o texto "vazar" para baixo da
           caixa usada pelo flexbox da coluna para centralizar — zera aqui
           para o texto ficar alinhado de verdade com o botão ao lado. */
        .st-key-relay_status_box [data-testid="stMarkdownContainer"] {{
            margin-bottom: 0 !important;
        }}
        .st-key-relay_status_box div[data-testid="stVerticalBlockBorderWrapper"] {{
            background-color: transparent;
        }}
    </style>
""", unsafe_allow_html=True)

with st.container(key="relay_status_box"):
    col_msg, col_btn = st.columns([5, 1], vertical_alignment="center")
    with col_msg:
        st.markdown(status_text)
    with col_btn:
        if st.button("🔄 Verificar", use_container_width=True):
            _checar_relay()
            st.rerun()

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
# 2. Conectar (via relay) e comparar contra o estado atual do Reprtoir
# ---------------------------------------------------------------------------

st.subheader("2. Comparar com o Reprtoir")
st.caption(
    "Sempre busca o estado atual — se você já rodou isso antes hoje (ou a sessão caiu no meio), "
    "rodar de novo é seguro: só aparece o que ainda falta. Requer o relay local rodando "
    "(veja `relay/README.md`)."
)

if st.button("🔄 Conectar e comparar", type="primary"):
    try:
        relay = _relay()
    except ValueError:
        st.error(
            "RELAY_URL / RELAY_TOKEN não configurados. Adicione nas Secrets do app "
            "(Streamlit Cloud) ou em `.streamlit/secrets.toml` (local)."
        )
        st.stop()

    with st.spinner("Comparando com o Reprtoir (via relay)..."):
        try:
            resultado = relay.comparar(linhas)
        except RelayError as e:
            st.error(str(e))
            st.stop()

    st.session_state.reconc_resultado = resultado
    st.success(f"{resultado['total_payments_reprtoir']} payments extraídos do Reprtoir.")

resultado = st.session_state.reconc_resultado
if resultado is None:
    st.stop()

st.divider()

# ---------------------------------------------------------------------------
# 3. Revisão
# ---------------------------------------------------------------------------

st.subheader("3. Revisão")

a_pagar = resultado["a_pagar"]
pendentes = resultado["pendentes"]
ja_ok = resultado["ja_ok"]
conflitos = resultado["conflitos"]
ambiguos = resultado["ambiguos"]
sem_correspondencia = resultado["sem_correspondencia"]

c1, c2, c3, c4, c5 = st.columns(5)
c1.metric("A marcar como Paid", len(a_pagar))
c2.metric("Pendências a registrar", len(pendentes))
c3.metric("Já OK (nada a fazer)", len(ja_ok))
c4.metric("Ambíguos", len(ambiguos))
c5.metric("Sem correspondência", len(sem_correspondencia))

data_padrao = None
if a_pagar:
    with st.expander(f"✅ Serão marcados como Paid ({len(a_pagar)})", expanded=True):
        st.dataframe(
            [{"Rights-Holder": m["linha"]["rightsholder"], "VAT": m["linha"]["vat"],
              "Valor": m["linha"]["amount"],
              "Data de pagamento": m["linha"]["data_pagamento"] or "— (obrigatório informar abaixo)"}
             for m in a_pagar],
            use_container_width=True,
            hide_index=True,
        )
        sem_data = [m for m in a_pagar if not m["linha"]["data_pagamento"]]
        if sem_data:
            st.warning(
                f"{len(sem_data)} linha(s) sem data de pagamento na planilha — informe uma data "
                "padrão para aplicar a todas elas:"
            )
            data_padrao = st.date_input("Data de pagamento (para as linhas sem data na planilha)")

if ja_ok:
    with st.expander(f"✔️ Já OK, nada a fazer ({len(ja_ok)})", expanded=False):
        st.dataframe(
            [{"Rights-Holder": m["linha"]["rightsholder"], "VAT": m["linha"]["vat"],
              "Valor": m["linha"]["amount"], "Status no Reprtoir": m["payment"]["status"]["text"],
              "Payment date": m["payment"]["payment_date"] or "—"}
             for m in ja_ok],
            use_container_width=True,
            hide_index=True,
        )

notas_editadas: dict[str, str] = {}
if pendentes:
    with st.expander(f"⏳ Pendências a registrar ({len(pendentes)})", expanded=True):
        st.caption("Edite o texto da nota se quiser — ela fica gravada no payment no Reprtoir.")
        for m in pendentes:
            padrao = m["linha"]["motivo"] or "Pendente — planilha marcou como NÃO pago neste ciclo."
            notas_editadas[m["payment"]["uuid"]] = st.text_input(
                f"{m['linha']['rightsholder']} — R$ {m['linha']['amount']:,.2f}",
                value=padrao,
                key=f"nota_{m['payment']['uuid']}",
            )

if ambiguos:
    with st.expander(f"🔀 Ambíguos ({len(ambiguos)}) — não aplicado automaticamente", expanded=True):
        st.warning(
            "Mais de um payment do Reprtoir bate com o mesmo VAT + valor desta linha. "
            "Resolva manualmente no Reprtoir (ou ajuste a planilha) para evitar marcar o "
            "payment errado."
        )
        for amb in ambiguos:
            st.markdown(
                f"**{amb['linha']['rightsholder']}** — VAT {amb['linha']['vat']} — "
                f"R$ {amb['linha']['amount']:,.2f}"
            )
            st.dataframe(
                [{"Payment (nome)": p["name"], "Status": p["status"]["text"], "Criado em": p["created_at"],
                  "uuid": p["uuid"]}
                 for p in amb["candidatos"]],
                use_container_width=True,
                hide_index=True,
            )

if conflitos:
    with st.expander(f"⚠️ Inconsistências ({len(conflitos)}) — não aplicado automaticamente", expanded=True):
        st.warning("Planilha diz NÃO pago, mas o Reprtoir já mostra Paid. Confira manualmente.")
        st.dataframe(
            [{"Rights-Holder": m["linha"]["rightsholder"], "VAT": m["linha"]["vat"],
              "Valor": m["linha"]["amount"], "Status no Reprtoir": m["payment"]["status"]["text"]}
             for m in conflitos],
            use_container_width=True,
            hide_index=True,
        )

if sem_correspondencia:
    with st.expander(f"❓ Sem correspondência no Reprtoir ({len(sem_correspondencia)})", expanded=True):
        st.dataframe(
            [{"Rights-Holder": l["rightsholder"], "VAT": l["vat"], "Valor": l["amount"]}
             for l in sem_correspondencia],
            use_container_width=True,
            hide_index=True,
        )

if not a_pagar and not pendentes:
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
    marcar_pagos = []
    ignorados_sem_data = 0
    for m in a_pagar:
        data = m["linha"]["data_pagamento"] or (str(data_padrao) if data_padrao else None)
        if not data:
            ignorados_sem_data += 1
            continue
        marcar_pagos.append({"uuid": m["payment"]["uuid"], "name": m["payment"]["name"], "payment_date": data})

    pendencias_payload = [
        {
            "uuid": m["payment"]["uuid"],
            "name": m["payment"]["name"],
            "status": m["payment"]["status"]["value"],
            "notes": notas_editadas.get(m["payment"]["uuid"], ""),
        }
        for m in pendentes
    ]

    try:
        relay = _relay()
        with st.spinner("Aplicando no Reprtoir (via relay)..."):
            resumo = relay.aplicar(marcar_pagos, pendencias_payload)
    except RelayError as e:
        st.error(str(e))
        st.info(
            "Pode rodar a página de novo com segurança — quem já foi marcado não será "
            "reprocessado, só o que ainda falta."
        )
    else:
        st.success(
            f"Concluído: {resumo['marcados_paid']} marcado(s) como Paid, "
            f"{resumo['pendencias_registradas']} pendência(s) registrada(s)."
        )
        if ignorados_sem_data:
            st.warning(f"{ignorados_sem_data} linha(s) sem data de pagamento — pulada(s).")

        registrar(PAGINA, periodo=arquivo.name, resumo=resumo)
        st.session_state.reconc_resultado = None

st.divider()

# ---------------------------------------------------------------------------
# 5. Pendências em aberto (estado vivo do Reprtoir, não depende da planilha)
# ---------------------------------------------------------------------------

st.subheader("5. Pendências em aberto (todas, não só desta planilha)")
if st.button("Consultar pendências em aberto"):
    try:
        relay = _relay()
        with st.spinner("Consultando..."):
            abertas = relay.pendencias_em_aberto()
    except (ValueError, RelayError) as e:
        st.error(str(e))
    else:
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
