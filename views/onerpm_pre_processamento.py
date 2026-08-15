import streamlit as st
import pandas as pd
import io
import re
from datetime import datetime

from utils.page import setup_page


def _extract_date_from_filename(filename: str) -> str:
    """Extrai data do nome do arquivo no formato YYYYMMDD para uso como sufixo.
    Aceita YYYY-MM-DD ou YYYYMMDD em qualquer posição do nome.
    Fallback: data de hoje."""
    m = re.search(r'(\d{4})-(\d{2})-(\d{2})', filename)
    if m:
        return m.group(1) + m.group(2) + m.group(3)
    m = re.search(r'(\d{8})', filename)
    if m:
        return m.group(1)
    return datetime.now().strftime('%Y%m%d')

setup_page(__file__)

# Seleção do tipo de processamento
tipo_processamento = st.selectbox(
    "Selecione o tipo de processamento:",
    ["OneRPM (Masters + Youtube + Shares)", "Publishing Rights", "OneRPM Fragmentado (CSVs)"],
    help="Escolha qual tipo de relatório será processado"
)

st.divider()

# Upload de múltiplos arquivos
if tipo_processamento == "OneRPM (Masters + Youtube + Shares)":
    st.write("Faça upload dos arquivos xlsx contendo as planilhas Masters, Youtube Channels e Shares In & Out")
    uploaded_files = st.file_uploader("Selecione os arquivos xlsx", type=['xlsx'], accept_multiple_files=True)
elif tipo_processamento == "Publishing Rights":
    st.write("Faça upload dos arquivos xlsx contendo a planilha Publishing Rights")
    uploaded_files = st.file_uploader("Selecione os arquivos xlsx", type=['xlsx'], accept_multiple_files=True)
else:
    st.write("Faça upload dos arquivos CSV (masters, youtube, shares, publishing). Os arquivos serão classificados automaticamente pelo nome.")
    uploaded_files = st.file_uploader("Selecione os arquivos CSV", type=['csv'], accept_multiple_files=True)

if uploaded_files:
    try:
        report_date = _extract_date_from_filename(uploaded_files[0].name)

        # ============================================================================
        # PROCESSAMENTO PUBLISHING RIGHTS
        # ============================================================================
        if tipo_processamento == "Publishing Rights":
            # Inicializar dataframe vazio para consolidação
            all_publishing = []
            
            # Processar cada arquivo
            st.subheader("Arquivos carregados")
            for i, uploaded_file in enumerate(uploaded_files, 1):
                st.write(f"{i}. {uploaded_file.name}")
                
                # Ler a planilha Publishing Rights
                df_publishing = pd.read_excel(uploaded_file, sheet_name='Publishing Rights')
                all_publishing.append(df_publishing)
            
            # Consolidar todos os dataframes
            df_publishing = pd.concat(all_publishing, ignore_index=True)
            
            # Limpar dados: remover linhas com Currency inválida ou Net nulo
            df_publishing = df_publishing[df_publishing['Currency'].notna()].copy()
            df_publishing = df_publishing[df_publishing['Currency'].astype(str).str.strip() != ''].copy()
            df_publishing = df_publishing[df_publishing['Net'].notna()].copy()
            
            st.success(f"{len(uploaded_files)} arquivo(s) carregado(s) e consolidado(s) com sucesso")
            st.divider()
            
            # RESUMO: Valores por moeda
            st.subheader("Valores por moeda (antes das taxas)")
            
            if df_publishing.empty or 'Net' not in df_publishing.columns or df_publishing['Net'].isna().all() or df_publishing['Net'].sum() == 0:
                st.write("*Sem rendimentos*")
            else:
                if 'Currency' in df_publishing.columns:
                    summary = df_publishing.groupby('Currency')['Net'].sum().reset_index()
                    summary.columns = ['Moeda', 'Valor']
                    st.dataframe(summary, hide_index=True, use_container_width=True)
                else:
                    st.write(f"Total: {df_publishing['Net'].sum():,.2f}")
            
            st.divider()
            
            # Inputs para taxas bancárias
            st.subheader("Taxas bancárias")
            
            col1, col2 = st.columns(2)
            with col1:
                taxa_brl = st.number_input("Taxa BRL", min_value=0.0, value=0.49, step=0.01, format="%.2f", help="Valor da taxa bancária a ser descontada proporcionalmente")
            with col2:
                taxa_usd = st.number_input("Taxa USD", min_value=0.0, value=26.00, step=0.01, format="%.2f", help="Valor da taxa bancária a ser descontada proporcionalmente")
            
            st.divider()
            
            # Aplicar descontos proporcionais
            def apply_discount(df, currency, discount_amount):
                if discount_amount == 0:
                    return df
                
                # Calcular total da moeda
                total_currency = df[df['Currency'] == currency]['Net'].sum()
                
                if total_currency == 0:
                    return df
                
                # Calcular fator de redução
                fator_reducao = (total_currency - discount_amount) / total_currency
                
                # Aplicar desconto proporcional
                df.loc[df['Currency'] == currency, 'Net'] = \
                    df.loc[df['Currency'] == currency, 'Net'] * fator_reducao
                
                return df
            
            # Criar cópia para aplicar os descontos
            df_publishing_final = df_publishing.copy()
            
            # Aplicar descontos
            if taxa_brl > 0:
                df_publishing_final = apply_discount(df_publishing_final, 'BRL', taxa_brl)
            
            if taxa_usd > 0:
                df_publishing_final = apply_discount(df_publishing_final, 'USD', taxa_usd)
            
            # RESUMO: Valores após descontos
            st.subheader("Valores após descontos das taxas")
            
            if df_publishing_final.empty or df_publishing_final['Net'].sum() == 0:
                st.write("*Sem rendimentos*")
            else:
                summary_final = df_publishing_final.groupby('Currency')['Net'].sum().reset_index()
                summary_final.columns = ['Moeda', 'Valor']
                st.dataframe(summary_final, hide_index=True, use_container_width=True)
            
            st.divider()
            
            # Downloads
            st.subheader("Download dos resultados finais")
            
            # Função para criar arquivo Excel
            def to_excel(df):
                df = df.copy()
                for col in df.columns:
                    if pd.api.types.is_datetime64_any_dtype(df[col]):
                        df[col] = df[col].dt.strftime('%Y-%m-%d')
                output = io.BytesIO()
                with pd.ExcelWriter(output, engine='openpyxl') as writer:
                    df.to_excel(writer, index=False)
                return output.getvalue()
            
            if not df_publishing_final.empty:
                # Download completo (todas as moedas)
                excel_data_all = to_excel(df_publishing_final)
                st.download_button(
                    label="📥 Download Publishing Rights (Todas as moedas)",
                    data=excel_data_all,
                    file_name=f"Publishing_Rights_COMPLETO_{report_date}.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    use_container_width=True
                )
                
                st.write("")
                st.write("**Download por moeda:**")
                
                # Downloads individuais por moeda
                currencies = sorted([str(c) for c in df_publishing_final['Currency'].unique() if pd.notna(c)])
                
                # Criar colunas para organizar os botões
                cols = st.columns(min(len(currencies), 3))
                
                for idx, currency in enumerate(currencies):
                    col_idx = idx % 3
                    with cols[col_idx]:
                        df_download = df_publishing_final[df_publishing_final['Currency'] == currency]
                        excel_data = to_excel(df_download)
                        st.download_button(
                            label=f"Download {currency}",
                            data=excel_data,
                            file_name=f"Publishing_Rights_{currency}_{report_date}.xlsx",
                            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                            use_container_width=True
                        )
        
        # ============================================================================
        # PROCESSAMENTO ONERPM FRAGMENTADO (CSVs)
        # ============================================================================
        elif tipo_processamento == "OneRPM Fragmentado (CSVs)":
            # Classificar arquivos pelo nome
            all_masters_csv = []
            all_youtube_csv = []
            all_shares_csv = []
            all_publishing_csv = []

            st.subheader("Arquivos carregados")
            for i, uploaded_file in enumerate(uploaded_files, 1):
                filename = uploaded_file.name.lower()
                original_name = uploaded_file.name

                # Reporting Date a partir do prefixo do nome (YYYY-MM-DD → YYYY/MM/DD)
                reporting_date = (
                    original_name[:10].replace('-', '/')
                    if len(original_name) >= 10 and original_name[4] == '-' and original_name[7] == '-'
                    else None
                )

                if 'master' in filename:
                    df_csv = pd.read_csv(uploaded_file)
                    df_csv['Reporting Date'] = reporting_date
                    all_masters_csv.append(df_csv)
                    file_type = "Masters"
                elif 'youtube' in filename:
                    df_csv = pd.read_csv(uploaded_file)
                    df_csv['Reporting Date'] = reporting_date
                    all_youtube_csv.append(df_csv)
                    file_type = "Youtube"
                elif 'share' in filename:
                    df_csv = pd.read_csv(uploaded_file)
                    df_csv['Reporting Date'] = reporting_date
                    all_shares_csv.append(df_csv)
                    file_type = "Shares"
                elif 'publishing' in filename:
                    df_csv = pd.read_csv(uploaded_file)
                    df_csv['Reporting Date'] = reporting_date
                    all_publishing_csv.append(df_csv)
                    file_type = "Publishing"
                else:
                    file_type = "Ignorado (não identificado)"

                st.write(f"{i}. {uploaded_file.name} → **{file_type}**")

            if not (all_masters_csv or all_youtube_csv or all_shares_csv or all_publishing_csv):
                st.warning("Nenhum arquivo válido identificado. Os nomes devem conter 'masters', 'youtube', 'shares' ou 'publishing'.")
            else:
                # Consolidar
                df_masters = pd.concat(all_masters_csv, ignore_index=True) if all_masters_csv else pd.DataFrame()
                df_youtube = pd.concat(all_youtube_csv, ignore_index=True) if all_youtube_csv else pd.DataFrame()
                df_shares = pd.concat(all_shares_csv, ignore_index=True) if all_shares_csv else pd.DataFrame()
                df_publishing = pd.concat(all_publishing_csv, ignore_index=True) if all_publishing_csv else pd.DataFrame()

                st.success(f"{len(uploaded_files)} arquivo(s) carregado(s) e consolidado(s) com sucesso")
                st.divider()

                # RESUMO 1: Soma por planilha original
                st.subheader("Valores por planilha original (consolidado)")

                def show_summary_df(df, sheet_name):
                    st.write(f"**{sheet_name}:**")
                    if df.empty or 'Net' not in df.columns or df['Net'].isna().all() or df['Net'].sum() == 0:
                        st.write("*Sem rendimentos*")
                    else:
                        if 'Currency' in df.columns:
                            summary = df.groupby('Currency')['Net'].sum().reset_index()
                            summary.columns = ['Moeda', 'Valor']
                            st.dataframe(summary, hide_index=True, use_container_width=True)
                        else:
                            st.write(f"Total: {df['Net'].sum():,.2f}")

                show_summary_df(df_masters, "Masters")
                show_summary_df(df_youtube, "Youtube Channels")
                show_summary_df(df_shares, "Shares In & Out")
                show_summary_df(df_publishing, "Publishing Rights")

                # Análise Share-In e Share-Out
                if not df_shares.empty and 'Share Type' in df_shares.columns and 'Net' in df_shares.columns:
                    st.write("")
                    share_in = df_shares[df_shares['Share Type'] == 'In']
                    share_out = df_shares[df_shares['Share Type'] == 'Out']

                    st.write("**Share-In:**")
                    if share_in.empty or share_in['Net'].sum() == 0:
                        st.write("*Sem rendimentos*")
                    else:
                        if 'Currency' in share_in.columns:
                            summary_in = share_in.groupby('Currency')['Net'].sum().reset_index()
                            summary_in.columns = ['Moeda', 'Valor']
                            st.dataframe(summary_in, hide_index=True, use_container_width=True)

                    st.write("**Share-Out:**")
                    if share_out.empty or share_out['Net'].sum() == 0:
                        st.write("*Sem rendimentos*")
                    else:
                        if 'Currency' in share_out.columns:
                            summary_out = share_out.groupby('Currency')['Net'].sum().reset_index()
                            summary_out.columns = ['Moeda', 'Valor']
                            st.dataframe(summary_out, hide_index=True, use_container_width=True)

                st.divider()

                # Processamento
                st.subheader("Processamento dos dados")

                columns_masters = ['Track Title', 'Artists', 'Product Type', 'ISRC', 'UPC', 'Store',
                                   'Territory', 'Sale Type', 'Transaction Month', 'Accounted Date',
                                   'Currency', 'Quantity', 'Net', 'Reporting Date']
                columns_youtube = ['Video Title', 'Video ID', 'Channel ID', 'Store', 'Territory',
                                   'Sale Type', 'Transaction Month', 'Accounted Date', 'Currency',
                                   'Quantity', 'Net', 'Reporting Date']

                # Manter TODAS as colunas originais dos CSVs Masters/Youtube (igual à opção 1, que preserva colunas do XLSX)
                df_masters_reduced = df_masters.copy() if not df_masters.empty else pd.DataFrame(columns=columns_masters)
                df_youtube_reduced = df_youtube.copy() if not df_youtube.empty else pd.DataFrame(columns=columns_youtube)

                # Processar Shares (excluir listener-1703345420400, separar YouTube Video)
                if not df_shares.empty:
                    df_shares_filtered = df_shares[df_shares['Receiver Name'] != 'listener-1703345420400'].copy()
                    df_shares_youtube = df_shares_filtered[df_shares_filtered['Product Type'] == 'YouTube Video'].copy()
                    df_shares_masters = df_shares_filtered[df_shares_filtered['Product Type'] != 'YouTube Video'].copy()

                    if not df_shares_masters.empty:
                        df_shares_masters_mapped = df_shares_masters.rename(columns={
                            'Title': 'Track Title',
                            'ID': 'ISRC',
                            'Parent ID': 'UPC'
                        })[columns_masters]
                    else:
                        df_shares_masters_mapped = pd.DataFrame(columns=columns_masters)

                    if not df_shares_youtube.empty:
                        df_shares_youtube_mapped = df_shares_youtube.rename(columns={
                            'Title': 'Video Title',
                            'ID': 'Video ID',
                            'Parent ID': 'Channel ID'
                        })[columns_youtube]
                    else:
                        df_shares_youtube_mapped = pd.DataFrame(columns=columns_youtube)
                else:
                    df_shares_masters_mapped = pd.DataFrame(columns=columns_masters)
                    df_shares_youtube_mapped = pd.DataFrame(columns=columns_youtube)

                df_masters_concat = pd.concat([df_masters_reduced, df_shares_masters_mapped], ignore_index=True)
                df_youtube_concat = pd.concat([df_youtube_reduced, df_shares_youtube_mapped], ignore_index=True)

                # Limpar Publishing
                if not df_publishing.empty:
                    df_publishing_clean = df_publishing[df_publishing['Currency'].notna()].copy()
                    df_publishing_clean = df_publishing_clean[df_publishing_clean['Currency'].astype(str).str.strip() != ''].copy()
                    df_publishing_clean = df_publishing_clean[df_publishing_clean['Net'].notna()].copy()
                else:
                    df_publishing_clean = pd.DataFrame()

                st.success("Dados concatenados com sucesso")
                st.divider()

                # RESUMO 2: Valores após concatenação
                st.subheader("Valores após concatenação")

                st.write("**Masters + Shares In & Out:**")
                if df_masters_concat.empty or df_masters_concat['Net'].sum() == 0:
                    st.write("*Sem rendimentos*")
                else:
                    summary_masters = df_masters_concat.groupby('Currency')['Net'].sum().reset_index()
                    summary_masters.columns = ['Moeda', 'Valor']
                    st.dataframe(summary_masters, hide_index=True, use_container_width=True)

                st.write("**Youtube Channels:**")
                if df_youtube_concat.empty or df_youtube_concat['Net'].sum() == 0:
                    st.write("*Sem rendimentos*")
                else:
                    summary_youtube = df_youtube_concat.groupby('Currency')['Net'].sum().reset_index()
                    summary_youtube.columns = ['Moeda', 'Valor']
                    st.dataframe(summary_youtube, hide_index=True, use_container_width=True)

                st.write("**Publishing Rights:**")
                if df_publishing_clean.empty or df_publishing_clean['Net'].sum() == 0:
                    st.write("*Sem rendimentos*")
                else:
                    summary_pub = df_publishing_clean.groupby('Currency')['Net'].sum().reset_index()
                    summary_pub.columns = ['Moeda', 'Valor']
                    st.dataframe(summary_pub, hide_index=True, use_container_width=True)

                st.divider()

                # Inputs para taxas bancárias
                st.subheader("Taxas bancárias - Masters + Youtube")
                col1, col2 = st.columns(2)
                with col1:
                    taxa_brl_my = st.number_input("Taxa BRL", min_value=0.0, value=0.49, step=0.01, format="%.2f", key="frag_taxa_brl_my", help="Aplicada proporcionalmente entre Masters e Youtube")
                with col2:
                    taxa_usd_my = st.number_input("Taxa USD", min_value=0.0, value=26.00, step=0.01, format="%.2f", key="frag_taxa_usd_my", help="Aplicada proporcionalmente entre Masters e Youtube")

                st.subheader("Taxas bancárias - Publishing")
                col3, col4 = st.columns(2)
                with col3:
                    taxa_brl_pub = st.number_input("Taxa BRL", min_value=0.0, value=0.49, step=0.01, format="%.2f", key="frag_taxa_brl_pub", help="Aplicada proporcionalmente em Publishing Rights")
                with col4:
                    taxa_usd_pub = st.number_input("Taxa USD", min_value=0.0, value=26.00, step=0.01, format="%.2f", key="frag_taxa_usd_pub", help="Aplicada proporcionalmente em Publishing Rights")

                st.divider()

                # Funções de desconto
                def apply_proportional_discount(df_m, df_y, currency, discount_amount):
                    if discount_amount == 0:
                        return df_m, df_y
                    total_m = df_m[df_m['Currency'] == currency]['Net'].sum() if not df_m.empty else 0
                    total_y = df_y[df_y['Currency'] == currency]['Net'].sum() if not df_y.empty else 0
                    total_combined = total_m + total_y
                    if total_combined == 0:
                        return df_m, df_y
                    discount_m = discount_amount * (total_m / total_combined)
                    discount_y = discount_amount * (total_y / total_combined)
                    if total_m > 0:
                        df_m.loc[df_m['Currency'] == currency, 'Net'] = \
                            df_m.loc[df_m['Currency'] == currency, 'Net'] - \
                            (df_m.loc[df_m['Currency'] == currency, 'Net'] / total_m * discount_m)
                    if total_y > 0:
                        df_y.loc[df_y['Currency'] == currency, 'Net'] = \
                            df_y.loc[df_y['Currency'] == currency, 'Net'] - \
                            (df_y.loc[df_y['Currency'] == currency, 'Net'] / total_y * discount_y)
                    return df_m, df_y

                def apply_discount(df, currency, discount_amount):
                    if discount_amount == 0 or df.empty:
                        return df
                    total_currency = df[df['Currency'] == currency]['Net'].sum()
                    if total_currency == 0:
                        return df
                    fator_reducao = (total_currency - discount_amount) / total_currency
                    df.loc[df['Currency'] == currency, 'Net'] = df.loc[df['Currency'] == currency, 'Net'] * fator_reducao
                    return df

                df_masters_final = df_masters_concat.copy()
                df_youtube_final = df_youtube_concat.copy()
                df_publishing_final = df_publishing_clean.copy()

                if taxa_brl_my > 0:
                    df_masters_final, df_youtube_final = apply_proportional_discount(df_masters_final, df_youtube_final, 'BRL', taxa_brl_my)
                if taxa_usd_my > 0:
                    df_masters_final, df_youtube_final = apply_proportional_discount(df_masters_final, df_youtube_final, 'USD', taxa_usd_my)

                if taxa_brl_pub > 0:
                    df_publishing_final = apply_discount(df_publishing_final, 'BRL', taxa_brl_pub)
                if taxa_usd_pub > 0:
                    df_publishing_final = apply_discount(df_publishing_final, 'USD', taxa_usd_pub)

                # RESUMO 3: Valores após descontos
                st.subheader("Valores após descontos das taxas")

                st.write("**Masters + Shares In & Out:**")
                if df_masters_final.empty or df_masters_final['Net'].sum() == 0:
                    st.write("*Sem rendimentos*")
                else:
                    summary_masters_final = df_masters_final.groupby('Currency')['Net'].sum().reset_index()
                    summary_masters_final.columns = ['Moeda', 'Valor']
                    st.dataframe(summary_masters_final, hide_index=True, use_container_width=True)

                st.write("**Youtube Channels:**")
                if df_youtube_final.empty or df_youtube_final['Net'].sum() == 0:
                    st.write("*Sem rendimentos*")
                else:
                    summary_youtube_final = df_youtube_final.groupby('Currency')['Net'].sum().reset_index()
                    summary_youtube_final.columns = ['Moeda', 'Valor']
                    st.dataframe(summary_youtube_final, hide_index=True, use_container_width=True)

                st.write("**Publishing Rights:**")
                if df_publishing_final.empty or df_publishing_final['Net'].sum() == 0:
                    st.write("*Sem rendimentos*")
                else:
                    summary_pub_final = df_publishing_final.groupby('Currency')['Net'].sum().reset_index()
                    summary_pub_final.columns = ['Moeda', 'Valor']
                    st.dataframe(summary_pub_final, hide_index=True, use_container_width=True)

                st.divider()

                # Downloads
                st.subheader("Download dos resultados finais")

                def to_excel(df):
                    output = io.BytesIO()
                    with pd.ExcelWriter(output, engine='openpyxl') as writer:
                        df.to_excel(writer, index=False)
                    return output.getvalue()

                col1, col2, col3 = st.columns(3)

                with col1:
                    st.write("**Masters + Shares In & Out:**")
                    if not df_masters_final.empty:
                        excel_data_all = to_excel(df_masters_final)
                        st.download_button(
                            label="📥 Download Masters (Todas as moedas)",
                            data=excel_data_all,
                            file_name=f"Masters_COMPLETO_{report_date}.xlsx",
                            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                            use_container_width=True,
                            key="frag_dl_masters_all"
                        )
                        st.write("")
                        st.write("*Por moeda:*")
                        currencies_masters = sorted([str(c) for c in df_masters_final['Currency'].unique() if pd.notna(c)])
                        for currency in currencies_masters:
                            df_download = df_masters_final[df_masters_final['Currency'] == currency]
                            excel_data = to_excel(df_download)
                            st.download_button(
                                label=f"Download Masters {currency}",
                                data=excel_data,
                                file_name=f"Masters_{currency}_{report_date}.xlsx",
                                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                                use_container_width=True,
                                key=f"frag_dl_masters_{currency}"
                            )

                with col2:
                    st.write("**Youtube Channels:**")
                    if not df_youtube_final.empty:
                        excel_data_all = to_excel(df_youtube_final)
                        st.download_button(
                            label="📥 Download Youtube (Todas as moedas)",
                            data=excel_data_all,
                            file_name=f"Youtube_COMPLETO_{report_date}.xlsx",
                            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                            use_container_width=True,
                            key="frag_dl_youtube_all"
                        )
                        st.write("")
                        st.write("*Por moeda:*")
                        currencies_youtube = sorted([str(c) for c in df_youtube_final['Currency'].unique() if pd.notna(c)])
                        for currency in currencies_youtube:
                            df_download = df_youtube_final[df_youtube_final['Currency'] == currency]
                            excel_data = to_excel(df_download)
                            st.download_button(
                                label=f"Download Youtube {currency}",
                                data=excel_data,
                                file_name=f"Youtube_{currency}_{report_date}.xlsx",
                                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                                use_container_width=True,
                                key=f"frag_dl_youtube_{currency}"
                            )

                with col3:
                    st.write("**Publishing Rights:**")
                    if not df_publishing_final.empty:
                        excel_data_all = to_excel(df_publishing_final)
                        st.download_button(
                            label="📥 Download Publishing (Todas as moedas)",
                            data=excel_data_all,
                            file_name=f"Publishing_Rights_COMPLETO_{report_date}.xlsx",
                            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                            use_container_width=True,
                            key="frag_dl_pub_all"
                        )
                        st.write("")
                        st.write("*Por moeda:*")
                        currencies_pub = sorted([str(c) for c in df_publishing_final['Currency'].unique() if pd.notna(c)])
                        for currency in currencies_pub:
                            df_download = df_publishing_final[df_publishing_final['Currency'] == currency]
                            excel_data = to_excel(df_download)
                            st.download_button(
                                label=f"Download Publishing {currency}",
                                data=excel_data,
                                file_name=f"Publishing_Rights_{currency}_{report_date}.xlsx",
                                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                                use_container_width=True,
                                key=f"frag_dl_pub_{currency}"
                            )

                st.divider()

                # RESUMO 4: Valores finais com totais
                st.subheader("Valores finais por moeda e dataframe")

                st.write("**Masters + Shares In & Out:**")
                if df_masters_final.empty or df_masters_final['Net'].sum() == 0:
                    st.write("*Sem rendimentos*")
                else:
                    summary_masters_final = df_masters_final.groupby('Currency')['Net'].sum().reset_index()
                    summary_masters_final.columns = ['Moeda', 'Valor']
                    st.dataframe(summary_masters_final, hide_index=True, use_container_width=True)

                st.write("**Youtube Channels:**")
                if df_youtube_final.empty or df_youtube_final['Net'].sum() == 0:
                    st.write("*Sem rendimentos*")
                else:
                    summary_youtube_final = df_youtube_final.groupby('Currency')['Net'].sum().reset_index()
                    summary_youtube_final.columns = ['Moeda', 'Valor']
                    st.dataframe(summary_youtube_final, hide_index=True, use_container_width=True)

                st.write("**Publishing Rights:**")
                if df_publishing_final.empty or df_publishing_final['Net'].sum() == 0:
                    st.write("*Sem rendimentos*")
                else:
                    summary_pub_final = df_publishing_final.groupby('Currency')['Net'].sum().reset_index()
                    summary_pub_final.columns = ['Moeda', 'Valor']
                    st.dataframe(summary_pub_final, hide_index=True, use_container_width=True)

                # TOTAL GERAL
                st.write("**TOTAL GERAL (Masters + Youtube + Publishing):**")
                all_currencies = set()
                if not df_masters_final.empty:
                    all_currencies |= set(df_masters_final['Currency'].dropna().unique())
                if not df_youtube_final.empty:
                    all_currencies |= set(df_youtube_final['Currency'].dropna().unique())
                if not df_publishing_final.empty:
                    all_currencies |= set(df_publishing_final['Currency'].dropna().unique())

                total_data = []
                for currency in sorted([str(c) for c in all_currencies]):
                    total_m = df_masters_final[df_masters_final['Currency'] == currency]['Net'].sum() if not df_masters_final.empty else 0
                    total_y = df_youtube_final[df_youtube_final['Currency'] == currency]['Net'].sum() if not df_youtube_final.empty else 0
                    total_p = df_publishing_final[df_publishing_final['Currency'] == currency]['Net'].sum() if not df_publishing_final.empty else 0
                    total_data.append({'Moeda': currency, 'Valor': total_m + total_y + total_p})
                summary_total = pd.DataFrame(total_data)
                st.dataframe(summary_total, hide_index=True, use_container_width=True)

        # ============================================================================
        # PROCESSAMENTO ONERPM (código original)
        # ============================================================================
        else:
            # Inicializar dataframes vazios para consolidação
            all_masters = []
            all_youtube = []
            all_shares = []
            
            # Processar cada arquivo
            st.subheader("Arquivos carregados")
            for i, uploaded_file in enumerate(uploaded_files, 1):
                st.write(f"{i}. {uploaded_file.name}")
                
                # Ler as planilhas de cada arquivo
                df_masters = pd.read_excel(uploaded_file, sheet_name='Masters')
                df_youtube = pd.read_excel(uploaded_file, sheet_name='Youtube Channels')
                df_shares = pd.read_excel(uploaded_file, sheet_name='Shares In & Out')
                
                # Adicionar às listas
                all_masters.append(df_masters)
                all_youtube.append(df_youtube)
                all_shares.append(df_shares)
            
            # Consolidar todos os dataframes
            df_masters = pd.concat(all_masters, ignore_index=True)
            df_youtube = pd.concat(all_youtube, ignore_index=True)
            df_shares = pd.concat(all_shares, ignore_index=True)
            
            st.success(f"{len(uploaded_files)} arquivo(s) carregado(s) e consolidado(s) com sucesso")
            st.divider()
            
            # RESUMO 1: Soma por planilha e moeda
            st.subheader("Valores por planilha original (consolidado)")
            
            def show_summary_df(df, sheet_name):
                st.write(f"**{sheet_name}:**")
                if df.empty or 'Net' not in df.columns or df['Net'].isna().all() or df['Net'].sum() == 0:
                    st.write("*Sem rendimentos*")
                else:
                    if 'Currency' in df.columns:
                        summary = df.groupby('Currency')['Net'].sum().reset_index()
                        summary.columns = ['Moeda', 'Valor']
                        st.dataframe(summary, hide_index=True, use_container_width=True)
                    else:
                        st.write(f"Total: {df['Net'].sum():,.2f}")
            
            show_summary_df(df_masters, "Masters")
            show_summary_df(df_youtube, "Youtube Channels")
            show_summary_df(df_shares, "Shares In & Out")
            
            # Análise Share-in e Share-out
            if not df_shares.empty and 'Share Type' in df_shares.columns and 'Net' in df_shares.columns:
                st.write("")
                
                share_in = df_shares[df_shares['Share Type'] == 'In']
                share_out = df_shares[df_shares['Share Type'] == 'Out']
                
                st.write("**Share-In:**")
                if share_in.empty or share_in['Net'].sum() == 0:
                    st.write("*Sem rendimentos*")
                else:
                    if 'Currency' in share_in.columns:
                        summary_in = share_in.groupby('Currency')['Net'].sum().reset_index()
                        summary_in.columns = ['Moeda', 'Valor']
                        st.dataframe(summary_in, hide_index=True, use_container_width=True)
                
                st.write("**Share-Out:**")
                if share_out.empty or share_out['Net'].sum() == 0:
                    st.write("*Sem rendimentos*")
                else:
                    if 'Currency' in share_out.columns:
                        summary_out = share_out.groupby('Currency')['Net'].sum().reset_index()
                        summary_out.columns = ['Moeda', 'Valor']
                        st.dataframe(summary_out, hide_index=True, use_container_width=True)
            
            st.divider()
            
            # Processamento dos dados
            st.subheader("Processamento dos dados")
            
            # Filtrar Shares In & Out
            # Excluir "listener-1703345420400" da coluna Receiver Name
            df_shares_filtered = df_shares[df_shares['Receiver Name'] != 'listener-1703345420400'].copy()
            
            # Separar YouTube Video para concatenar com Youtube Channels
            df_shares_youtube = df_shares_filtered[df_shares_filtered['Product Type'] == 'YouTube Video'].copy()
            
            # Excluir YouTube Video do restante (para concatenar com Masters)
            df_shares_masters = df_shares_filtered[df_shares_filtered['Product Type'] != 'YouTube Video'].copy()
            
            # Mapeamento e concatenação Masters + Shares In & Out
            df_shares_masters_mapped = df_shares_masters.rename(columns={
                'Title': 'Track Title',
                'Artists': 'Artists',
                'Product Type': 'Product Type',
                'ID': 'ISRC',
                'Parent ID': 'UPC',
                'Store': 'Store',
                'Territory': 'Territory',
                'Sale Type': 'Sale Type',
                'Transaction Month': 'Transaction Month',
                'Accounted Date': 'Accounted Date',
                'Currency': 'Currency',
                'Quantity': 'Quantity',
                'Net': 'Net'
            })
            
            # Manter apenas as colunas mapeadas
            columns_masters = ['Track Title', 'Artists', 'Product Type', 'ISRC', 'UPC', 'Store', 
                              'Territory', 'Sale Type', 'Transaction Month', 'Accounted Date', 
                              'Currency', 'Quantity', 'Net']
            
            df_shares_masters_mapped = df_shares_masters_mapped[columns_masters]
            df_masters_concat = pd.concat([df_masters, df_shares_masters_mapped], ignore_index=True)
            
            # Mapeamento e concatenação Youtube Channels + Shares In & Out (YouTube Video)
            df_shares_youtube_mapped = df_shares_youtube.rename(columns={
                'Title': 'Video Title',
                'ID': 'Video ID',
                'Parent ID': 'Channel ID',
                'Store': 'Store',
                'Territory': 'Territory',
                'Sale Type': 'Sale Type',
                'Transaction Month': 'Transaction Month',
                'Accounted Date': 'Accounted Date',
                'Currency': 'Currency',
                'Quantity': 'Quantity',
                'Net': 'Net'
            })
            
            # Manter apenas as colunas mapeadas
            columns_youtube = ['Video Title', 'Video ID', 'Channel ID', 'Store', 'Territory', 
                              'Sale Type', 'Transaction Month', 'Accounted Date', 'Currency', 
                              'Quantity', 'Net']
            
            df_shares_youtube_mapped = df_shares_youtube_mapped[columns_youtube]
            df_youtube_concat = pd.concat([df_youtube, df_shares_youtube_mapped], ignore_index=True)
            
            st.success("Dados concatenados com sucesso")
            st.divider()
            
            # RESUMO 2: Valores após concatenação
            st.subheader("Valores após concatenação")
            
            st.write("**Masters + Shares In & Out:**")
            if df_masters_concat.empty or df_masters_concat['Net'].sum() == 0:
                st.write("*Sem rendimentos*")
            else:
                summary_masters = df_masters_concat.groupby('Currency')['Net'].sum().reset_index()
                summary_masters.columns = ['Moeda', 'Valor']
                st.dataframe(summary_masters, hide_index=True, use_container_width=True)
            
            st.write("**Youtube Channels:**")
            if df_youtube_concat.empty or df_youtube_concat['Net'].sum() == 0:
                st.write("*Sem rendimentos*")
            else:
                summary_youtube = df_youtube_concat.groupby('Currency')['Net'].sum().reset_index()
                summary_youtube.columns = ['Moeda', 'Valor']
                st.dataframe(summary_youtube, hide_index=True, use_container_width=True)
            
            st.divider()
            
            # Inputs para taxas bancárias
            st.subheader("Taxas bancárias")
            
            col1, col2 = st.columns(2)
            with col1:
                taxa_brl = st.number_input("Taxa BRL", min_value=0.0, value=0.49, step=0.01, format="%.2f", help="Valor da taxa bancária a ser descontada proporcionalmente")
            with col2:
                taxa_usd = st.number_input("Taxa USD", min_value=0.0, value=26.00, step=0.01, format="%.2f", help="Valor da taxa bancária a ser descontada proporcionalmente")
            
            st.divider()
            
            # Aplicar descontos proporcionais entre Masters e Youtube
            def apply_proportional_discount(df_masters, df_youtube, currency, discount_amount):
                if discount_amount == 0:
                    return df_masters, df_youtube
                
                # Calcular totais por dataframe
                total_masters = df_masters[df_masters['Currency'] == currency]['Net'].sum()
                total_youtube = df_youtube[df_youtube['Currency'] == currency]['Net'].sum()
                total_combined = total_masters + total_youtube
                
                if total_combined == 0:
                    return df_masters, df_youtube
                
                # Calcular proporção de desconto para cada dataframe
                discount_masters = discount_amount * (total_masters / total_combined)
                discount_youtube = discount_amount * (total_youtube / total_combined)
                
                # Aplicar desconto proporcional
                if total_masters > 0:
                    df_masters.loc[df_masters['Currency'] == currency, 'Net'] = \
                        df_masters.loc[df_masters['Currency'] == currency, 'Net'] - \
                        (df_masters.loc[df_masters['Currency'] == currency, 'Net'] / total_masters * discount_masters)
                
                if total_youtube > 0:
                    df_youtube.loc[df_youtube['Currency'] == currency, 'Net'] = \
                        df_youtube.loc[df_youtube['Currency'] == currency, 'Net'] - \
                        (df_youtube.loc[df_youtube['Currency'] == currency, 'Net'] / total_youtube * discount_youtube)
                
                return df_masters, df_youtube
            
            # Criar cópias para aplicar os descontos
            df_masters_final = df_masters_concat.copy()
            df_youtube_final = df_youtube_concat.copy()
            
            # Aplicar descontos de forma proporcional
            if taxa_brl > 0:
                df_masters_final, df_youtube_final = apply_proportional_discount(df_masters_final, df_youtube_final, 'BRL', taxa_brl)
            
            if taxa_usd > 0:
                df_masters_final, df_youtube_final = apply_proportional_discount(df_masters_final, df_youtube_final, 'USD', taxa_usd)
            
            # RESUMO 3: Valores após descontos
            st.subheader("Valores após descontos das taxas")
            
            st.write("**Masters + Shares In & Out:**")
            if df_masters_final.empty or df_masters_final['Net'].sum() == 0:
                st.write("*Sem rendimentos*")
            else:
                summary_masters_final = df_masters_final.groupby('Currency')['Net'].sum().reset_index()
                summary_masters_final.columns = ['Moeda', 'Valor']
                st.dataframe(summary_masters_final, hide_index=True, use_container_width=True)
            
            st.write("**Youtube Channels:**")
            if df_youtube_final.empty or df_youtube_final['Net'].sum() == 0:
                st.write("*Sem rendimentos*")
            else:
                summary_youtube_final = df_youtube_final.groupby('Currency')['Net'].sum().reset_index()
                summary_youtube_final.columns = ['Moeda', 'Valor']
                st.dataframe(summary_youtube_final, hide_index=True, use_container_width=True)
            
            st.divider()
            
            # Downloads
            st.subheader("Download dos resultados finais")
            
            # Função para criar arquivo Excel
            def to_excel(df):
                df = df.copy()
                for col in df.columns:
                    if pd.api.types.is_datetime64_any_dtype(df[col]):
                        df[col] = df[col].dt.strftime('%Y-%m-%d')
                output = io.BytesIO()
                with pd.ExcelWriter(output, engine='openpyxl') as writer:
                    df.to_excel(writer, index=False)
                return output.getvalue()
            
            col1, col2 = st.columns(2)
            
            # Downloads Masters
            with col1:
                st.write("**Masters + Shares In & Out:**")
                if not df_masters_final.empty:
                    # Download completo (todas as moedas)
                    excel_data_all = to_excel(df_masters_final)
                    st.download_button(
                        label="📥 Download Masters (Todas as moedas)",
                        data=excel_data_all,
                        file_name=f"Masters_COMPLETO_{report_date}.xlsx",
                        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                        use_container_width=True
                    )
                    
                    st.write("")
                    st.write("*Por moeda:*")
                    
                    # Downloads individuais por moeda
                    currencies_masters = sorted(df_masters_final['Currency'].unique())
                    for currency in currencies_masters:
                        df_download = df_masters_final[df_masters_final['Currency'] == currency]
                        excel_data = to_excel(df_download)
                        st.download_button(
                            label=f"Download Masters {currency}",
                            data=excel_data,
                            file_name=f"Masters_{currency}_{report_date}.xlsx",
                            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                            use_container_width=True
                        )
            
            # Downloads Youtube
            with col2:
                st.write("**Youtube Channels:**")
                if not df_youtube_final.empty:
                    # Download completo (todas as moedas)
                    excel_data_all = to_excel(df_youtube_final)
                    st.download_button(
                        label="📥 Download Youtube (Todas as moedas)",
                        data=excel_data_all,
                        file_name=f"Youtube_COMPLETO_{report_date}.xlsx",
                        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                        use_container_width=True
                    )
                    
                    st.write("")
                    st.write("*Por moeda:*")
                    
                    # Downloads individuais por moeda
                    currencies_youtube = sorted(df_youtube_final['Currency'].unique())
                    for currency in currencies_youtube:
                        df_download = df_youtube_final[df_youtube_final['Currency'] == currency]
                        excel_data = to_excel(df_download)
                        st.download_button(
                            label=f"Download Youtube {currency}",
                            data=excel_data,
                            file_name=f"Youtube_{currency}_{report_date}.xlsx",
                            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                            use_container_width=True
                        )
            
            st.divider()
            
            # RESUMO 4: Valores finais com totais
            st.subheader("Valores finais por moeda e dataframe")
            
            st.write("**Masters + Shares In & Out:**")
            if df_masters_final.empty or df_masters_final['Net'].sum() == 0:
                st.write("*Sem rendimentos*")
            else:
                summary_masters_final = df_masters_final.groupby('Currency')['Net'].sum().reset_index()
                summary_masters_final.columns = ['Moeda', 'Valor']
                st.dataframe(summary_masters_final, hide_index=True, use_container_width=True)
            
            st.write("**Youtube Channels:**")
            if df_youtube_final.empty or df_youtube_final['Net'].sum() == 0:
                st.write("*Sem rendimentos*")
            else:
                summary_youtube_final = df_youtube_final.groupby('Currency')['Net'].sum().reset_index()
                summary_youtube_final.columns = ['Moeda', 'Valor']
                st.dataframe(summary_youtube_final, hide_index=True, use_container_width=True)
            
            # TOTAL GERAL: Masters + Youtube por moeda
            st.write("**TOTAL GERAL (Masters + Shares In & Out + Youtube Channels):**")
            
            # Obter todas as moedas únicas
            all_currencies = set(df_masters_final['Currency'].unique()) | set(df_youtube_final['Currency'].unique())
            
            total_data = []
            for currency in sorted(all_currencies):
                total_masters_currency = df_masters_final[df_masters_final['Currency'] == currency]['Net'].sum()
                total_youtube_currency = df_youtube_final[df_youtube_final['Currency'] == currency]['Net'].sum()
                total_currency = total_masters_currency + total_youtube_currency
                total_data.append({'Moeda': currency, 'Valor': total_currency})
            
            summary_total = pd.DataFrame(total_data)
            st.dataframe(summary_total, hide_index=True, use_container_width=True)
        
    except Exception as e:
        st.error(f"Erro ao processar os arquivos: {str(e)}")
        if tipo_processamento == "Publishing Rights":
            st.write("Certifique-se de que todos os arquivos contêm a planilha Publishing Rights")
        elif tipo_processamento == "OneRPM Fragmentado (CSVs)":
            st.write("Certifique-se de fazer upload dos arquivos CSV com nomes contendo 'masters', 'youtube', 'shares' ou 'publishing'")
        else:
            st.write("Certifique-se de que todos os arquivos contêm as planilhas Masters, Youtube Channels e Shares In & Out")

else:
    st.info("Aguardando upload dos arquivos")