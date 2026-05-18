import streamlit as st
import pandas as pd
import io
from typing import Dict, List, Set

# Configuração da página
st.set_page_config(
    page_title="NN App",
    layout="wide"
)

# Estruturas de dados
estrutura_final = [
    "Album Title",
    "Track Title", 
    "Artists",
    "Label",
    "UPC",
    "ISRC",
    "Product Type",
    "Store",
    "Territory",
    "Sale Type",
    "Transaction Month",
    "Accounted Date",
    "Original Currency",
    "Gross (Original Currency)",
    "Exchange Rate",
    "Currency",
    "Gross",
    "Quantity",
    "Average Unit Gross",
    "% Share",
    "Fees",
    "Net",
    "Gross BRL",   # Nova coluna calculada
    "Net BRL",
    "Payer Name",  # Nova coluna
    "Origem",  # Nova coluna para identificar planilha de origem
    "Nome Arquivo"  # Nova coluna com nome do arquivo original
]

mapeamento_masters = {
    'Album Title': 'Album Title',
    'Track Title': 'Track Title',
    'Artists': 'Artists',
    'Label': 'Label',
    'UPC': 'UPC',
    'ISRC': 'ISRC',
    'Product Type': 'Product Type',
    'Store': 'Store',
    'Territory': 'Territory',
    'Sale Type': 'Sale Type',
    'Transaction Month': 'Transaction Month',
    'Accounted Date': 'Accounted Date',
    'Original Currency': 'Original Currency',
    'Gross (Original Currency)': 'Gross (Original Currency)',
    'Exchange Rate': 'Exchange Rate',
    'Currency': 'Currency',
    'Gross': 'Gross',
    'Quantity': 'Quantity',
    'Average Unit Gross': 'Average Unit Gross',
    '% Share': '% Share',
    'Fees': 'Fees',
    'Net': 'Net'
}

mapeamento_shares_in_out = {
    'Title': 'Album Title',
    'Artists': 'Artists',
    'Parent ID': 'UPC',
    'ID': 'ISRC',
    'Product Type': 'Product Type',
    'Store': 'Store',
    'Territory': 'Territory',
    'Sale Type': 'Sale Type',
    'Transaction Month': 'Transaction Month',
    'Accounted Date': 'Accounted Date',
    'Currency': 'Currency',
    'Quantity': 'Quantity',
    '% Share In/Out': '% Share',
    'Net': 'Net',
    'Payer Name': 'Payer Name'  # Nova coluna mapeada
}

def identificar_moedas(dfs: Dict[str, pd.DataFrame]) -> Set[str]:
    """Identifica todas as moedas únicas nas planilhas"""
    moedas = set()
    for nome_planilha, df in dfs.items():
        if 'Currency' in df.columns:
            moedas_planilha = df['Currency'].dropna().unique()
            moedas.update(moedas_planilha)
    return moedas

def processar_planilha(df: pd.DataFrame, mapeamento: Dict[str, str], nome_planilha: str, nome_arquivo: str = None) -> pd.DataFrame:
    """Processa uma planilha aplicando o mapeamento de colunas"""
    # Filtra apenas "In" para Shares In & Out
    if nome_planilha == "Shares In & Out" and 'Share Type' in df.columns:
        df = df[df['Share Type'] == 'In'].copy()
    
    # Renomeia as colunas conforme o mapeamento
    df_processado = df.rename(columns=mapeamento)
    
    # Adiciona a coluna "Origem" com o nome da planilha
    df_processado['Origem'] = nome_planilha
    
    # Adiciona a coluna "Nome Arquivo" com o nome do arquivo original
    if nome_arquivo:
        df_processado['Nome Arquivo'] = nome_arquivo
    else:
        df_processado['Nome Arquivo'] = None
    
    # Garante que todas as colunas da estrutura final existam
    for coluna in estrutura_final:
        if coluna not in df_processado.columns:
            df_processado[coluna] = None
    
    # Reordena as colunas conforme a estrutura final
    df_processado = df_processado[estrutura_final]
    
    return df_processado

def processar_youtube_channels(df: pd.DataFrame, taxas_cambio: Dict[str, float]) -> pd.DataFrame:
    """Processa a planilha Youtube Channels mantendo estrutura original e convertendo valores"""
    df_youtube = df.copy()
    
    # Renomeia as colunas originais primeiro
    if 'Gross' in df_youtube.columns:
        df_youtube = df_youtube.rename(columns={'Gross': 'Onerpm Gross'})
    if 'Net' in df_youtube.columns:
        df_youtube = df_youtube.rename(columns={'Net': 'Onerpm Net'})
    
    # Adiciona colunas de conversão para BRL se tiverem as colunas necessárias
    if 'Onerpm Gross' in df_youtube.columns and 'Currency' in df_youtube.columns:
        def converter_gross_para_brl(row):
            if pd.isna(row['Onerpm Gross']) or pd.isna(row['Currency']):
                return None
            
            moeda = row['Currency']
            valor_gross = row['Onerpm Gross']
            
            if moeda == 'BRL':
                return valor_gross
            elif moeda in taxas_cambio:
                return valor_gross * taxas_cambio[moeda]
            else:
                return None
        
        df_youtube['Gross'] = df_youtube.apply(converter_gross_para_brl, axis=1)
    
    if 'Onerpm Net' in df_youtube.columns and 'Currency' in df_youtube.columns:
        def converter_net_para_brl(row):
            if pd.isna(row['Onerpm Net']) or pd.isna(row['Currency']):
                return None
            
            moeda = row['Currency']
            valor_net = row['Onerpm Net']
            
            if moeda == 'BRL':
                return valor_net
            elif moeda in taxas_cambio:
                return valor_net * taxas_cambio[moeda]
            else:
                return None
        
        df_youtube['Net'] = df_youtube.apply(converter_net_para_brl, axis=1)
    
    return df_youtube

def processar_shares_out(df: pd.DataFrame, taxas_cambio: Dict[str, float]) -> pd.DataFrame:
    """Processa os dados de Share Out separadamente"""
    if 'Share Type' not in df.columns:
        return pd.DataFrame()
    
    # Filtra apenas "Out"
    df_out = df[df['Share Type'] == 'Out'].copy()
    
    if df_out.empty:
        return pd.DataFrame()
    
    # Calcula Net BRL para Share Out
    def converter_para_brl(row):
        if pd.isna(row['Net']) or pd.isna(row['Currency']):
            return None
        
        moeda = row['Currency']
        valor_net = row['Net']
        
        if moeda == 'BRL':
            return valor_net
        elif moeda in taxas_cambio:
            return valor_net * taxas_cambio[moeda]
        else:
            return None
    
    df_out['Net BRL'] = df_out.apply(converter_para_brl, axis=1)
    
    # Seleciona e reordena as colunas conforme solicitado
    colunas_share_out = ['Receiver Name', 'Net', 'Currency', 'Net BRL', 'Artists', 'Title']
    colunas_existentes = [col for col in colunas_share_out if col in df_out.columns]
    
    return df_out[colunas_existentes]

def calcular_gross_brl(df: pd.DataFrame, taxas_cambio: Dict[str, float]) -> pd.DataFrame:
    """Calcula a coluna Gross BRL baseada nas taxas de câmbio"""
    df = df.copy()
    
    def converter_gross_para_brl(row):
        if pd.isna(row['Gross']) or pd.isna(row['Currency']):
            return None
        
        moeda = row['Currency']
        valor_gross = row['Gross']
        
        if moeda == 'BRL':
            return valor_gross
        elif moeda in taxas_cambio:
            return valor_gross * taxas_cambio[moeda]
        else:
            return None
    
    df['Gross BRL'] = df.apply(converter_gross_para_brl, axis=1)
    return df

def calcular_net_brl(df: pd.DataFrame, taxas_cambio: Dict[str, float]) -> pd.DataFrame:
    """Calcula a coluna Net BRL baseada nas taxas de câmbio"""
    df = df.copy()
    
    def converter_para_brl(row):
        if pd.isna(row['Net']) or pd.isna(row['Currency']):
            return None
        
        moeda = row['Currency']
        valor_net = row['Net']
        
        if moeda == 'BRL':
            return valor_net
        elif moeda in taxas_cambio:
            return valor_net * taxas_cambio[moeda]
        else:
            return None
    
    df['Net BRL'] = df.apply(converter_para_brl, axis=1)
    return df

def preparar_df_para_download(df: pd.DataFrame, taxas_cambio: Dict[str, float]) -> pd.DataFrame:
    """Prepara o DataFrame final para download com as colunas renomeadas"""
    # Primeiro calcula Gross BRL
    df_download = calcular_gross_brl(df, taxas_cambio)
    
    # Renomeia as colunas conforme solicitado
    df_download = df_download.rename(columns={
        'Gross': 'Onerpm Gross',
        'Net': 'Onerpm Net',
        'Gross BRL': 'Gross',
        'Net BRL': 'Net'
    })
    
    return df_download

def criar_resumo_financeiro_por_origem(df_final: pd.DataFrame) -> pd.DataFrame:
    """Cria um resumo financeiro por origem das planilhas"""
    resumo_data = []
    
    # Agrupa por origem e calcula totais
    for origem in df_final['Origem'].dropna().unique():
        df_origem = df_final[df_final['Origem'] == origem]
        total_net_brl = df_origem['Net BRL'].sum()
        registros = len(df_origem)
        
        resumo_data.append({
            'Origem': origem,
            'Registros': registros,
            'Total Net BRL': total_net_brl
        })
    
    resumo_df = pd.DataFrame(resumo_data)
    # Adiciona linha de total
    total_registros = resumo_df['Registros'].sum()
    total_net_brl = resumo_df['Total Net BRL'].sum()
    
    resumo_df = pd.concat([
        resumo_df,
        pd.DataFrame([{
            'Origem': 'TOTAL',
            'Registros': total_registros,
            'Total Net BRL': total_net_brl
        }])
    ], ignore_index=True)
    
    return resumo_df

def criar_resumo_share_out(df_share_out: pd.DataFrame) -> pd.DataFrame:
    """Cria resumo dos Share Out por Receiver Name"""
    if df_share_out.empty:
        return pd.DataFrame()
    
    resumo = df_share_out.groupby('Receiver Name').agg({
        'Net BRL': 'sum'
    }).reset_index()
    
    resumo = resumo.sort_values('Net BRL', ascending=False)
    
    # Adiciona linha de total
    total_net_brl = resumo['Net BRL'].sum()
    
    resumo = pd.concat([
        resumo,
        pd.DataFrame([{
            'Receiver Name': 'TOTAL',
            'Net BRL': total_net_brl
        }])
    ], ignore_index=True)
    
    return resumo

# Interface Streamlit
st.title("OneRPM Normalizer")
st.caption("Prepara o relatório OneRPM para upload no Reprtoir")

st.divider()

# Upload do arquivo
uploaded_file = st.file_uploader(
    "Faça upload do arquivo Excel com as planilhas OneRPM:",
    type=['xlsx', 'xls'],
    help="O arquivo deve conter as abas: Masters, Youtube Channels, e Shares In & Out"
)

if uploaded_file is not None:
    try:
        # Lê todas as abas do arquivo
        with st.spinner("Carregando planilhas..."):
            excel_file = pd.ExcelFile(uploaded_file)
            
            # Verifica se as abas necessárias existem
            abas_necessarias = ["Masters", "Youtube Channels", "Shares In & Out"]
            abas_existentes = excel_file.sheet_names
            
            st.info(f"Abas encontradas: {', '.join(abas_existentes)}")
            
            # Carrega as planilhas
            dfs = {}
            for aba in abas_necessarias:
                if aba in abas_existentes:
                    dfs[aba] = pd.read_excel(uploaded_file, sheet_name=aba)
                else:
                    st.warning(f"⚠️ Aba '{aba}' não encontrada no arquivo")
        st.divider()
        if len(dfs) > 0:
            # Identifica moedas
            moedas_encontradas = identificar_moedas(dfs)
            st.subheader("💱 Configuração de Taxas de Câmbio")
            st.write(f"Moedas encontradas: {', '.join(sorted(moedas_encontradas))}")
            
            # Cria inputs para taxas de câmbio
            taxas_cambio = {}
            col1, col2, col3 = st.columns(3)
            
            # Define valores padrão para moedas comuns
            valores_padrao = {
                'USD': 5.0,
                'EUR': 5.5,
                'GBP': 6.0,
                'RUB': 0.06,
                'CAD': 3.8,
                'AUD': 3.3,
                'JPY': 0.035
            }
            
            for i, moeda in enumerate(sorted(moedas_encontradas)):
                if moeda != 'BRL':  # BRL não precisa de conversão
                    col = [col1, col2, col3][i % 3]
                    with col1:
                        valor_padrao = valores_padrao.get(moeda, 1.0)
                        taxa = st.number_input(
                            f"Taxa {moeda} → BRL:",
                            min_value=0.0,
                            value=valor_padrao,
                            step=0.01,
                            format="%.4f",
                            key=f"taxa_{moeda}",
                            help=f"Taxa de conversão de {moeda} para Real brasileiro"
                        )
                        taxas_cambio[moeda] = taxa
                else:
                    taxas_cambio[moeda] = 1.0
            
            # Botão para processar
            if st.button("Processar e Gerar Planilhas", type="primary"):
                with st.spinner("Processando dados..."):
                    # Extrai nome do arquivo com e sem extensão
                    nome_arquivo_completo = uploaded_file.name if uploaded_file.name else "arquivo.xlsx"
                    nome_arquivo_sem_extensao = uploaded_file.name.rsplit('.', 1)[0] if uploaded_file.name else "arquivo"
                    
                    dfs_processados = []
                    df_share_out = pd.DataFrame()
                    df_youtube_processado = pd.DataFrame()
                    
                    # Processa cada planilha
                    if "Masters" in dfs:
                        df_masters = processar_planilha(dfs["Masters"], mapeamento_masters, "Masters", nome_arquivo_completo)
                        df_masters = calcular_net_brl(df_masters, taxas_cambio)
                        dfs_processados.append(df_masters)
                        st.success(f"✓ Masters processado: {len(df_masters)} registros")
                    
                    if "Youtube Channels" in dfs:
                        # Processa Youtube Channels separadamente mantendo estrutura original
                        df_youtube_processado = processar_youtube_channels(dfs["Youtube Channels"], taxas_cambio)
                        st.success(f"✓ Youtube Channels processado: {len(df_youtube_processado)} registros")
                    
                    if "Shares In & Out" in dfs:
                        # Processa Share In (para concatenar)
                        df_shares_in = processar_planilha(dfs["Shares In & Out"], mapeamento_shares_in_out, "Shares In & Out", nome_arquivo_completo)
                        df_shares_in = calcular_net_brl(df_shares_in, taxas_cambio)
                        dfs_processados.append(df_shares_in)
                        st.success(f"✓ Shares In processado: {len(df_shares_in)} registros")
                        
                        # Processa Share Out (separadamente)
                        df_share_out = processar_shares_out(dfs["Shares In & Out"], taxas_cambio)
                        if not df_share_out.empty:
                            st.success(f"✓ Shares Out processado: {len(df_share_out)} registros para análise")
                    
                    # Concatena Masters e Shares In
                    if dfs_processados:
                        df_final = pd.concat(dfs_processados, ignore_index=True)
                        
                        # Armazena no session_state
                        st.session_state['df_final'] = df_final
                        st.session_state['df_youtube_processado'] = df_youtube_processado
                        st.session_state['df_share_out'] = df_share_out
                        st.session_state['taxas_cambio'] = taxas_cambio
                        st.session_state['nome_arquivo_sem_extensao'] = nome_arquivo_sem_extensao
                        st.session_state['processamento_concluido'] = True
                        
                        st.success(f"🎉 Processamento concluído! Total de registros Masters + Shares In: {len(df_final)}")
                        st.rerun()  # Atualiza a página para mostrar os resultados
    except Exception as e:
        st.error(f"Ocorreu um erro ao processar o arquivo: {e}")

# Exibe resultados somente após processamento
if 'df_final' in st.session_state and 'processamento_concluido' in st.session_state:
    df_final = st.session_state['df_final']
    df_youtube_processado = st.session_state.get('df_youtube_processado', pd.DataFrame())
    df_share_out = st.session_state.get('df_share_out', pd.DataFrame())
    taxas_cambio = st.session_state['taxas_cambio']
    nome_arquivo_original = st.session_state.get('nome_arquivo_sem_extensao', 'arquivo')
    
    st.divider()
    
    # Resumo financeiro por origem
    st.subheader("💲Resumo Financeiro por Origem")
    resumo_origem = criar_resumo_financeiro_por_origem(df_final)
    
    # Exibe métricas em colunas
    col1, col2, col3 = st.columns(3)
    for i, row in resumo_origem.iterrows():
        if row['Origem'] != 'TOTAL':
            col = [col1, col2, col3][i % 3]
            with col:
                st.metric(
                    row['Origem'], 
                    f"R$ {row['Total Net BRL']:,.2f}"
                )

    # Total geral
    total_brl = resumo_origem[resumo_origem['Origem'] == 'TOTAL']['Total Net BRL'].iloc[0]
    st.metric("**💵 Total Masters + Share-In em BRL**", f"R$ {total_brl:,.2f}")
         
    # Adiciona resumo do Youtube Channels se existir
    if not df_youtube_processado.empty and 'Net' in df_youtube_processado.columns:
        total_youtube_brl = df_youtube_processado['Net'].sum()
        st.metric("📺 Youtube Channels Net BRL", f"R$ {total_youtube_brl:,.2f}")
    
    st.divider()

    # Análise de Share Out
    if not df_share_out.empty:
        st.subheader("📈Análise de Share Out")
        resumo_share_out = criar_resumo_share_out(df_share_out)
        
        if not resumo_share_out.empty:
            # Aplica styling para destacar a linha TOTAL e formatar valores
            def highlight_total(row):
                if row['Receiver Name'] == 'TOTAL':
                    return ['background-color: #f0f0f0; font-weight: bold'] * len(row)
                return [''] * len(row)
            
            def format_numbers(val):
                if isinstance(val, (int, float)) and not pd.isna(val):
                    return f"{val:.2f}"
                return val
            
            # Exibe o dataframe com styling e formatação
            styled_df = resumo_share_out.style.apply(highlight_total, axis=1).format({
                'Net BRL': lambda x: f"{x:.2f}" if pd.notna(x) else x
            })
            st.dataframe(styled_df, use_container_width=True, hide_index=True)
        else:
            st.info("Nenhum dado de Share Out encontrado")
    
    st.divider()
    
    # Botões de download
    st.subheader("📥 Download das Planilhas Finais")
    
    col1, col2 = st.columns(2)
    
    # Arquivo 1: Masters + Shares In
    with col1:
        st.write("**📊 Masters + Shares In**")
        output1 = io.BytesIO()
        with pd.ExcelWriter(output1, engine='openpyxl') as writer:
            # Prepara o DataFrame final para download com colunas renomeadas
            df_final_download = preparar_df_para_download(df_final, taxas_cambio)
            df_final_download.to_excel(writer, sheet_name='Dados_Processados', index=False)
            
            # Adiciona Share Out se existir
            if not df_share_out.empty:
                df_share_out.to_excel(writer, sheet_name='Share_Out_Analysis', index=False)
                resumo_share_out = criar_resumo_share_out(df_share_out)
                if not resumo_share_out.empty:
                    resumo_share_out.to_excel(writer, sheet_name='Resumo_Share_Out', index=False)
        
        st.download_button(
            label="📄 Baixar Masters + Shares In",
            data=output1.getvalue(),
            file_name=f"masters_shares_in_{nome_arquivo_original}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            key="download_masters"
        )
    
    # Arquivo 2: Youtube Channels
    with col2:
        st.write("**📺 Youtube Channels**")
        if not df_youtube_processado.empty:
            output2 = io.BytesIO()
            with pd.ExcelWriter(output2, engine='openpyxl') as writer:
                df_youtube_processado.to_excel(writer, sheet_name='Youtube_Channels', index=False)
            
            st.download_button(
                label="📄 Baixar Youtube Channels",
                data=output2.getvalue(),
                file_name=f"youtube_channels_{nome_arquivo_original}.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                key="download_youtube"
            )
        else:
            st.info("Nenhum dado do Youtube Channels para download")

else:
    pass