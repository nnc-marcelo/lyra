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
    "Gross BRL",
    "Net BRL",
    "Payer Name",
    "Origem",
    "Nome Arquivo"
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
    'Payer Name': 'Payer Name'
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
    
    df_processado = df.rename(columns=mapeamento)
    
    if nome_planilha == "Shares In & Out" and 'Share Type' in df.columns:
        df_processado['Share Type'] = df['Share Type']
    
    df_processado['Origem'] = nome_planilha
    
    if nome_arquivo:
        df_processado['Nome Arquivo'] = nome_arquivo
    else:
        df_processado['Nome Arquivo'] = None
    
    for coluna in estrutura_final:
        if coluna not in df_processado.columns:
            df_processado[coluna] = None
    
    colunas_ordenadas = estrutura_final.copy()
    if 'Share Type' in df_processado.columns:
        colunas_ordenadas.append('Share Type')
    
    df_processado = df_processado[colunas_ordenadas]
    
    return df_processado

def processar_youtube_channels(df: pd.DataFrame, taxas_cambio: Dict[str, float]) -> pd.DataFrame:
    """Processa a planilha Youtube Channels mantendo estrutura original e convertendo valores"""
    df_youtube = df.copy()
    
    if 'Gross' in df_youtube.columns:
        df_youtube = df_youtube.rename(columns={'Gross': 'Onerpm Gross'})
    if 'Net' in df_youtube.columns:
        df_youtube = df_youtube.rename(columns={'Net': 'Onerpm Net'})
    
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
    
    df_out = df[df['Share Type'] == 'Out'].copy()
    
    if df_out.empty:
        return pd.DataFrame()
    
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

def aplicar_desconto_proporcional(df: pd.DataFrame, taxa_usd: float, taxa_brl: float, taxas_cambio: Dict[str, float]) -> pd.DataFrame:
    """Aplica desconto proporcional das taxas bancárias na coluna Net"""
    df = df.copy()
    
    taxa_usd_em_brl = taxa_usd * taxas_cambio.get('USD', 1.0)
    total_taxas_brl = taxa_usd_em_brl + taxa_brl
    
    total_net_brl = df['Net BRL'].sum()
    
    if total_net_brl > 0:
        df['Net'] = df.apply(lambda row: 
            row['Net'] - (row['Net BRL'] / total_net_brl * total_taxas_brl / taxas_cambio.get(row['Currency'], 1.0))
            if pd.notna(row['Net']) and pd.notna(row['Net BRL']) and pd.notna(row['Currency'])
            else row['Net'],
            axis=1
        )
        
        df = calcular_net_brl(df, taxas_cambio)
    
    return df

def preparar_df_para_download(df: pd.DataFrame, taxas_cambio: Dict[str, float]) -> pd.DataFrame:
    """Prepara o DataFrame final para download com as colunas renomeadas"""
    df_download = calcular_gross_brl(df, taxas_cambio)
    
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
    
    for origem in df_final['Origem'].dropna().unique():
        df_origem = df_final[df_final['Origem'] == origem]
        
        if origem == "Shares In & Out":
            df_share_in = df_origem[df_origem['Share Type'] == 'In'] if 'Share Type' in df_origem.columns else df_origem
            if not df_share_in.empty:
                total_net_brl_in = df_share_in['Net BRL'].sum()
                registros_in = len(df_share_in)
                resumo_data.append({
                    'Origem': 'Share In',
                    'Registros': registros_in,
                    'Total Net BRL': total_net_brl_in
                })
            
            df_share_out = df_origem[df_origem['Share Type'] == 'Out'] if 'Share Type' in df_origem.columns else pd.DataFrame()
            if not df_share_out.empty:
                total_net_brl_out = df_share_out['Net BRL'].sum()
                registros_out = len(df_share_out)
                resumo_data.append({
                    'Origem': 'Share Out',
                    'Registros': registros_out,
                    'Total Net BRL': total_net_brl_out
                })
        else:
            total_net_brl = df_origem['Net BRL'].sum()
            registros = len(df_origem)
            resumo_data.append({
                'Origem': origem,
                'Registros': registros,
                'Total Net BRL': total_net_brl
            })
    
    resumo_df = pd.DataFrame(resumo_data)
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
    
    total_net_brl = resumo['Net BRL'].sum()
    
    resumo = pd.concat([
        resumo,
        pd.DataFrame([{
            'Receiver Name': 'TOTAL',
            'Net BRL': total_net_brl
        }])
    ], ignore_index=True)
    
    return resumo

def criar_resumo_por_moeda(df_final: pd.DataFrame) -> pd.DataFrame:
    """Cria resumo dos valores por moeda"""
    resumo = df_final.groupby('Currency').agg({
        'Net': 'sum',
        'Net BRL': 'sum'
    }).reset_index()
    
    resumo = resumo.rename(columns={
        'Currency': 'Moeda',
        'Net': 'Total (Moeda Original)',
        'Net BRL': 'Total (BRL)'
    })
    
    resumo = resumo.sort_values('Total (BRL)', ascending=False)
    
    total_brl = resumo['Total (BRL)'].sum()
    
    resumo = pd.concat([
        resumo,
        pd.DataFrame([{
            'Moeda': 'TOTAL',
            'Total (Moeda Original)': None,
            'Total (BRL)': total_brl
        }])
    ], ignore_index=True)
    
    return resumo

# ===== NOVA FUNÇÃO: GERAR ARQUIVOS POR MOEDA =====
def gerar_arquivos_por_moeda(df_final: pd.DataFrame, df_youtube: pd.DataFrame, df_share_out: pd.DataFrame, 
                              taxas_cambio: Dict[str, float], nome_arquivo_original: str) -> Dict[str, bytes]:
    """
    Gera arquivos Excel separados por moeda
    Retorna um dicionário com {nome_arquivo: bytes_do_arquivo}
    """
    arquivos_gerados = {}
    
    # Prepara o DataFrame final para download
    df_final_preparado = preparar_df_para_download(df_final, taxas_cambio)
    
    # Identifica todas as moedas únicas no df_final
    moedas_masters_shares = df_final_preparado['Currency'].dropna().unique()
    
    # Gera arquivo para cada moeda (Masters + Shares In)
    for moeda in moedas_masters_shares:
        # Filtra dados da moeda específica
        df_moeda = df_final_preparado[df_final_preparado['Currency'] == moeda].copy()
        
        if not df_moeda.empty:
            output = io.BytesIO()
            with pd.ExcelWriter(output, engine='openpyxl') as writer:
                df_moeda.to_excel(writer, sheet_name='Dados_Processados', index=False)
                
                # Adiciona Share Out filtrado por moeda se existir
                if not df_share_out.empty and 'Currency' in df_share_out.columns:
                    df_share_out_moeda = df_share_out[df_share_out['Currency'] == moeda].copy()
                    if not df_share_out_moeda.empty:
                        df_share_out_moeda.to_excel(writer, sheet_name='Share_Out_Analysis', index=False)
                        
                        resumo_share_out_moeda = criar_resumo_share_out(df_share_out_moeda)
                        if not resumo_share_out_moeda.empty:
                            resumo_share_out_moeda.to_excel(writer, sheet_name='Resumo_Share_Out', index=False)
            
            nome_arquivo = f"masters_shares_in_{moeda}_{nome_arquivo_original}.xlsx"
            arquivos_gerados[nome_arquivo] = output.getvalue()
    
    # Gera arquivo para cada moeda (Youtube Channels)
    if not df_youtube.empty and 'Currency' in df_youtube.columns:
        moedas_youtube = df_youtube['Currency'].dropna().unique()
        
        for moeda in moedas_youtube:
            df_youtube_moeda = df_youtube[df_youtube['Currency'] == moeda].copy()
            
            if not df_youtube_moeda.empty:
                output = io.BytesIO()
                with pd.ExcelWriter(output, engine='openpyxl') as writer:
                    df_youtube_moeda.to_excel(writer, sheet_name='Youtube_Channels', index=False)
                
                nome_arquivo = f"youtube_channels_{moeda}_{nome_arquivo_original}.xlsx"
                arquivos_gerados[nome_arquivo] = output.getvalue()
    
    return arquivos_gerados

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
        with st.spinner("Carregando planilhas..."):
            excel_file = pd.ExcelFile(uploaded_file)
            
            abas_necessarias = ["Masters", "Youtube Channels", "Shares In & Out"]
            abas_existentes = excel_file.sheet_names
            
            st.info(f"Abas encontradas: {', '.join(abas_existentes)}")
            
            dfs = {}
            for aba in abas_necessarias:
                if aba in abas_existentes:
                    dfs[aba] = pd.read_excel(uploaded_file, sheet_name=aba)
                else:
                    st.warning(f"⚠️ Aba '{aba}' não encontrada no arquivo")
        st.divider()
        if len(dfs) > 0:
            moedas_encontradas = identificar_moedas(dfs)
            st.subheader("💱 Configuração de Taxas de Câmbio")
            st.write(f"Moedas encontradas: {', '.join(sorted(moedas_encontradas))}")
            
            taxas_cambio = {}
            col1, col2, col3 = st.columns(3)
            
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
                if moeda != 'BRL':
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
            
            st.divider()
            
            st.subheader("🏦 Taxas Bancárias")
            st.write("Preencha os valores fixos para taxas a serem descontadas proporcionalmente:")
            
            col1, col2 = st.columns(2)
            with col1:
                taxa_usd = st.number_input(
                    "Insira o valor fixo da taxa em USD:",
                    min_value=0.0,
                    value=26.00,
                    step=0.01,
                    format="%.2f",
                    key="taxa_bancaria_usd"
                )
            with col2:
                taxa_brl = st.number_input(
                    "Insira o valor fixo da taxa em BRL:",
                    min_value=0.0,
                    value=0.49,
                    step=0.01,
                    format="%.2f",
                    key="taxa_bancaria_brl"
                )
            
            if st.button("Processar e Gerar Planilhas", type="primary"):
                with st.spinner("Processando dados..."):
                    nome_arquivo_completo = uploaded_file.name if uploaded_file.name else "arquivo.xlsx"
                    nome_arquivo_sem_extensao = uploaded_file.name.rsplit('.', 1)[0] if uploaded_file.name else "arquivo"
                    
                    dfs_processados = []
                    df_share_out = pd.DataFrame()
                    df_youtube_processado = pd.DataFrame()
                    
                    if "Masters" in dfs:
                        df_masters = processar_planilha(dfs["Masters"], mapeamento_masters, "Masters", nome_arquivo_completo)
                        df_masters = calcular_net_brl(df_masters, taxas_cambio)
                        dfs_processados.append(df_masters)
                        st.success(f"✓ Masters processado: {len(df_masters)} registros")
                    
                    if "Youtube Channels" in dfs:
                        df_youtube_processado = processar_youtube_channels(dfs["Youtube Channels"], taxas_cambio)
                        st.success(f"✓ Youtube Channels processado: {len(df_youtube_processado)} registros")
                    
                    if "Shares In & Out" in dfs:
                        df_shares = processar_planilha(dfs["Shares In & Out"], mapeamento_shares_in_out, "Shares In & Out", nome_arquivo_completo)
                        df_shares = calcular_net_brl(df_shares, taxas_cambio)
                        dfs_processados.append(df_shares)
                        st.success(f"✓ Shares In & Out processado: {len(df_shares)} registros")
                        
                        df_share_out = processar_shares_out(dfs["Shares In & Out"], taxas_cambio)
                        if not df_share_out.empty:
                            st.success(f"✓ Shares Out processado: {len(df_share_out)} registros para análise")
                    
                    if dfs_processados:
                        df_final_sem_desconto = pd.concat(dfs_processados, ignore_index=True)
                        df_final = aplicar_desconto_proporcional(df_final_sem_desconto, taxa_usd, taxa_brl, taxas_cambio)
                        
                        st.session_state['df_final_sem_desconto'] = df_final_sem_desconto
                        st.session_state['df_final'] = df_final
                        st.session_state['df_youtube_processado'] = df_youtube_processado
                        st.session_state['df_share_out'] = df_share_out
                        st.session_state['taxas_cambio'] = taxas_cambio
                        st.session_state['nome_arquivo_sem_extensao'] = nome_arquivo_sem_extensao
                        st.session_state['processamento_concluido'] = True
                        
                        st.success(f"🎉 Processamento concluído! Total de registros Masters + Shares In & Out: {len(df_final)}")
                        st.rerun()
    except Exception as e:
        st.error(f"Ocorreu um erro ao processar o arquivo: {e}")

# Exibe resultados somente após processamento
if 'df_final' in st.session_state and 'processamento_concluido' in st.session_state:
    df_final_sem_desconto = st.session_state['df_final_sem_desconto']
    df_final = st.session_state['df_final']
    df_youtube_processado = st.session_state.get('df_youtube_processado', pd.DataFrame())
    df_share_out = st.session_state.get('df_share_out', pd.DataFrame())
    taxas_cambio = st.session_state['taxas_cambio']
    nome_arquivo_original = st.session_state.get('nome_arquivo_sem_extensao', 'arquivo')
    
    st.divider()
    
    # Resumo por moeda (ANTES do desconto)
    st.subheader("💱 Resumo por Moeda")
    resumo_moeda = criar_resumo_por_moeda(df_final_sem_desconto)
    
    def highlight_total_moeda(row):
        if row['Moeda'] == 'TOTAL':
            return ['background-color: #f0f0f0; font-weight: bold'] * len(row)
        return [''] * len(row)
    
    styled_moeda = resumo_moeda.style.apply(highlight_total_moeda, axis=1).format({
        'Total (Moeda Original)': lambda x: f"{x:,.2f}" if pd.notna(x) else '-',
        'Total (BRL)': lambda x: f"{x:,.2f}" if pd.notna(x) else x
    })
    st.dataframe(styled_moeda, use_container_width=True, hide_index=True)

    st.divider()

    # Resumo financeiro por origem ANTES do desconto
    st.subheader("💲Resumo Financeiro por Origem (Antes do Desconto de Taxas)")
    resumo_origem = criar_resumo_financeiro_por_origem(df_final_sem_desconto)
    
    cols = st.columns(len(resumo_origem) - 1)
    for i, row in resumo_origem.iterrows():
        if row['Origem'] != 'TOTAL':
            col_idx = i % len(cols)
            with cols[col_idx]:
                st.metric(
                    row['Origem'], 
                    f"R$ {row['Total Net BRL']:,.2f}"
                )

    total_brl = resumo_origem[resumo_origem['Origem'] == 'TOTAL']['Total Net BRL'].iloc[0]
    st.metric("**💵 Total Masters + Share-In + Share-Out em BRL**", f"R$ {total_brl:,.2f}")

    if not df_youtube_processado.empty and 'Net' in df_youtube_processado.columns:
        total_youtube_brl = df_youtube_processado['Net'].sum()
        st.metric("📺 Youtube Channels Net BRL", f"R$ {total_youtube_brl:,.2f}")
    
    st.divider()
      
    # Resumo financeiro APÓS desconto das taxas bancárias
    st.subheader("💲Resumo Financeiro por Origem (Após Desconto de Taxas)")
    resumo_origem_com_desconto = criar_resumo_financeiro_por_origem(df_final)
    
    cols_desconto = st.columns(len(resumo_origem_com_desconto) - 1)
    for i, row in resumo_origem_com_desconto.iterrows():
        if row['Origem'] != 'TOTAL':
            col_idx = i % len(cols_desconto)
            with cols_desconto[col_idx]:
                st.metric(
                    row['Origem'], 
                    f"R$ {row['Total Net BRL']:,.2f}"
                )

    total_brl_com_desconto = resumo_origem_com_desconto[resumo_origem_com_desconto['Origem'] == 'TOTAL']['Total Net BRL'].iloc[0]
    st.metric("**💵 Total Masters + Share-In + Share-Out em BRL (Após Desconto)**", f"R$ {total_brl_com_desconto:,.2f}")

    st.divider()

    # Análise de Share Out
    if not df_share_out.empty:
        st.subheader("📈Análise de Share Out")
        resumo_share_out = criar_resumo_share_out(df_share_out)
        
        if not resumo_share_out.empty:
            def highlight_total(row):
                if row['Receiver Name'] == 'TOTAL':
                    return ['background-color: #f0f0f0; font-weight: bold'] * len(row)
                return [''] * len(row)
            
            styled_df = resumo_share_out.style.apply(highlight_total, axis=1).format({
                'Net BRL': lambda x: f"{x:.2f}" if pd.notna(x) else x
            })
            st.dataframe(styled_df, use_container_width=True, hide_index=True)
        else:
            st.info("Nenhum dado de Share Out encontrado")
    
    st.divider()
    
    # ===== SEÇÃO DE DOWNLOAD POR MOEDA =====
    st.subheader("📥 Download das Planilhas Finais (Separadas por Moeda)")
    
    # Gera os arquivos por moeda
    with st.spinner("Gerando arquivos por moeda..."):
        arquivos_por_moeda = gerar_arquivos_por_moeda(
            df_final, 
            df_youtube_processado, 
            df_share_out, 
            taxas_cambio, 
            nome_arquivo_original
        )
    
    if arquivos_por_moeda:
        st.success(f"✓ {len(arquivos_por_moeda)} arquivo(s) gerado(s) com sucesso!")
        
        # Separa arquivos de Masters+SharesIn e Youtube Channels
        arquivos_masters = {k: v for k, v in arquivos_por_moeda.items() if 'masters_shares_in' in k}
        arquivos_youtube = {k: v for k, v in arquivos_por_moeda.items() if 'youtube_channels' in k}
        
        # Exibe downloads de Masters + Shares In
        if arquivos_masters:
            st.write("**📊 Masters + Shares In (por moeda):**")
            
            # Cria colunas dinamicamente baseado no número de arquivos
            num_cols = min(3, len(arquivos_masters))  # Máximo 3 colunas
            cols_masters = st.columns(num_cols)
            
            for idx, (nome_arquivo, bytes_arquivo) in enumerate(sorted(arquivos_masters.items())):
                col_idx = idx % num_cols
                with cols_masters[col_idx]:
                    # Extrai a moeda do nome do arquivo para exibição
                    moeda = nome_arquivo.split('_')[3]  # Pega a moeda do padrão: masters_shares_in_MOEDA_arquivo.xlsx
                    
                    st.download_button(
                        label=f"📄 {moeda}",
                        data=bytes_arquivo,
                        file_name=nome_arquivo,
                        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                        key=f"download_masters_{moeda}_{idx}"
                    )
        
        st.divider()
        
        # Exibe downloads de Youtube Channels
        if arquivos_youtube:
            st.write("**📺 Youtube Channels (por moeda):**")
            
            # Cria colunas dinamicamente baseado no número de arquivos
            num_cols_yt = min(3, len(arquivos_youtube))
            cols_youtube = st.columns(num_cols_yt)
            
            for idx, (nome_arquivo, bytes_arquivo) in enumerate(sorted(arquivos_youtube.items())):
                col_idx = idx % num_cols_yt
                with cols_youtube[col_idx]:
                    # Extrai a moeda do nome do arquivo
                    moeda = nome_arquivo.split('_')[2]  # Pega a moeda do padrão: youtube_channels_MOEDA_arquivo.xlsx
                    
                    st.download_button(
                        label=f"📄 {moeda}",
                        data=bytes_arquivo,
                        file_name=nome_arquivo,
                        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                        key=f"download_youtube_{moeda}_{idx}"
                    )
        else:
            st.info("Nenhum dado do Youtube Channels para download")
    else:
        st.warning("Nenhum arquivo foi gerado. Verifique os dados processados.")

else:
    pass