import streamlit as st
import pandas as pd
import os
from io import BytesIO

#----------------------------------
# Royalties by Channel App
#----------------------------------


title = st.title("Royalties by Channel")

descritivo = st.caption("Cria a planilha Royalties by Channel para uso do financeiro.")

selectbox = st.selectbox("Selecione a fonte", ['ABRAMUS', 'UBC'])

# Inputs do usuário para os caminhos dos arquivos
source_file = st.file_uploader('Upload do relatório', type=['csv', 'xlsx'])  # Carregando o arquivo CSV

# Definindo caminhos fixos para as planilhas de mapeamento
target_path = 'data/mapping/planilha-target.xlsx'
mapping_file_path = 'data/mapping/mapping-rubricas.xlsx'

# Variáveis adicionais para o mês e ano
mes = st.number_input('Mês', min_value=1, max_value=12, value=1, step=1)  # Exemplo de período
ano = st.number_input('Ano', min_value=1900, max_value=2100, value=2024, step=1)
source_name = selectbox  # Variável para a coluna Source

# Função para extrair as informações iniciais diretamente do arquivo CSV
def extract_catalog_and_period_abramus(source_file):
    metadata = [next(source_file).decode('latin1').strip() for _ in range(4)]
    
    # Extraindo "Catalog" e "Period" dos metadados
    catalog = metadata[1].split(":")[1].strip()  # Linha 2 para "Catalog"
    period = metadata[3].split(":")[1].strip()   # Linha 4 para "Period"
    
    return catalog, period

def extract_catalog_and_period_ubc(source_file):
    # Read the first few rows of the Excel file to extract metadata
    df_metadata = pd.read_excel(source_file, nrows=5)
    
    # Extract catalog (name) from the row that starts with "Nome:"
    name_row = df_metadata[df_metadata.iloc[:, 0].str.contains("Nome:", na=False)].iloc[0, 0]
    catalog = name_row.split("Nome:")[1].strip()
    
    # Extract period from the row that starts with "Período:"
    period_row = df_metadata[df_metadata.iloc[:, 0].str.contains("Período:", na=False)].iloc[0, 0]
    period_text = period_row.split("Período:")[1].strip()
    
    # Convert period format (e.g., "Nov de 2024" to "2024-11")
    month_map = {
        'Jan': '01', 'Fev': '02', 'Mar': '03', 'Abr': '04',
        'Mai': '05', 'Jun': '06', 'Jul': '07', 'Ago': '08',
        'Set': '09', 'Out': '10', 'Nov': '11', 'Dez': '12'
    }
    
    # Split the period text and extract month and year
    month_text = period_text.split()[0]
    year = period_text.split()[-1]
    
    # Convert to desired format
    month_number = month_map[month_text]
    period = f"{year}-{month_number}"
    
    return catalog, period

# Função para criar coluna 'Channel' baseada no arquivo de mapeamento
def map_channel(df, mapping_file_path):
    mapping_df = pd.read_excel(mapping_file_path, sheet_name='Sheet1')
    
    # Realizando o mapeamento
    df['Channel'] = df['Rubrica'].map(mapping_df.set_index('Rubrica')['Channel']).fillna("Not Mapped")
    
    return df

# Função para criar a coluna 'Key' com separador "|"
def create_key_column(df):
    df['Key'] = df.apply(lambda row: "|".join(row.values.astype(str)), axis=1)
    return df



if selectbox == "ABRAMUS":

    # Função de processamento do relatório ABRAMUS
    def processa_abramus():
        # Botão para iniciar o processamento
        if st.button('Criar arquivo', type='primary'):
            # Verifica se o arquivo CSV foi carregado
            if source_file is not None:
                try:
                    # Lendo as planilhas
                    st.write("Carregando os dados...")
                    target_df = pd.read_excel(target_path, header=None)  # Planilha com headers padrão
                    source_df = pd.read_csv(source_file, sep=';', encoding='latin1', header=4)  # Planilha com conteúdo a ser copiado
                    
                    # Extraindo Catalog e Period da planilha de origem
                    source_file.seek(0)  # Volta ao início do arquivo carregado
                    catalog, period = extract_catalog_and_period_abramus(source_file)

                    # Criando o DataFrame final com os headers da target e adicionando conteúdo da source
                    final_df = source_df[['RUBRICA', 'RATEIO', 'TIPO DISTRIBUIÇÃO']].copy()
                    final_df.columns = ['Rubrica', 'Rendimentos', 'Tipo Distribuição']
                    final_df['Catalog'] = catalog
                    final_df['Period'] = f"{ano}-{str(mes).zfill(2)}"
                    final_df['Source'] = source_name  # Usando a variável "Source"

                    # Mapeando o Channel usando o arquivo de mapeamento
                    final_df = map_channel(final_df, mapping_file_path)

                    # Criando a coluna 'Key' com separador "|"
                    final_df = create_key_column(final_df)

                    # Reordenando as colunas
                    final_df = final_df[['Catalog', 'Source', 'Period', 'Rubrica', 'Channel', 'Rendimentos', 'Tipo Distribuição', 'Key']]

                    # Salvando o DataFrame final em memória (buffer)
                    buffer = BytesIO()
                    final_df.to_excel(buffer, index=False)
                    buffer.seek(0)

                    # Disponibilizando o botão de download
                    st.download_button(
                        label="Baixar arquivo processado",
                        data=buffer,
                        file_name=f'Royalties_by_Channel_{catalog}.xlsx',
                        mime='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
                    )

                except Exception as e:
                    st.error(f"Ocorreu um erro: {e}")


if selectbox == "UBC":

    # Função de processamento do relatório UBC
    def processa_ubc():
    # Botão para iniciar o processamento
        if st.button('Criar arquivo', type='primary'):
            # Verifica se o arquivo Excel foi carregado
            if source_file is not None:
                try:
                    # Lendo as planilhas
                    st.write("Carregando os dados...")
                    target_df = pd.read_excel(target_path, header=None)  # Planilha com headers padrão
                    
                    # Extract metadata first
                    catalog, period = extract_catalog_and_period_ubc(source_file)
                    
                    # Reset file pointer and read main data
                    source_df = pd.read_excel(source_file, skiprows=6, usecols=["Descrição", "Rendimento Total do Titular"])

                    # Remove a última linha (que contém a soma)
                    source_df = source_df.iloc[:-1]
                    
                    # Renomeando colunas para o formato esperado
                    source_df.columns = ['Rubrica', 'Rendimentos']

                    # Adicionando colunas adicionais
                    source_df['Tipo Distribuição'] = 'Padrão'  # Placeholder
                    source_df['Catalog'] = catalog
                    source_df['Period'] = period  # Using the extracted and formatted period
                    source_df['Source'] = source_name

                    # Mapeando o Channel usando o arquivo de mapeamento
                    final_df = map_channel(source_df, mapping_file_path)

                    # Criando a coluna 'Key' com separador "|"
                    final_df = create_key_column(final_df)

                    # Reordenando as colunas
                    final_df = final_df[['Catalog', 'Source', 'Period', 'Rubrica', 'Channel', 'Rendimentos', 'Tipo Distribuição', 'Key']]

                    # Salvando o DataFrame final em memória (buffer)
                    buffer = BytesIO()
                    final_df.to_excel(buffer, index=False)
                    buffer.seek(0)

                    # Disponibilizando o botão de download
                    st.download_button(
                        label="Baixar arquivo processado",
                        data=buffer,
                        file_name=f'Royalties_by_Channel_{catalog}.xlsx',
                        mime='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
                    )

                except Exception as e:
                    st.error(f"Ocorreu um erro: {e}")



if __name__ == "__main__":
    if selectbox == "ABRAMUS":
        processa_abramus()
    elif selectbox == "UBC":
        processa_ubc()

