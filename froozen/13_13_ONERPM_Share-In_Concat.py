import streamlit as st
import pandas as pd
import io
from typing import Dict, List, Set

# Configuração da página
st.set_page_config(
    page_title="Costa Gold Normalizer",
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

# Estrutura para Youtube Channels
estrutura_youtube = [
    "Video Title",
    "Video ID", 
    "Channel ID",
    "Store",
    "Territory",
    "Sale Type",
    "Transaction Month",
    "Accounted Date",
    "% Share",
    "Currency",
    "Quantity",
    "Onerpm Net",
    "Onerpm Gross",
    "Net",
    "Gross",
    "Payer Name",
    "Receiver Name",
    "Origem",
    "Nome Arquivo"
]

# Mapeamento para Master_Share-In (baseado no mapeamento_shares_in_out do código original)
mapeamento_master_share_in = {
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

# Mapeamento para YouTube Video de Shares In & Out para Youtube Channels
mapeamento_youtube_shares_to_channels = {
    'Title': 'Video Title',
    'ID': 'Video ID',
    'Parent ID': 'Channel ID',
    'Store': 'Store',
    'Territory': 'Territory',
    'Sale Type': 'Sale Type',
    'Transaction Month': 'Transaction Month',
    'Accounted Date': 'Accounted Date',
    '% Share In/Out': '% Share',
    'Currency': 'Currency',
    'Quantity': 'Quantity',
    'Net': 'Onerpm Net',
    'Payer Name': 'Payer Name',
    'Receiver Name': 'Receiver Name'
}

def identificar_moedas(dfs: Dict[str, pd.DataFrame]) -> Set[str]:
    """Identifica todas as moedas únicas nas planilhas"""
    moedas = set()
    for nome_planilha, df in dfs.items():
        if 'Currency' in df.columns:
            moedas_planilha = df['Currency'].dropna().unique()
            moedas.update(moedas_planilha)
    return moedas

def processar_planilha_nas_nuvens(df: pd.DataFrame, payer_names: List[str], origem: str, nome_arquivo: str) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Processa a planilha Nas Nuvens filtrando por Share Type = 'In' e Payer Name específico
    Retorna: (df_normal, df_youtube_videos)"""
    
    # Filtra por Share Type = 'In'
    if 'Share Type' in df.columns:
        df = df[df['Share Type'] == 'In'].copy()
    
    # Filtra por Payer Name (Costa Gold ou Costa Gold by DMC)
    if 'Payer Name' in df.columns:
        df = df[df['Payer Name'].isin(payer_names)].copy()
    
    # Se não há dados após filtros, retorna DataFrames vazios
    if df.empty:
        return pd.DataFrame(columns=estrutura_final), pd.DataFrame(columns=estrutura_youtube)
    
    # Separa linhas com YouTube Video das demais
    df_youtube_videos = pd.DataFrame()
    df_normal = df.copy()
    
    if 'Product Type' in df.columns:
        mask_youtube = df['Product Type'] == 'YouTube Video'
        df_youtube_videos = df[mask_youtube].copy()
        df_normal = df[~mask_youtube].copy()
    
    # Processa dados normais
    df_normal_processado = pd.DataFrame(columns=estrutura_final)
    if not df_normal.empty:
        # Aplica o mapeamento
        df_normal_processado = df_normal.rename(columns=mapeamento_master_share_in)
        
        # Adiciona colunas de origem e nome do arquivo
        df_normal_processado['Origem'] = origem
        df_normal_processado['Nome Arquivo'] = nome_arquivo
        
        # Garante que todas as colunas da estrutura final existam
        for coluna in estrutura_final:
            if coluna not in df_normal_processado.columns:
                df_normal_processado[coluna] = None
        
        # Reordena as colunas conforme a estrutura final
        df_normal_processado = df_normal_processado[estrutura_final]
    
    # Processa dados do YouTube Video
    df_youtube_processado = pd.DataFrame(columns=estrutura_youtube)
    if not df_youtube_videos.empty:
        # Aplica o mapeamento específico para YouTube
        df_youtube_processado = df_youtube_videos.rename(columns=mapeamento_youtube_shares_to_channels)
        
        # Adiciona colunas de origem e nome do arquivo
        df_youtube_processado['Origem'] = origem
        df_youtube_processado['Nome Arquivo'] = nome_arquivo
        
        # Garante que todas as colunas da estrutura youtube existam
        for coluna in estrutura_youtube:
            if coluna not in df_youtube_processado.columns:
                df_youtube_processado[coluna] = None
        
        # Reordena as colunas conforme a estrutura youtube
        df_youtube_processado = df_youtube_processado[estrutura_youtube]
    
    return df_normal_processado, df_youtube_processado

def processar_planilha_costa_gold(df: pd.DataFrame, origem: str, nome_arquivo: str) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Processa as planilhas Costa Gold e Costa Gold by DMC
    Retorna: (df_normal, df_youtube_videos)"""
    
    # Filtra por Share Type = 'In'
    if 'Share Type' in df.columns:
        df = df[df['Share Type'] == 'In'].copy()
    
    # Se não há dados após filtros, retorna DataFrames vazios
    if df.empty:
        return pd.DataFrame(columns=estrutura_final), pd.DataFrame(columns=estrutura_youtube)
    
    # Separa linhas com YouTube Video das demais
    df_youtube_videos = pd.DataFrame()
    df_normal = df.copy()
    
    if 'Product Type' in df.columns:
        mask_youtube = df['Product Type'] == 'YouTube Video'
        df_youtube_videos = df[mask_youtube].copy()
        df_normal = df[~mask_youtube].copy()
    
    # Processa dados normais
    df_normal_processado = pd.DataFrame(columns=estrutura_final)
    if not df_normal.empty:
        # Aplica o mapeamento
        df_normal_processado = df_normal.rename(columns=mapeamento_master_share_in)
        
        # Adiciona colunas de origem e nome do arquivo
        df_normal_processado['Origem'] = origem
        df_normal_processado['Nome Arquivo'] = nome_arquivo
        
        # Garante que todas as colunas da estrutura final existam
        for coluna in estrutura_final:
            if coluna not in df_normal_processado.columns:
                df_normal_processado[coluna] = None
        
        # Reordena as colunas conforme a estrutura final
        df_normal_processado = df_normal_processado[estrutura_final]
    
    # Processa dados do YouTube Video
    df_youtube_processado = pd.DataFrame(columns=estrutura_youtube)
    if not df_youtube_videos.empty:
        # Aplica o mapeamento específico para YouTube
        df_youtube_processado = df_youtube_videos.rename(columns=mapeamento_youtube_shares_to_channels)
        
        # Adiciona colunas de origem e nome do arquivo
        df_youtube_processado['Origem'] = origem
        df_youtube_processado['Nome Arquivo'] = nome_arquivo
        
        # Garante que todas as colunas da estrutura youtube existam
        for coluna in estrutura_youtube:
            if coluna not in df_youtube_processado.columns:
                df_youtube_processado[coluna] = None
        
        # Reordena as colunas conforme a estrutura youtube
        df_youtube_processado = df_youtube_processado[estrutura_youtube]
    
    return df_normal_processado, df_youtube_processado

def processar_youtube_channels(df: pd.DataFrame, taxas_cambio: Dict[str, float], origem: str, nome_arquivo: str) -> pd.DataFrame:
    """Processa a planilha Youtube Channels mantendo estrutura original e convertendo valores"""
    df_youtube = df.copy()
    
    # Adiciona colunas de origem e nome do arquivo
    df_youtube['Origem'] = origem
    df_youtube['Nome Arquivo'] = nome_arquivo
    
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

def calcular_conversoes_youtube(df: pd.DataFrame, taxas_cambio: Dict[str, float]) -> pd.DataFrame:
    """Calcula as conversões para BRL nas planilhas YouTube"""
    df = df.copy()
    
    # Converte Onerpm Net para Net (BRL)
    if 'Onerpm Net' in df.columns and 'Currency' in df.columns:
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
        
        df['Net'] = df.apply(converter_net_para_brl, axis=1)
    
    # Converte Onerpm Gross para Gross (BRL) se existir
    if 'Onerpm Gross' in df.columns and 'Currency' in df.columns:
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
        
        df['Gross'] = df.apply(converter_gross_para_brl, axis=1)
    
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
    
    # Adiciona linha de total se há dados
    if not resumo_df.empty:
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

def criar_resumo_youtube(df_youtube: pd.DataFrame) -> pd.DataFrame:
    """Cria um resumo financeiro para dados do YouTube"""
    resumo_data = []
    
    # Agrupa por origem e calcula totais
    for origem in df_youtube['Origem'].dropna().unique():
        df_origem = df_youtube[df_youtube['Origem'] == origem]
        total_net = df_origem['Net'].sum() if 'Net' in df_origem.columns else 0
        registros = len(df_origem)
        
        resumo_data.append({
            'Origem': origem,
            'Registros': registros,
            'Total Net BRL': total_net
        })
    
    resumo_df = pd.DataFrame(resumo_data)
    
    # Adiciona linha de total se há dados
    if not resumo_df.empty:
        total_registros = resumo_df['Registros'].sum()
        total_net = resumo_df['Total Net BRL'].sum()
        
        resumo_df = pd.concat([
            resumo_df,
            pd.DataFrame([{
                'Origem': 'TOTAL',
                'Registros': total_registros,
                'Total Net BRL': total_net
            }])
        ], ignore_index=True)
    
    return resumo_df

# Interface Streamlit
st.title("Costa Gold Normalizer")
st.caption("Processador de relatórios OneRPM para Costa Gold e Costa Gold by DMC")

st.divider()

# Seção de uploads
st.subheader("📂 Upload dos Arquivos")

col1, col2, col3 = st.columns(3)

with col1:
    st.write("**Nas Nuvens**")
    uploaded_nas_nuvens = st.file_uploader(
        "Upload arquivo Nas Nuvens:",
        type=['xlsx', 'xls'],
        key="nas_nuvens",
        help="Arquivo deve conter a aba 'Shares In & Out'"
    )

with col2:
    st.write("**Costa Gold**")
    uploaded_costa_gold = st.file_uploader(
        "Upload arquivo Costa Gold:",
        type=['xlsx', 'xls'],
        key="costa_gold",
        help="Arquivo deve conter a aba 'Shares In & Out'"
    )

with col3:
    st.write("**Costa Gold by DMC**")
    uploaded_costa_gold_dmc = st.file_uploader(
        "Upload arquivo Costa Gold by DMC:",
        type=['xlsx', 'xls'],
        key="costa_gold_dmc",
        help="Arquivo deve conter a aba 'Shares In & Out'"
    )

# Verifica se pelo menos um arquivo foi enviado
arquivos_enviados = []
if uploaded_nas_nuvens:
    arquivos_enviados.append(("Nas Nuvens", uploaded_nas_nuvens))
if uploaded_costa_gold:
    arquivos_enviados.append(("Costa Gold", uploaded_costa_gold))
if uploaded_costa_gold_dmc:
    arquivos_enviados.append(("Costa Gold by DMC", uploaded_costa_gold_dmc))

if arquivos_enviados:
    try:
        # Carrega e processa os arquivos
        dfs_carregados = {}
        
        with st.spinner("Carregando arquivos..."):
            for nome, arquivo in arquivos_enviados:
                excel_file = pd.ExcelFile(arquivo)
                abas_existentes = excel_file.sheet_names
                
                st.info(f"📄 {nome} - Abas encontradas: {', '.join(abas_existentes)}")
                
                if "Shares In & Out" in abas_existentes:
                    df = pd.read_excel(arquivo, sheet_name="Shares In & Out")
                    dfs_carregados[nome] = {
                        'df': df,
                        'arquivo': arquivo
                    }
                else:
                    st.warning(f"⚠️ Aba 'Shares In & Out' não encontrada em {nome}")
        
        if dfs_carregados:
            st.divider()
            
            # Identifica moedas de todos os arquivos
            moedas_encontradas = set()
            for nome, dados in dfs_carregados.items():
                df = dados['df']
                if 'Currency' in df.columns:
                    moedas_df = df['Currency'].dropna().unique()
                    moedas_encontradas.update(moedas_df)
            
            # Verifica se existe Youtube Channels em algum arquivo
            youtube_data = {}
            for nome, dados in dfs_carregados.items():
                arquivo = dados['arquivo']
                excel_file = pd.ExcelFile(arquivo)
                if "Youtube Channels" in excel_file.sheet_names:
                    df_youtube = pd.read_excel(arquivo, sheet_name="Youtube Channels")
                    youtube_data[nome] = {
                        'df': df_youtube,
                        'arquivo': arquivo
                    }
                    # Adiciona moedas do Youtube Channels
                    if 'Currency' in df_youtube.columns:
                        moedas_youtube = df_youtube['Currency'].dropna().unique()
                        moedas_encontradas.update(moedas_youtube)
            
            # Configuração de taxas de câmbio
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
            if st.button("Processar Dados", type="primary"):
                with st.spinner("Processando dados..."):
                    dfs_processados = []
                    youtube_shares_dfs = []  # Para YouTube Videos das Shares In & Out
                    
                    # Processa cada arquivo
                    for nome, dados in dfs_carregados.items():
                        df = dados['df']
                        arquivo = dados['arquivo']
                        nome_arquivo = arquivo.name if arquivo.name else f"{nome}.xlsx"
                        
                        if nome == "Nas Nuvens":
                            # Filtra Nas Nuvens por Payer Name = Costa Gold ou Costa Gold by DMC
                            payer_names = ["Costa Gold", "Costa Gold by DMC"]
                            df_processado, df_youtube_shares = processar_planilha_nas_nuvens(
                                df, payer_names, nome, nome_arquivo
                            )
                        else:
                            # Processa Costa Gold e Costa Gold by DMC
                            df_processado, df_youtube_shares = processar_planilha_costa_gold(
                                df, nome, nome_arquivo
                            )
                        
                        if not df_processado.empty:
                            # Calcula Net BRL
                            df_processado = calcular_net_brl(df_processado, taxas_cambio)
                            dfs_processados.append(df_processado)
                            st.success(f"✓ {nome} processado: {len(df_processado)} registros")
                        else:
                            st.info(f"ℹ️ Nenhum dado normal encontrado em {nome}")
                        
                        if not df_youtube_shares.empty:
                            # Calcula conversões para YouTube
                            df_youtube_shares = calcular_conversoes_youtube(df_youtube_shares, taxas_cambio)
                            youtube_shares_dfs.append(df_youtube_shares)
                            st.success(f"✓ YouTube Videos de {nome}: {len(df_youtube_shares)} registros")
                    
                    # Processa Youtube Channels se existir
                    youtube_channels_dfs = []
                    if youtube_data:
                        for nome, dados in youtube_data.items():
                            df_youtube = dados['df']
                            arquivo = dados['arquivo']
                            nome_arquivo = arquivo.name if arquivo.name else f"{nome}.xlsx"
                            
                            df_youtube_proc = processar_youtube_channels(df_youtube, taxas_cambio, nome, nome_arquivo)
                            if not df_youtube_proc.empty:
                                youtube_channels_dfs.append(df_youtube_proc)
                                st.success(f"✓ Youtube Channels de {nome}: {len(df_youtube_proc)} registros")
                    
                    # Concatena YouTube Shares com YouTube Channels
                    df_youtube_final = pd.DataFrame()
                    if youtube_shares_dfs or youtube_channels_dfs:
                        todos_youtube = []
                        
                        # Adiciona YouTube Videos das Shares In & Out
                        if youtube_shares_dfs:
                            todos_youtube.extend(youtube_shares_dfs)
                        
                        # Adiciona YouTube Channels
                        if youtube_channels_dfs:
                            todos_youtube.extend(youtube_channels_dfs)
                        
                        if todos_youtube:
                            df_youtube_final = pd.concat(todos_youtube, ignore_index=True)
                    
                    # Concatena todos os DataFrames normais
                    if dfs_processados:
                        df_final = pd.concat(dfs_processados, ignore_index=True)
                        
                        # Armazena no session_state
                        st.session_state['df_final'] = df_final
                        st.session_state['df_youtube_final'] = df_youtube_final
                        st.session_state['taxas_cambio'] = taxas_cambio
                        st.session_state['processamento_concluido'] = True
                        
                        st.success(f"🎉 Processamento concluído! Total de registros: {len(df_final)}")
                        if not df_youtube_final.empty:
                            st.success(f"📺 YouTube consolidado: {len(df_youtube_final)} registros")
                        st.rerun()
                    else:
                        st.error("❌ Nenhum dado válido foi processado")
                        
    except Exception as e:
        st.error(f"Ocorreu um erro ao processar os arquivos: {e}")

# Exibe resultados somente após processamento
if 'df_final' in st.session_state and 'processamento_concluido' in st.session_state:
    df_final = st.session_state['df_final']
    df_youtube_final = st.session_state.get('df_youtube_final', pd.DataFrame())
    taxas_cambio = st.session_state['taxas_cambio']
    
    st.divider()
    
    # Resumo financeiro por origem
    resumo_origem = criar_resumo_financeiro_por_origem(df_final)
    
    # Visualização dos dados processados
    st.subheader("💲 Resumo Financeiro por Origem")
    
    # Mostra resumo por origem em tabela
    if not resumo_origem.empty:
        st.dataframe(
            resumo_origem.style.format({
                'Total Net BRL': lambda x: f"R$ {x:,.2f}" if pd.notna(x) else x,
                'Registros': lambda x: f"{x:,}" if pd.notna(x) else x
            }),
            use_container_width=True,
            hide_index=True
        )
    
    # Resumo YouTube se existir
    if not df_youtube_final.empty:
        st.subheader("📺 Resumo YouTube")
        resumo_youtube = criar_resumo_youtube(df_youtube_final)
        if not resumo_youtube.empty:
            st.dataframe(
                resumo_youtube.style.format({
                    'Total Net BRL': lambda x: f"R$ {x:,.2f}" if pd.notna(x) else x,
                    'Registros': lambda x: f"{x:,}" if pd.notna(x) else x
                }),
                use_container_width=True,
                hide_index=True
            )
    
    # Mostra preview dos dados
    st.write("**Preview dos dados processados (Shares In & Out):**")
    st.dataframe(df_final.head(10), use_container_width=True)
    
    if not df_youtube_final.empty:
        st.write("**Preview dos dados YouTube:**")
        st.dataframe(df_youtube_final.head(10), use_container_width=True)
    
    st.divider()
    
    # Botão de download
    st.subheader("📥 Download das Planilhas Finais")
    
    col1, col2 = st.columns(2)
    
    # Arquivo 1: Dados Processados (Masters + Shares In)
    with col1:
        st.write("**📊 Dados Processados**")
        output1 = io.BytesIO()
        with pd.ExcelWriter(output1, engine='openpyxl') as writer:
            # Prepara o DataFrame final para download
            df_final_download = preparar_df_para_download(df_final, taxas_cambio)
            df_final_download.to_excel(writer, sheet_name='Costa_Gold_Processado', index=False)
            
            # Adiciona aba de resumo
            if not resumo_origem.empty:
                resumo_origem.to_excel(writer, sheet_name='Resumo_Financeiro', index=False)
        
        st.download_button(
            label="📄 Baixar Dados Processados",
            data=output1.getvalue(),
            file_name="costa_gold_processado.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            key="download_final"
        )
    
    # Arquivo 2: Youtube Consolidado
    with col2:
        st.write("**📺 YouTube Consolidado**")
        if not df_youtube_final.empty:
            output2 = io.BytesIO()
            with pd.ExcelWriter(output2, engine='openpyxl') as writer:
                df_youtube_final.to_excel(writer, sheet_name='YouTube_Consolidado', index=False)
                
                # Adiciona aba de resumo YouTube se existir
                resumo_youtube = criar_resumo_youtube(df_youtube_final)
                if not resumo_youtube.empty:
                    resumo_youtube.to_excel(writer, sheet_name='Resumo_YouTube', index=False)
            
            st.download_button(
                label="📄 Baixar YouTube Consolidado",
                data=output2.getvalue(),
                file_name="youtube_consolidado_costa_gold.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                key="download_youtube"
            )
        else:
            st.info("Nenhum dado do YouTube para download")