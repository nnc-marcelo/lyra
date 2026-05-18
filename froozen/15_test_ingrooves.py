import streamlit as st
import pandas as pd
from io import BytesIO
import zipfile
import unicodedata
import re
import os
import logging
from pathlib import Path


# Configurar logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def format_br(value):
    # Converte para string com 2 casas decimais, usando vírgula como decimal e ponto como separador de milhar
    return f"{value:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")

def format_fx_rate(value):
    # Formata a taxa de câmbio com 4 casas decimais
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
    
    # Remover acentos
    s = unicodedata.normalize('NFKD', s).encode('ASCII', 'ignore').decode('ASCII')
    # Converter para minúsculas
    s = s.lower()
    # Remover caracteres especiais mantendo letras, números e espaços
    s = re.sub(r'[^\w\s]', '', s)
    # Remover espaços extras e normalizar espaços
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

def match_artist_from_mapping(isrc_code, mapping_df):
    """
    Função para correspondência de ISRC usando a planilha de mapeamento
    Retorna o valor da coluna Tag_Artista se encontrar correspondência ou None
    """
    if not isinstance(isrc_code, str) or mapping_df is None:
        return None
    
    # Correspondência direta por ISRC
    exact_match = mapping_df[mapping_df['ISRC'] == isrc_code]
    if not exact_match.empty:
        tag = exact_match.iloc[0]['Tag_Artista']
        return tag
    
    return None

def unclassified_artists_to_dataframe(unclassified_list):
    """
    Converte a lista de ISRCs não classificados para um DataFrame
    """
    if not unclassified_list:
        return pd.DataFrame()
    
    data = []
    for isrc_info in unclassified_list:
        data.append({
            "ISRC": isrc_info['isrc'],
            "Total Net Dollars": isrc_info['net_dollars'],
            "Total BRL": isrc_info['brl']
        })
    
    return pd.DataFrame(data)

def load_mapping_file():
    """
    Carrega a planilha de mapeamento do local padrão
    """
    # Caminho para o arquivo de mapeamento
    mapping_path = os.path.join("data", "mapping", "mapping-artistas-ingrooves.xlsx")
    
    try:
        mapping_df = pd.read_excel(mapping_path)
        if 'ISRC' in mapping_df.columns and 'Tag_Artista' in mapping_df.columns:
            st.success(f"✅ Arquivo de mapeamento carregado com sucesso: {mapping_path}")
            return mapping_df
        else:
            st.error(f"❌ O arquivo de mapeamento não contém as colunas necessárias (ISRC, Tag_Artista)")
            return None
    except Exception as e:
        st.error(f"❌ Erro ao carregar arquivo de mapeamento: {str(e)}")
        return None

def export_mapping_df(mapping_df):
    """
    Exporta o DataFrame de mapeamento para um arquivo Excel
    """
    if mapping_df is None or mapping_df.empty:
        return None
        
    output = BytesIO()
    mapping_df.to_excel(output, index=False)
    output.seek(0)
    return output.getvalue()

def process_file(df, mapping_df):
    """
    Processa o arquivo aplicando o desconto e o mapeamento de artistas
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
    
    # Tratar ISRC em branco/null como "indefinido"
    df['ISRC'] = df['ISRC'].fillna('indefinido (adicionar ao mapeamento)')
    df['ISRC'] = df['ISRC'].replace('', 'adicionar ao mapeamento')
    
    # Adicionar coluna para rastreamento de processamento
    df['Processed'] = False
    
    # Aplicar o mapeamento para cada ISRC
    df['Matched Group'] = df['ISRC'].apply(
        lambda x: match_artist_from_mapping(x, mapping_df)
    )
    
    return df, original_total, discounted_total, total_withheld

def get_unmatched_artists_with_values(df, fx_rate):
    """
    Identifica ISRCs não encontrados no mapeamento e seus valores
    Retorna uma lista de dicionários com ISRC, valor em USD e BRL
    """
    if df is None:
        return []
    
    # Identificar ISRCs não classificados (Matched Group é nulo)
    unmatched_isrcs_df = df[df['Matched Group'].isna()]
    unmatched_isrcs = []
    
    if not unmatched_isrcs_df.empty:
        for isrc in unmatched_isrcs_df['ISRC'].unique():
            isrc_data = unmatched_isrcs_df[unmatched_isrcs_df['ISRC'] == isrc]
            total_net_dollars = isrc_data['Net Dollars after Fees'].sum()
            
            if total_net_dollars > 0:  # Só inclui se tiver valor positivo
                unmatched_isrcs.append({
                    'isrc': isrc,
                    'net_dollars': round(total_net_dollars, 2),
                    'brl': round(total_net_dollars * fx_rate, 2)
                })
    
    # Ordenar ISRCs não encontrados por valor (maior para menor)
    unmatched_isrcs.sort(key=lambda x: x['net_dollars'], reverse=True)
    
    return unmatched_isrcs

def generate_summary(df, fx_rate):
    """
    Gera o resumo dos dados agrupados por artista
    """
    if df is None:
        return None, None, None, []
    
    # Processamento dos dados por artista utilizando a coluna 'Matched Group'
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
    
    # Agrupar ISRCs não encontrados no mapeamento (incluindo "indefinido")
    df_without_group = df[df['Matched Group'].isna()]
    if not df_without_group.empty:
        # Agrupar por ISRC original (incluindo "indefinido")
        unmatched_grouped = df_without_group.groupby('ISRC')
        
        for isrc_code, isrc_data in unmatched_grouped:
            total_net_dollars = isrc_data['Net Dollars after Fees'].sum()
            total_brl = total_net_dollars * fx_rate
            
            # Adicionar diretamente no DataFrame principal de agrupamento
            grouped_df = pd.concat([grouped_df, pd.DataFrame([{
                "Artist": isrc_code,  # Agora mostra o ISRC em vez do nome do artista
                "Total Net Dollars": round(total_net_dollars, 2),
                "FX Rate": fx_rate,
                "Total BRL": round(total_brl, 2)
            }])], ignore_index=True)
            
            artist_dfs[isrc_code] = isrc_data
            df.loc[isrc_data.index, 'Processed'] = True
    
    # Ordenar por valor (do maior para o menor)
    grouped_df = grouped_df.sort_values(by="Total Net Dollars", ascending=False)
    
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

    # Agora os ISRCs não encontrados estão vazios pois foram incluídos no agrupamento principal
    unclassified_isrcs = []

    # Calcular o total geral - agora deve bater perfeitamente
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
    
    return grouped_df, artist_dfs, total_geral_values, unclassified_isrcs

def generate_mapping_template(df, unmatched_isrcs):
    """
    Gera uma planilha no formato da planilha de mapping com os ISRCs não encontrados
    Retorna um DataFrame com as colunas: Artist, Label, Album Title, Song, ISRC, Tag_Artista
    """
    if df is None or not unmatched_isrcs:
        return pd.DataFrame()
    
    mapping_template_data = []
    
    for isrc_info in unmatched_isrcs:
        isrc_code = isrc_info['isrc']
        
        # Pular ISRCs indefinidos
        if isrc_code in ['indefinido (adicionar ao mapeamento)', 'adicionar ao mapeamento']:
            continue
            
        # Buscar as informações do ISRC no DataFrame original
        isrc_rows = df[df['ISRC'] == isrc_code]
        
        if not isrc_rows.empty:
            # Pegar a primeira linha para extrair as informações
            first_row = isrc_rows.iloc[0]
            
            mapping_template_data.append({
                'Artist': first_row.get('Artist', ''),
                'Label': first_row.get('Label', ''),
                'Album Title': first_row.get('Album Title', ''),
                'Song': first_row.get('Song', ''),
                'ISRC': isrc_code,
                'Tag_Artista': ''  # Campo vazio para ser preenchido manualmente
            })
    
    # Criar DataFrame e remover duplicatas (caso o mesmo ISRC apareça várias vezes)
    mapping_template_df = pd.DataFrame(mapping_template_data)
    if not mapping_template_df.empty:
        mapping_template_df = mapping_template_df.drop_duplicates(subset=['ISRC'])
        # Ordenar por Artist para facilitar a organização
        mapping_template_df = mapping_template_df.sort_values(by='Artist')
    
    return mapping_template_df

#----------------------------------
# Interface principal
#----------------------------------

# Carregar arquivo de mapeamento (apenas uma vez)
if st.session_state['mapping_df'] is None:
    st.session_state['mapping_df'] = load_mapping_file()

# Upload do arquivo
uploaded_file = st.file_uploader("Selecione o relatório Ingrooves", key="file_uploader")

# Reset de estado quando um novo arquivo é carregado
if uploaded_file and st.session_state.uploaded_file != uploaded_file:
    reset_state()
    st.session_state.uploaded_file = uploaded_file

# Processamento do arquivo (automático quando temos o arquivo e o mapeamento)
if uploaded_file is not None and st.session_state['mapping_df'] is not None:
    try:
        # Ler o arquivo
        df = pd.read_excel(uploaded_file, sheet_name='Digital Sales Details')
        df = df[~df['Sales Classification'].str.contains("Total", case=False, na=False)]
        
        # Processar o arquivo automaticamente
        processed_df, original_total, discounted_total, total_withheld = process_file(
            df, 
            st.session_state['mapping_df']
        )
        
        # Armazenar os resultados no session_state
        st.session_state['processed_df'] = processed_df
        st.session_state.net_dollars = original_total
        st.session_state.net_withholding_total = discounted_total
        st.session_state.total_withheld = total_withheld
        
        # Preparar para download
        output = BytesIO()
        writer = pd.ExcelWriter(output, engine='xlsxwriter')
        processed_df.to_excel(writer, sheet_name='Digital Sales Details', index=False)
        writer.close()
        st.session_state.processed_data = output.getvalue()
        
        # Mostrar informações sobre o processamento
        st.write(f'O valor Original é **USD {format_br(original_total)}**')
        st.write(f'O total de withholding aplicado é **USD {format_br(total_withheld)}**')
        st.write(f':red[O valor Net menos withholding é **USD {format_br(discounted_total)}**]')
        
        # Habilitar a entrada da taxa de câmbio
        st.session_state.show_fx_rate = True
        
    except Exception as e:
        st.error(f"Erro ao processar o arquivo: {str(e)}")
        import traceback
        st.error(traceback.format_exc())
elif uploaded_file is not None and st.session_state['mapping_df'] is None:
    st.warning("⚠️ Não foi possível carregar o arquivo de mapeamento. Verifique se o arquivo está no caminho correto: data/mapping/mapping-artistas-ingrooves.xlsx")

# Área de taxa de câmbio e resumo
if st.session_state.show_fx_rate:
    fx_rate = st.number_input("Adicione aqui a taxa de câmbio (FX rate)", value=0.0, format="%.4f")
    
    # Identificar e exibir artistas não encontrados (apenas para informação)
    if st.session_state['processed_df'] is not None and fx_rate > 0:
        unmatched_artists = get_unmatched_artists_with_values(st.session_state['processed_df'], fx_rate)
        
         # ✅ Salva imediatamente para uso no template depois
        st.session_state['unclassified_artists'] = unmatched_artists or []

        if unmatched_artists:
            st.markdown("### ⚠️ ISRCs não encontrados no mapeamento")
            st.info("Os seguintes ISRCs não foram encontrados na planilha de mapeamento e precisam ser adicionados manualmente:")
            
            # Calcular total dos não encontrados
            total_unmatched_usd = sum(artist['net_dollars'] for artist in unmatched_artists)
            total_unmatched_brl = sum(artist['brl'] for artist in unmatched_artists)
            
            st.markdown(f"**Total de ISRCs não encontrados:** {len(unmatched_artists)}")
            st.markdown(f"**Valor total não classificado:** USD {format_br(total_unmatched_usd)} (BRL {format_br(total_unmatched_brl)})")
            
            # Exibir lista de artistas não encontrados
            for i, artist_info in enumerate(unmatched_artists, 1):
                st.markdown(f"{i}. **{artist_info['isrc']}** - USD {format_br(artist_info['net_dollars'])} (BRL {format_br(artist_info['brl'])})")
    
    # Gerar resumo quando a taxa de câmbio for informada
    if fx_rate > 0 and st.session_state['processed_df'] is not None:
        # Gerar o resumo
        summary_df, artist_dfs, total_geral_values, unclassified_artists = generate_summary(
            st.session_state['processed_df'],
            fx_rate
        )
        
        # Armazenar no session_state
        st.session_state.summary_df = summary_df
        st.session_state.artist_dataframes = artist_dfs
        st.session_state.total_geral_values = total_geral_values
        st.session_state['unclassified_artists'] = unclassified_artists
        st.session_state.show_summary = True

# Exibição do resumo e download
if st.session_state.show_summary and st.session_state.summary_df is not None:
    st.divider()
    st.write("### Agrupamento por artista:")
    
    # DataFrame formatado para exibição
    display_df = st.session_state.summary_df.copy()
    display_df['Total Net Dollars'] = display_df['Total Net Dollars'].apply(lambda x: f"{x:,.2f}".replace(",", "X").replace(".", ",").replace("X", "."))
    display_df['FX Rate'] = display_df['FX Rate'].apply(lambda x: f"{x:.4f}".replace(".", ","))
    display_df['Total BRL'] = display_df['Total BRL'].apply(lambda x: f"{x:,.2f}".replace(",", "X").replace(".", ",").replace("X", "."))
    st.dataframe(display_df)

     # Mostrar ISRCs não encontrados após o dataframe principal
    if 'unclassified_artists' in st.session_state and st.session_state['unclassified_artists']:
        st.write("### ⚠️ ISRCs não encontrados no mapeamento:")
        
        # Imprimir diretamente ISRC e valor de cada um
        for i, isrc_info in enumerate(st.session_state['unclassified_artists'], 1):
            st.write(f"{i}. **{isrc_info['isrc']}** - USD {format_br(isrc_info['net_dollars'])} (BRL {format_br(isrc_info['brl'])})")
        
        # Mostrar totais dos não encontrados
        total_unclassified_usd = sum(isrc_info['net_dollars'] for isrc_info in st.session_state['unclassified_artists'])
        total_unclassified_brl = sum(isrc_info['brl'] for isrc_info in st.session_state['unclassified_artists'])
        
        st.markdown(f"**Total de ISRCs não encontrados:** {len(st.session_state['unclassified_artists'])}")
        st.markdown(f"**Total USD:** {format_br(total_unclassified_usd)}")
        st.markdown(f"**Total BRL:** {format_br(total_unclassified_brl)}")

    # Botão de download das planilhas
    if st.session_state.artist_dataframes:
        zip_buffer = BytesIO()
        with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zip_file:
            for artist, artist_df in st.session_state.artist_dataframes.items():
                # Limpar nome de arquivo
                safe_name = re.sub(r'[\\/*?:"<>|]', "", artist)
                excel_data = create_excel_with_formatted_numbers(artist_df, f"{safe_name}.xlsx")
                zip_file.writestr(f"{safe_name}.xlsx", excel_data)
            
            # Adicionar o arquivo principal processado
            if st.session_state.processed_data:
                zip_file.writestr("Relatório_Processado_Completo.xlsx", st.session_state.processed_data)
                
            # Adicionar o mapeamento original
            mapping_data = export_mapping_df(st.session_state['mapping_df'])
            if mapping_data:
                zip_file.writestr("Mapeamento_Artistas.xlsx", mapping_data)
        
        zip_buffer.seek(0)
        # st.download_button(
        #     label="Baixar planilhas por artista",
        #     data=zip_buffer.getvalue(),
        #     file_name="planilhas_por_artista.zip",
        #     mime="application/zip"
        # )
    
    st.divider()
    # Total Geral
    st.markdown(
        f"### Total Geral\n"
        f"**Total Net Dollars:** USD {format_br(st.session_state.total_geral_values['Total Net Dollars'])}\n\n"
        f"**Total BRL:** BRL {format_br(st.session_state.total_geral_values['Total BRL'])}\n\n"
        f":red[**Diferença Net Dollars: USD {format_br(st.session_state.total_geral_values['Difference Net Dollars'])}**]\n\n"
        f":red[**Diferença BRL: BRL {format_br(st.session_state.total_geral_values['Difference BRL'])}**]"
    )

    # Opção para download da lista de não classificados (mantida aqui também)
   
    # Botão 1: Download das planilhas separadas por Tag_Artista (o que já existe)
    if st.session_state.artist_dataframes:
        zip_buffer = BytesIO()
        with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zip_file:
            for artist, artist_df in st.session_state.artist_dataframes.items():
                # Limpar nome de arquivo
                safe_name = re.sub(r'[\\/*?:"<>|]', "", artist)
                excel_data = create_excel_with_formatted_numbers(artist_df, f"{safe_name}.xlsx")
                zip_file.writestr(f"{safe_name}.xlsx", excel_data)
            
            # Adicionar o arquivo principal processado
            if st.session_state.processed_data:
                zip_file.writestr("Relatório_Processado_Completo.xlsx", st.session_state.processed_data)
                
            # Adicionar o mapeamento original
            mapping_data = export_mapping_df(st.session_state['mapping_df'])
            if mapping_data:
                zip_file.writestr("Mapeamento_Artistas.xlsx", mapping_data)
        
        zip_buffer.seek(0)
        st.download_button(
            label="Baixar planilhas por artista",
            data=zip_buffer.getvalue(),
            file_name="planilhas_por_artista.zip",
            mime="application/zip",
            key="download_planilhas_artista"  # Chave única
        )

    # Botão 2: Download do template de mapping para ISRCs não encontrados
    if 'unclassified_artists' in st.session_state and st.session_state['unclassified_artists']:
        mapping_template_df = generate_mapping_template(
            st.session_state['processed_df'], 
            st.session_state['unclassified_artists']
        )
        
        if not mapping_template_df.empty:
            mapping_template_excel = create_excel_with_formatted_numbers(
                mapping_template_df, 
                "template_mapping_isrcs_nao_encontrados.xlsx"
            )
            
            st.download_button(
                label="Baixar template de mapping para ISRCs não encontrados",
                data=mapping_template_excel,
                file_name="template_mapping_isrcs_nao_encontrados.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                help="Planilha com ISRCs não encontrados no formato da planilha de mapping. Preencha a coluna 'Tag_Artista' e adicione à planilha de mapping principal.",
                key="download_template_mapping"  # Chave única
            )
