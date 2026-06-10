import streamlit as st
import pandas as pd
from io import BytesIO
import zipfile
import locale
import unicodedata
import re
import os
import logging
from pathlib import Path

# Configurar logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def format_br(value):
    return f"{value:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")

def format_fx_rate(value):
    return f"{value:.4f}".replace(".", ",")

#----------------------------------
# Ingrooves Breaker
#----------------------------------

st.title("Ingrooves Breaker")
st.caption("Desconta 30% das receitas EUA do relatório Ingrooves e separa por artista usando mapeamento externo.")

#----------------------------------
# Inicializa variáveis de estado da sessão
#----------------------------------
if 'uploaded_file' not in st.session_state:
    st.session_state['uploaded_file'] = None
if 'net_dollars' not in st.session_state:
    st.session_state['net_dollars'] = None
if 'net_withholding_total' not in st.session_state:
    st.session_state['net_withholding_total'] = None
if 'total_withheld' not in st.session_state:
    st.session_state['total_withheld'] = None
if 'processed_data' not in st.session_state:
    st.session_state['processed_data'] = None
if 'show_fx_rate' not in st.session_state:
    st.session_state['show_fx_rate'] = False
if 'show_summary' not in st.session_state:
    st.session_state['show_summary'] = False
if 'summary_df' not in st.session_state:
    st.session_state['summary_df'] = None
if 'total_geral_values' not in st.session_state:
    st.session_state['total_geral_values'] = {
        'Total Net Dollars': 0,
        'Total BRL': 0,
        'Difference Net Dollars': 0,
        'Difference BRL': 0
    }
if 'artist_dataframes' not in st.session_state:
    st.session_state['artist_dataframes'] = {}
if 'matched_artists' not in st.session_state:
    st.session_state['matched_artists'] = {}
if 'mapping_df' not in st.session_state:
    st.session_state['mapping_df'] = None
if 'processed_df' not in st.session_state:
    st.session_state['processed_df'] = None
if 'unclassified_artists' not in st.session_state:
    st.session_state['unclassified_artists'] = []

#----------------------------------
# Funções auxiliares
#----------------------------------
def reset_state():
    st.session_state['net_dollars'] = None
    st.session_state['net_withholding_total'] = None
    st.session_state['total_withheld'] = None
    st.session_state['processed_data'] = None
    st.session_state['show_fx_rate'] = False
    st.session_state['show_summary'] = False
    st.session_state['summary_df'] = None
    st.session_state['total_geral_values'] = {
        'Total Net Dollars': 0,
        'Total BRL': 0,
        'Difference Net Dollars': 0,
        'Difference BRL': 0
    }
    st.session_state['uploaded_file'] = None
    st.session_state['artist_dataframes'] = {}
    st.session_state['matched_artists'] = {}
    st.session_state['processed_df'] = None
    st.session_state['unclassified_artists'] = []
    # Não resetamos o mapping_df para manter o mapeamento carregado

def normalize_text(s):
    """
    Função para normalizar texto:
    - Remove acentos
    - Converte para minúsculas
    - Remove caracteres especiais mantendo apenas letras, números e espaços
    - Remove espaços extras
    """
    if not isinstance(s, str):
        return ''
    
    s = unicodedata.normalize('NFKD', s).encode('ASCII', 'ignore').decode('ASCII')
    s = s.lower()
    s = re.sub(r'[^\w\s]', '', s)
    s = ' '.join(s.split())
    
    return s

def create_excel_with_formatted_numbers(df, filename):
    output = BytesIO()
    writer = pd.ExcelWriter(output, engine='xlsxwriter')
    
    df.to_excel(writer, index=False, sheet_name='Sheet1')
    
    workbook = writer.book
    worksheet = writer.sheets['Sheet1']
    num_format = workbook.add_format({'num_format': '#,##0.00'})
    
    for idx, col in enumerate(df.columns):
        if df[col].dtype in ['float64', 'int64']:
            worksheet.set_column(idx, idx, 18, num_format)
    
    writer.close()
    return output.getvalue()

def match_artist_from_mapping(artist_name, mapping_df):
    """
    Função para correspondência de artistas usando a planilha de mapeamento.
    Retorna o valor da coluna Tag_Artista se encontrar correspondência ou None.
    """
    if not isinstance(artist_name, str) or mapping_df is None:
        return None
    
    # Correspondência exata
    exact_match = mapping_df[mapping_df['Artist'] == artist_name]
    if not exact_match.empty:
        return exact_match.iloc[0]['Tag_Artista']
    
    # Correspondência normalizada
    normalized_artist = normalize_text(artist_name)
    
    for idx, row in mapping_df.iterrows():
        map_artist = row['Artist']
        map_tag = row['Tag_Artista']
        
        if not isinstance(map_artist, str) or not isinstance(map_tag, str):
            continue
            
        normalized_map_artist = normalize_text(map_artist)
        
        if normalized_artist in normalized_map_artist or normalized_map_artist in normalized_artist:
            return map_tag
    
    return None

def unclassified_artists_to_dataframe(unclassified_list):
    if not unclassified_list:
        return pd.DataFrame()
    
    data = []
    for artist_info in unclassified_list:
        data.append({
            "Artist": artist_info['artist'],
            "Total Net Dollars": artist_info['net_dollars'],
            "Total BRL": artist_info['brl']
        })
    
    return pd.DataFrame(data)

def load_mapping_file():
    mapping_path = os.path.join("data", "mapping", "mapping-artistas-ingrooves.xlsx")
    
    try:
        mapping_df = pd.read_excel(mapping_path)
        if 'Artist' in mapping_df.columns and 'Tag_Artista' in mapping_df.columns:
            st.success(f"✅ Arquivo de mapeamento carregado com sucesso: {mapping_path}")
            return mapping_df
        else:
            st.error(f"❌ O arquivo de mapeamento não contém as colunas necessárias (Artist, Tag_Artista)")
            return None
    except Exception as e:
        st.error(f"❌ Erro ao carregar arquivo de mapeamento: {str(e)}")
        return None

def export_mapping_df(mapping_df):
    if mapping_df is None or mapping_df.empty:
        return None
        
    output = BytesIO()
    mapping_df.to_excel(output, index=False)
    output.seek(0)
    return output.getvalue()

def process_file(df, mapping_df):
    """
    Processa o arquivo aplicando o desconto e o mapeamento de artistas.
    Linhas com Sales Description 'Non-transactional' são agrupadas numa
    categoria própria antes de qualquer mapeamento.
    """
    if df is None or mapping_df is None:
        return None, 0, 0, 0
    
    # Valor original antes do desconto
    original_total = df['Net Dollars after Fees'].sum()
    
    # Aplica o desconto de 30% nas receitas dos EUA
    df['Net Dollars after Fees'] = df.apply(
        lambda row: row['Net Dollars after Fees'] * 0.7 if row['Territory'] == 'United States' 
        else row['Net Dollars after Fees'],
        axis=1
    )
    
    # Valor após o desconto
    discounted_total = df['Net Dollars after Fees'].sum()
    total_withheld = original_total - discounted_total
    
    # ------------------------------------------------------------------
    # NOVO: identificar linhas Non-transactional ANTES do mapeamento
    # ------------------------------------------------------------------
    NON_TRANSACTIONAL_LABEL = 'Ajustes Non-Transactional'

    mask_non_transactional = df['Sales Description'].str.contains(
        'non-transactional',
        case=False,
        na=False
    )

    # Atribui artista e grupo fixo para essas linhas
    df.loc[mask_non_transactional, 'Artist'] = NON_TRANSACTIONAL_LABEL
    df.loc[mask_non_transactional, 'Matched Group'] = NON_TRANSACTIONAL_LABEL
    # ------------------------------------------------------------------

    # Tratar artistas em branco/null (apenas nas linhas que NÃO são non-transactional)
    df.loc[~mask_non_transactional, 'Artist'] = (
        df.loc[~mask_non_transactional, 'Artist']
        .fillna('indefinido (adicionar ao mapeamento)')
        .replace('', 'adicionar ao mapeamento')
    )

    # Adicionar coluna para rastreamento de processamento
    df['Processed'] = False
    
    # Aplicar o mapeamento apenas nas linhas que ainda não têm Matched Group
    mask_needs_mapping = df['Matched Group'].isna()
    df.loc[mask_needs_mapping, 'Matched Group'] = df.loc[mask_needs_mapping, 'Artist'].apply(
        lambda x: match_artist_from_mapping(x, mapping_df)
    )
    
    return df, original_total, discounted_total, total_withheld

def get_unmatched_artists_with_values(df, fx_rate):
    if df is None:
        return []
    
    unmatched_artists_df = df[df['Matched Group'].isna()]
    unmatched_artists = []
    
    if not unmatched_artists_df.empty:
        for artist in unmatched_artists_df['Artist'].unique():
            artist_data = unmatched_artists_df[unmatched_artists_df['Artist'] == artist]
            total_net_dollars = artist_data['Net Dollars after Fees'].sum()
            
            if total_net_dollars > 0:
                unmatched_artists.append({
                    'artist': artist,
                    'net_dollars': round(total_net_dollars, 2),
                    'brl': round(total_net_dollars * fx_rate, 2)
                })
    
    unmatched_artists.sort(key=lambda x: x['net_dollars'], reverse=True)
    
    return unmatched_artists

def generate_summary(df, fx_rate):
    if df is None:
        return None, None, None, []
    
    grouped_df = pd.DataFrame(columns=["Artist", "Total Net Dollars", "FX Rate", "Total BRL"])
    artist_dfs = {}
    
    # Agrupar por 'Matched Group' não nulo
    df_with_group = df[df['Matched Group'].notna()]
    grouped_data = df_with_group.groupby('Matched Group')
    
    for group_name, group_data in grouped_data:
        total_net_dollars = group_data['Net Dollars after Fees'].sum()
        total_brl = total_net_dollars * fx_rate
        
        grouped_df = pd.concat([grouped_df, pd.DataFrame([{
            "Artist": group_name,
            "Total Net Dollars": round(total_net_dollars, 2),
            "FX Rate": fx_rate,
            "Total BRL": round(total_brl, 2)
        }])], ignore_index=True)
        
        artist_dfs[group_name] = group_data
        df.loc[group_data.index, 'Processed'] = True
    
    # Agrupar artistas sem Matched Group
    df_without_group = df[df['Matched Group'].isna()]
    if not df_without_group.empty:
        unmatched_grouped = df_without_group.groupby('Artist')
        
        for artist_name, artist_data in unmatched_grouped:
            total_net_dollars = artist_data['Net Dollars after Fees'].sum()
            total_brl = total_net_dollars * fx_rate
            
            grouped_df = pd.concat([grouped_df, pd.DataFrame([{
                "Artist": artist_name,
                "Total Net Dollars": round(total_net_dollars, 2),
                "FX Rate": fx_rate,
                "Total BRL": round(total_brl, 2)
            }])], ignore_index=True)
            
            artist_dfs[artist_name] = artist_data
            df.loc[artist_data.index, 'Processed'] = True
    
    # Ordenar por valor (maior para menor), mantendo "Ajustes Non-Transactional" sempre no final
    NON_TRANSACTIONAL_LABEL = 'Ajustes Non-Transactional'
    df_main = grouped_df[grouped_df['Artist'] != NON_TRANSACTIONAL_LABEL].sort_values(
        by="Total Net Dollars", ascending=False
    )
    df_non_transactional = grouped_df[grouped_df['Artist'] == NON_TRANSACTIONAL_LABEL]
    grouped_df = pd.concat([df_main, df_non_transactional], ignore_index=True)

    # Linha de total
    total_net_dollars_df = grouped_df['Total Net Dollars'].sum()
    total_brl_df = grouped_df['Total BRL'].sum()
    total_row = pd.DataFrame([{
        "Artist": "TOTAL",
        "Total Net Dollars": round(total_net_dollars_df, 2),
        "FX Rate": fx_rate,
        "Total BRL": round(total_brl_df, 2)
    }])
    grouped_df = pd.concat([grouped_df, total_row], ignore_index=True)

    unclassified_artists = []

    total_net_dollars = df['Net Dollars after Fees'].sum()
    total_brl = total_net_dollars * fx_rate
    difference_net_dollars = total_net_dollars - total_net_dollars_df
    difference_brl = total_brl - total_brl_df

    total_geral_values = {
        'Total Net Dollars': round(total_net_dollars, 2),
        'Total BRL': round(total_brl, 2),
        'Difference Net Dollars': round(difference_net_dollars, 2),
        'Difference BRL': round(difference_brl, 2)
    }
    
    return grouped_df, artist_dfs, total_geral_values, unclassified_artists

#----------------------------------
# Interface principal
#----------------------------------

if st.session_state['mapping_df'] is None:
    st.session_state['mapping_df'] = load_mapping_file()

uploaded_file = st.file_uploader("Selecione o relatório Ingrooves", key="file_uploader")

if uploaded_file and st.session_state.uploaded_file != uploaded_file:
    reset_state()
    st.session_state.uploaded_file = uploaded_file

if uploaded_file is not None and st.session_state['mapping_df'] is not None:
    try:
        df = pd.read_excel(uploaded_file, sheet_name='Digital Sales Details')
        df = df[~df['Sales Classification'].str.contains("Total", case=False, na=False)]
        
        processed_df, original_total, discounted_total, total_withheld = process_file(
            df, 
            st.session_state['mapping_df']
        )
        
        st.session_state['processed_df'] = processed_df
        st.session_state.net_dollars = original_total
        st.session_state.net_withholding_total = discounted_total
        st.session_state.total_withheld = total_withheld
        
        output = BytesIO()
        writer = pd.ExcelWriter(output, engine='xlsxwriter')
        processed_df.to_excel(writer, sheet_name='Digital Sales Details', index=False)
        writer.close()
        st.session_state.processed_data = output.getvalue()
        
        st.write(f'O valor Original é **USD {format_br(original_total)}**')
        st.write(f'O total de withholding aplicado é **USD {format_br(total_withheld)}**')
        st.write(f':red[O valor Net menos withholding é **USD {format_br(discounted_total)}**]')
        
        st.session_state.show_fx_rate = True
        
    except Exception as e:
        st.error(f"Erro ao processar o arquivo: {str(e)}")
        import traceback
        st.error(traceback.format_exc())

elif uploaded_file is not None and st.session_state['mapping_df'] is None:
    st.warning("⚠️ Não foi possível carregar o arquivo de mapeamento. Verifique se o arquivo está no caminho correto: data/mapping/mapping-artistas-ingrooves.xlsx")

if st.session_state.show_fx_rate:
    fx_rate = st.number_input("Adicione aqui a taxa de câmbio (FX rate)", value=0.0, format="%.4f")
    
    if st.session_state['processed_df'] is not None and fx_rate > 0:
        unmatched_artists = get_unmatched_artists_with_values(st.session_state['processed_df'], fx_rate)
        
        if unmatched_artists:
            st.markdown("### ⚠️ Artistas não encontrados no mapeamento")
            st.info("Os seguintes artistas não foram encontrados na planilha de mapeamento e precisam ser adicionados manualmente:")
            
            total_unmatched_usd = sum(artist['net_dollars'] for artist in unmatched_artists)
            total_unmatched_brl = sum(artist['brl'] for artist in unmatched_artists)
            
            st.markdown(f"**Total de artistas não encontrados:** {len(unmatched_artists)}")
            st.markdown(f"**Valor total não classificado:** USD {format_br(total_unmatched_usd)} (BRL {format_br(total_unmatched_brl)})")
            
            for i, artist_info in enumerate(unmatched_artists, 1):
                st.markdown(f"{i}. **{artist_info['artist']}** - USD {format_br(artist_info['net_dollars'])} (BRL {format_br(artist_info['brl'])})")
    
    if fx_rate > 0 and st.session_state['processed_df'] is not None:
        summary_df, artist_dfs, total_geral_values, unclassified_artists = generate_summary(
            st.session_state['processed_df'],
            fx_rate
        )
        
        st.session_state.summary_df = summary_df
        st.session_state.artist_dataframes = artist_dfs
        st.session_state.total_geral_values = total_geral_values
        st.session_state['unclassified_artists'] = unclassified_artists
        st.session_state.show_summary = True

if st.session_state.show_summary and st.session_state.summary_df is not None:
    st.divider()
    st.write("### Agrupamento por artista:")
    
    display_df = st.session_state.summary_df.copy()
    display_df['Total Net Dollars'] = display_df['Total Net Dollars'].apply(lambda x: f"{x:,.2f}".replace(",", "X").replace(".", ",").replace("X", "."))
    display_df['FX Rate'] = display_df['FX Rate'].apply(lambda x: f"{x:.4f}".replace(".", ","))
    display_df['Total BRL'] = display_df['Total BRL'].apply(lambda x: f"{x:,.2f}".replace(",", "X").replace(".", ",").replace("X", "."))
    st.dataframe(display_df)

    if 'unclassified_artists' in st.session_state and st.session_state['unclassified_artists']:
        st.write("### ⚠️ Artistas não encontrados no mapeamento:")
        
        for i, artist_info in enumerate(st.session_state['unclassified_artists'], 1):
            st.write(f"{i}. **{artist_info['artist']}** - USD {format_br(artist_info['net_dollars'])} (BRL {format_br(artist_info['brl'])})")
        
        total_unclassified_usd = sum(artist['net_dollars'] for artist in st.session_state['unclassified_artists'])
        total_unclassified_brl = sum(artist['brl'] for artist in st.session_state['unclassified_artists'])
        
        st.markdown(f"**Total de artistas não encontrados:** {len(st.session_state['unclassified_artists'])}")
        st.markdown(f"**Total USD:** {format_br(total_unclassified_usd)}")
        st.markdown(f"**Total BRL:** {format_br(total_unclassified_brl)}")

    if st.session_state.artist_dataframes:
        zip_buffer = BytesIO()
        with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zip_file:
            for artist, artist_df in st.session_state.artist_dataframes.items():
                safe_name = re.sub(r'[\\/*?:"<>|]', "", artist)
                excel_data = create_excel_with_formatted_numbers(artist_df, f"{safe_name}.xlsx")
                zip_file.writestr(f"{safe_name}.xlsx", excel_data)
            
            if st.session_state.processed_data:
                zip_file.writestr("Relatório_Processado_Completo.xlsx", st.session_state.processed_data)
                
            mapping_data = export_mapping_df(st.session_state['mapping_df'])
            if mapping_data:
                zip_file.writestr("Mapeamento_Artistas.xlsx", mapping_data)
        
        zip_buffer.seek(0)
        st.download_button(
            label="Baixar planilhas por artista",
            data=zip_buffer.getvalue(),
            file_name="planilhas_por_artista.zip",
            mime="application/zip"
        )
    
    st.divider()
    st.markdown(
        f"### Total Geral\n"
        f"**Total Net Dollars:** USD {format_br(st.session_state.total_geral_values['Total Net Dollars'])}\n\n"
        f"**Total BRL:** BRL {format_br(st.session_state.total_geral_values['Total BRL'])}\n\n"
        f":red[**Diferença Net Dollars: USD {format_br(st.session_state.total_geral_values['Difference Net Dollars'])}**]\n\n"
        f":red[**Diferença BRL: BRL {format_br(st.session_state.total_geral_values['Difference BRL'])}**]"
    )

    if 'unclassified_artists' in st.session_state and st.session_state['unclassified_artists']:
        unclassified_df = unclassified_artists_to_dataframe(st.session_state['unclassified_artists'])
        if not unclassified_df.empty:
            excel_data = create_excel_with_formatted_numbers(unclassified_df, "artistas_nao_classificados.xlsx")
            st.download_button(
                label="Baixar lista de artistas não classificados",
                data=excel_data,
                file_name="artistas_nao_classificados.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            )