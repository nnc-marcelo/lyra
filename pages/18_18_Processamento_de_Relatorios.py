import streamlit as st
import pandas as pd
import openpyxl
import io
from io import BytesIO
import warnings

warnings.filterwarnings("ignore", category=UserWarning, module="openpyxl")
pd.set_option('display.max_colwidth', None)

st.title("Processamento de Relatórios")
st.caption("Transforma relatórios e prepara-os para o Reprtoir.")

template = st.selectbox("STATEMENT TEMPLATE:", ["Nikita Digital", "Backoffice"])

# ============================================================================
# TEMPLATE: NIKITA DIGITAL
# ============================================================================

# Para o template Nikita, geramos um arquivo por aba (por posição, base 1).
# "last" = última aba.
NIKITA_OUTPUTS = [
    ("DSP", 2),                 # segunda aba
    ("YouTube", 3),             # terceira aba
    ("YouTube Music", "last"),  # última aba
]


def build_single_sheet(raw_bytes, keep_idx):
    """Retorna um xlsx em memória contendo apenas a aba do índice informado."""
    wb = openpyxl.load_workbook(io.BytesIO(raw_bytes))
    keep_name = wb.sheetnames[keep_idx]
    for name in list(wb.sheetnames):
        if name != keep_name:
            del wb[name]
    out = io.BytesIO()
    wb.save(out)
    out.seek(0)
    return out, keep_name


def render_nikita():
    uploaded = st.file_uploader("Upload do relatório (.xlsx)", type=["xlsx"])
    if not uploaded:
        return

    raw = uploaded.read()
    sheets = openpyxl.load_workbook(io.BytesIO(raw), read_only=True).sheetnames
    base_name = uploaded.name.rsplit(".", 1)[0]

    st.success(f"Arquivo carregado com {len(sheets)} aba(s). Baixe cada relatório abaixo:")

    for label, rule in NIKITA_OUTPUTS:
        keep_idx = len(sheets) - 1 if rule == "last" else rule - 1

        if keep_idx < 0 or keep_idx >= len(sheets):
            st.warning(f"{label}: aba esperada não encontrada (arquivo tem {len(sheets)} abas).")
            continue

        data, keep_name = build_single_sheet(raw, keep_idx)
        st.download_button(
            label=f"Baixar {label}  (aba: {keep_name})",
            data=data,
            file_name=f"{base_name}_{label}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            key=f"nikita_{label}",
        )


# ============================================================================
# TEMPLATE: BACKOFFICE
# ============================================================================

def detectar_formato_arquivo(file):
    """
    Detecta automaticamente o formato do arquivo Backoffice.

    Retorna:
        - 0: arquivo começa direto com o cabeçalho (header=0)
        - 5: arquivo tem metadados nas primeiras linhas (header=5)
        - None: arquivo inválido ou muito pequeno
    """
    try:
        df_test = pd.read_excel(file, nrows=7)

        if len(df_test) < 1:
            return None

        if "BO_PayeesID" in df_test.columns or "PAYEESID" in str(df_test.columns[0]).upper():
            return 0

        if len(df_test) >= 6:
            file.seek(0)
            df_test_h5 = pd.read_excel(file, header=5, nrows=1)
            if "BO_PayeesID" in df_test_h5.columns or any("PAYEE" in str(col).upper() for col in df_test_h5.columns):
                return 5

        return None

    except Exception:
        return None
    finally:
        file.seek(0)


def ler_arquivo_backoffice(file):
    """Lê arquivo Backoffice detectando automaticamente o formato."""
    header_pos = detectar_formato_arquivo(file)

    if header_pos is None:
        return None, "❌ Arquivo muito pequeno ou formato inválido", False

    try:
        df = pd.read_excel(file, header=header_pos)
        if len(df) == 0:
            return None, "⚠️ Arquivo sem dados", False
        info = f"✅ Lido com sucesso (header={header_pos}, {len(df)} linhas)"
        return df, info, True
    except Exception as e:
        return None, f"❌ Erro ao ler: {str(e)}", False


def render_backoffice():
    st.caption("Concatena e totaliza os arquivos Backoffice para conferência e inclusão no Repertoir.")

    uploaded_files = st.file_uploader(
        "Faça o upload dos arquivos Excel",
        type=["xlsx", "xls"],
        accept_multiple_files=True,
        key="concat_files",
    )

    if not uploaded_files:
        st.info("📤 Aguardando upload dos arquivos...")
        st.markdown("""
        ### 📝 Instruções:

        **Para Concatenar:**
        - Faça upload de múltiplos arquivos Excel do Backoffice
        - Clique em "🔗 Concatenar arquivos"
        - Baixe o arquivo único com todos os dados

        **Para Totalizar:**
        - Faça upload de arquivos **ST** (Statements)
        - Clique em "🧮 Calcular totais"
        - Visualize o resumo financeiro e baixe os totais
        """)
        return

    st.info(f"📁 {len(uploaded_files)} arquivo(s) carregado(s)")

    col1, col2 = st.columns(2)
    with col1:
        concat_button = st.button('🔗 Concatenar arquivos', type='secondary', use_container_width=True)
    with col2:
        totals_button = st.button('🧮 Calcular totais', type='primary', use_container_width=True)

    # ---- CONCATENAR ----
    if concat_button:
        st.divider()
        st.subheader("📊 Processando concatenação...")

        dataframes, logs = [], []
        arquivos_sucesso = arquivos_erro = 0

        progress_bar = st.progress(0)
        status_text = st.empty()

        for i, file in enumerate(uploaded_files):
            progress_bar.progress((i + 1) / len(uploaded_files))
            status_text.text(f"Processando {i+1}/{len(uploaded_files)}: {file.name}")

            df, info, sucesso = ler_arquivo_backoffice(file)
            if sucesso:
                dataframes.append(df)
                arquivos_sucesso += 1
            else:
                arquivos_erro += 1
            logs.append(f"**{file.name}** - {info}")

        progress_bar.empty()
        status_text.empty()

        with st.expander(f"📋 Detalhes do processamento ({arquivos_sucesso} sucesso, {arquivos_erro} erro)", expanded=False):
            for log in logs:
                st.markdown(log)

        if dataframes:
            try:
                concatenated_df = pd.concat(dataframes, ignore_index=True)
                st.success(f"""
                ✅ **Concatenação concluída com sucesso!**
                - Arquivos processados: {arquivos_sucesso}/{len(uploaded_files)}
                - Total de linhas: {len(concatenated_df):,}
                - Total de colunas: {len(concatenated_df.columns)}
                """)

                with st.expander("👁️ Visualizar dados concatenados", expanded=False):
                    st.dataframe(concatenated_df.head(100), use_container_width=True)

                buffer = BytesIO()
                with pd.ExcelWriter(buffer, engine='xlsxwriter') as writer:
                    concatenated_df.to_excel(writer, index=False, sheet_name='Dados Concatenados')

                st.download_button(
                    label="📥 Baixar arquivo concatenado",
                    data=buffer.getvalue(),
                    file_name="backoffice_concatenado.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    use_container_width=True
                )
            except Exception as e:
                st.error(f"❌ Erro ao concatenar os arquivos: {str(e)}")
        else:
            st.error("❌ Nenhum arquivo pôde ser processado com sucesso!")

    # ---- CALCULAR TOTAIS ----
    if totals_button:
        st.divider()
        st.subheader("💰 Calculando totais...")

        results = []
        arquivos_processados = 0
        arquivos_ignorados = []

        progress_bar = st.progress(0)
        status_text = st.empty()

        for i, file in enumerate(uploaded_files):
            progress_bar.progress((i + 1) / len(uploaded_files))
            status_text.text(f"Processando {i+1}/{len(uploaded_files)}: {file.name}")

            if "ST" in file.name.upper():
                try:
                    df, info, sucesso = ler_arquivo_backoffice(file)
                    if not sucesso:
                        arquivos_ignorados.append((file.name, info))
                        continue

                    coluna_royalties = None
                    if "ROYALTIES_TO_BE_PAID" in df.columns:
                        coluna_royalties = "ROYALTIES_TO_BE_PAID"
                    elif "ROYALTIES_TO_BE_PAID_$" in df.columns:
                        coluna_royalties = "ROYALTIES_TO_BE_PAID_$"
                    else:
                        for col in df.columns:
                            if "ROYALTIES" in str(col).upper() and "PAID" in str(col).upper():
                                coluna_royalties = col
                                break

                    if coluna_royalties:
                        total_royalties = df[coluna_royalties].sum()
                        results.append((file.name, total_royalties))
                        arquivos_processados += 1
                    else:
                        arquivos_ignorados.append((file.name, "❌ Coluna de royalties não encontrada"))

                except Exception as e:
                    arquivos_ignorados.append((file.name, f"❌ Erro: {str(e)}"))
            else:
                arquivos_ignorados.append((file.name, "⚠️ Não é arquivo ST (Statement)"))

        progress_bar.empty()
        status_text.empty()

        if arquivos_ignorados:
            with st.expander(f"⚠️ Arquivos ignorados ({len(arquivos_ignorados)})", expanded=False):
                for nome, motivo in arquivos_ignorados:
                    st.markdown(f"**{nome}** - {motivo}")

        if results:
            df_results = pd.DataFrame(results, columns=["Arquivo", "Soma de ROYALTIES_TO_BE_PAID"])
            df_results["Soma de ROYALTIES_TO_BE_PAID"] = df_results["Soma de ROYALTIES_TO_BE_PAID"].round(2)
            total_royalties_sum = df_results["Soma de ROYALTIES_TO_BE_PAID"].sum().round(2)
            df_results.loc[len(df_results.index)] = ["TOTAL GERAL", total_royalties_sum]
            df_results["Soma de ROYALTIES_TO_BE_PAID"] = df_results["Soma de ROYALTIES_TO_BE_PAID"].apply(
                lambda x: f"R$ {x:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
            )

            st.success(f"✅ {arquivos_processados} arquivo(s) totalizado(s) com sucesso!")
            st.dataframe(df_results, use_container_width=True, hide_index=True)

            st.divider()
            col1, col2, col3 = st.columns(3)
            with col1:
                st.metric(
                    label="💰 Total Bruto",
                    value=f"R$ {total_royalties_sum:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
                )
            desconto_r3 = (total_royalties_sum * 0.025).round(2)
            with col2:
                st.metric(
                    label="📉 Desconto R3 (2,5%)",
                    value=f"R$ {desconto_r3:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
                )
            total_liquido = (total_royalties_sum - desconto_r3).round(2)
            with col3:
                st.metric(
                    label="✅ Total Líquido",
                    value=f"R$ {total_liquido:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
                )

            buffer = BytesIO()
            with pd.ExcelWriter(buffer, engine='xlsxwriter') as writer:
                df_export = pd.DataFrame(results, columns=["Arquivo", "Total_Royalties"])
                df_export.loc[len(df_export.index)] = ["TOTAL GERAL", total_royalties_sum]
                df_export.loc[len(df_export.index)] = ["Desconto R3 (2,5%)", desconto_r3]
                df_export.loc[len(df_export.index)] = ["TOTAL LÍQUIDO", total_liquido]
                df_export.to_excel(writer, index=False, sheet_name='Totais')

            st.download_button(
                label="📥 Baixar totais em Excel",
                data=buffer.getvalue(),
                file_name="totais_backoffice.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                use_container_width=True
            )
        else:
            st.error("❌ Nenhum arquivo válido para totalização foi encontrado.")


# ============================================================================
# ROTEAMENTO POR TEMPLATE
# ============================================================================

st.divider()

if template == "Nikita Digital":
    render_nikita()
elif template == "Backoffice":
    render_backoffice()
